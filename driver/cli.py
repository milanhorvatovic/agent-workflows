"""Command-line surface: `python3 -m driver <run|resume|status> --config <path>`,
with `run` naming the workflow and the new run's id, and `resume` naming the
run to resume.

Exit codes: 0 success, 1 the command cannot run yet — a module it needs has
not landed, or the step it resolved is blocked on an input the run has not
produced (spec §9.1) — and 2 bad usage or a defective config, environment, or
framework. `run` creates the run — directory and bootstrap state — resolves
its first step and assembles the context that step would execute from, then
exits 1 at the point invocation would start; `resume` resolves the position
the same way. The created run is durable either way, which is the point: the
state machine's writes are real, and the later modules pick up exactly where
these commands stop.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

from . import PROTOCOL
from . import assembler
from . import state as run_state
from .config import Config, ConfigError, load_config
from .workflow import Workflow, WorkflowError, load_workflow


def _has_control_characters(value: str) -> bool:
    # Newlines would split one name into several output records; the rest of
    # C0 (NUL included), DEL, and C1 break paths or terminals the same way,
    # and U+2028/U+2029 are line breaks to Unicode-aware tooling.
    return any(
        character < " "
        or "\x7f" <= character <= "\x9f"
        or character in "\u2028\u2029"
        for character in value
    )


def _entry_is_link(entry: os.DirEntry) -> bool:
    """The DirEntry twin of state.is_link: is_dir(follow_symlinks=False) already
    excludes symlinks, but an NTFS junction still classifies as a directory
    there, and following one would list an external tree as a run."""
    if entry.is_symlink():
        return True
    try:
        attributes = entry.stat(follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
    except AttributeError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


# Win32 resolves these basenames through the device namespace even with
# an extension or stream suffix, superscript COM/LPT aliases included, so
# none of them can name a run directory (the run-state schema refuses the
# same set).
_RESERVED_DEVICE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])(?:[.:]|$)",
    re.IGNORECASE,
)


def _run_id(value: str) -> str:
    # Path safety only, not id-format validation — the run id joins under
    # {artifacts}/runs/, so control characters, separators, dot entries,
    # absolute paths, and colons would break or escape it. Every colon is
    # refused — an NTFS `name:stream` is a stream rather than a child
    # directory, and the ban covers drive prefixes with it — which also
    # retires the ISO-timestamp allowance the first cut of this guard made:
    # an id only POSIX can create is a state file only POSIX can share, and
    # the run-state schema now refuses the same set. What else a well-formed
    # id looks like is that schema's business, enforced where state is read.
    # A trailing dot or space is stripped by Windows normalization, so
    # `demo.` and `demo` would resolve to one directory while naming two —
    # an alias the state schema's directory-identity rules refuse, and the
    # argument guard must refuse before any path is formed.
    if (
        not value.strip()
        or value in {".", ".."}
        or value[-1] in ". "
        or _RESERVED_DEVICE.match(value)
        or _has_control_characters(value)
        or "/" in value
        or "\\" in value
        or any(character in ':?*"<>|' for character in value)
        or Path(value).is_absolute()
    ):
        raise argparse.ArgumentTypeError(f"not a run id: {value!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="driver",
        description="Reference driver for the agent-workflows protocol.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="start a new run")
    run.add_argument(
        "--workflow",
        required=True,
        help="the workflow to execute: a file under {framework}/workflows/",
    )
    # The id is caller-chosen, never generated: it names the run directory
    # (spec §8.1) and the caller is who has to find it again.
    run.add_argument(
        "run_id",
        type=_run_id,
        help="the new run's id: becomes its directory name under {artifacts}/runs/",
    )
    resume = subparsers.add_parser("resume", help="resume a run from its first unfinished step")
    # The protocol permits concurrent runs (spec §8.1), so which run to
    # resume can never be inferred; the id is part of the contract.
    resume.add_argument(
        "run_id",
        type=_run_id,
        help="the run to resume: its directory name under {artifacts}/runs/",
    )
    status = subparsers.add_parser("status", help="list the runs under the configured artifact root")
    for command in (run, resume, status):
        command.add_argument(
            "--config",
            type=Path,
            required=True,
            help="path to the driver config (JSON)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        config = load_config(arguments.config)
    except ConfigError as error:
        print(f"driver: {arguments.config}: {error}", file=sys.stderr)
        return 2
    if arguments.command == "status":
        return _status(config)
    if arguments.command == "run":
        return _run(config, arguments.workflow, arguments.run_id)
    return _resume(config, arguments.run_id)


def _run(config: Config, workflow_name: str, run_id: str) -> int:
    """Create the run — directory and bootstrap state (spec §8.1, §10) —
    then stop where execution would start."""
    try:
        workflow = load_workflow(config.framework_dir, workflow_name)
    except WorkflowError as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    try:
        run_dir, created = run_state.create_run(
            config.runs_dir, run_id, workflow, PROTOCOL
        )
    except (run_state.StateError, OSError) as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    print(f"created {run_dir}")
    return _report_position(created, workflow, config, run_dir)


def _resume(config: Config, run_id: str) -> int:
    """Resolve the resume position (spec §8.5) and stop where execution
    would continue."""
    try:
        run_dir, loaded = run_state.open_run(config.runs_dir, run_id)
    except run_state.StateError as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    # The composition is read on the way in, not only to report a position:
    # §8.2 ties a done step to its manifested output, and a document that
    # breaks that tie would otherwise be answered "nothing left to run" —
    # a run reported finished that the conformance suite rejects. Routing
    # refuses to act on such a record already; reporting is the other place
    # the same document is trusted.
    try:
        workflow = load_workflow(config.framework_dir, loaded.workflow)
        run_state.check_records(loaded, workflow)
        run_state.check_gates(loaded, workflow)
        run_state.check_manifest(loaded, workflow)
    except (WorkflowError, run_state.StateError) as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    return _report_position(loaded, workflow, config, run_dir)


def _report_position(
    loaded: run_state.RunState, workflow: Workflow, config: Config, run_dir: Path
) -> int:
    position = loaded.position()
    if position is None:
        # Nothing left to run is not the same as ended. §7 ends a run at a
        # reject or an accept at its last gate, and a document recording
        # neither has run out of records rather than finished — which is
        # what a crash between a step's completion and the verdict that
        # routes it leaves behind, the transition still owed.
        if not run_state.ended(loaded, workflow):
            print(
                f"driver: run {loaded.run_id} has no record left to run and no "
                f"decision that ends it — the run is unfinished (spec §7)",
                file=sys.stderr,
            )
            return 2
        print(f"run {loaded.run_id}: nothing left to run")
        return 0
    print(f"run {loaded.run_id}: next is {position.id} ({position.status})")
    # What is missing depends on what the position is. A gate waits on a
    # human (§7) — blocked where it has been reached and is waiting, pending
    # where the run has yet to arrive — and no context assembler or backend
    # can clear that: the gate handler is the module it needs. Which kind a
    # record is comes from the composition rather than from its status,
    # since a gate is `pending` before it is reached like any other member.
    if workflow.member_kind(position.id) == "gate":
        print(
            "driver: cannot decide it yet — the gate handler module has not landed",
            file=sys.stderr,
        )
        return 1
    # The context a step would execute from is resolved here rather than left
    # to the module that will send it, because assembling is what says the
    # position is *runnable*: a required input the run has not produced blocks
    # the step (§9.1), and reporting "next is X" while X cannot start reports
    # a readiness the run does not have. Nothing is written — the scaffold
    # §8.3 asks for belongs to the invocation that fills it, not to a command
    # that stops before one.
    try:
        assembly = assembler.assemble(
            config.framework_dir, run_dir, loaded, workflow, position.id
        )
    except assembler.BlockedError as error:
        print(f"driver: {error}", file=sys.stderr)
        return 1
    except assembler.AssemblyError as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    print(
        f"assembled {assembly.step_id} ({assembly.role}): "
        f"{len(assembly.materials)} files, {len(assembly.prompt)} characters"
    )
    print(
        "driver: cannot execute it yet — the invocation backend module has not landed",
        file=sys.stderr,
    )
    return 1


def _bound_runs(runs_dir: Path) -> int | Path:
    """The runs directory as a descriptor where the platform binds, and as
    the path otherwise.

    `scandir` reads either. Bound, the refusal is the open — `O_NOFOLLOW`
    faults a link there and nothing can be swapped in afterwards, since what
    is scanned is the directory that was opened rather than the name it had.
    The descriptor stays the caller's: `scandir` reads one it is given
    without taking ownership, so exhausting the iterator leaves it open and
    `_status` closes it in its own `finally`.
    """
    if not run_state._BINDS_TO_DIRECTORY:
        return runs_dir
    return os.open(runs_dir, os.O_RDONLY | os.O_DIRECTORY | run_state._NOFOLLOW)


def _status(config: Config) -> int:
    """Print one run id (directory name) per line, sorted."""
    # No probes: pathlib's probe methods (exists, is_dir) suppress
    # filesystem errors, so an unreadable path would read as absent and an
    # unclassifiable child would be silently dropped — zero runs as the
    # wrong answer either way. os.scandir opens the directory directly,
    # and only absence at that open means zero runs (the first run creates
    # the directory) — and true absence only: a dangling runs symlink
    # raises the same error and is a defect, not an empty state. Every
    # later failure is a defect too — exit 1 is reserved for unimplemented
    # commands, so defects land in 2 rather than escaping as tracebacks or
    # hiding as empty output.
    # A link at the runs directory itself is refused before it is read, as
    # `run` and `resume` refuse it: following one lists an external
    # directory's children as this project's runs, and the containment the
    # other two commands enforce would be contradicted by the one that
    # reports what exists. Where the platform can bind, the refusal is the
    # open itself and the scan reads that descriptor, so the directory
    # cannot be swapped between the two — the same reason state reads and
    # writes are bound. A *dangling* link is caught below, where absence and
    # a broken link arrive as the same error.
    if run_state.is_link(config.runs_dir) and config.runs_dir.exists():
        print(
            f"driver: {config.runs_dir} is a link, not the runs directory",
            file=sys.stderr,
        )
        return 2
    # A dangling link is read before the open rather than after it: absence
    # and a broken link arrive as one error from a path-based open, and as a
    # different one from a bound open — `O_NOFOLLOW` faults the link itself
    # rather than reporting what it fails to reach. Deciding here keeps one
    # answer for both, and it is the answer the first run's mkdir will meet.
    dangling = next(
        (
            path
            for path in (config.runs_dir, *config.runs_dir.parents)
            if run_state.is_link(path) and not path.exists()
        ),
        None,
    )
    if dangling is not None:
        print(f"driver: {dangling} is a dangling link", file=sys.stderr)
        return 2
    # The descriptor is this function's to close: `scandir` reads one it is
    # given without taking ownership, so exhausting the iterator leaves it
    # open — twenty `status` calls in one process leaked twenty of them.
    try:
        bound = _bound_runs(config.runs_dir)
    except FileNotFoundError:
        return 0
    except NotADirectoryError:
        print(f"driver: {config.runs_dir} is not a directory", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    try:
        return _list_runs(config, bound)
    finally:
        if isinstance(bound, int):
            os.close(bound)


def _list_runs(config: Config, bound: int | Path) -> int:
    try:
        scan = os.scandir(bound)
    except FileNotFoundError:
        # True absence: the first run creates the directory, so nothing to
        # list is not a defect.
        return 0
    except NotADirectoryError:
        print(f"driver: {config.runs_dir} is not a directory", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    # A link — symlink or junction — is never a run: following one would
    # present an external directory as a run under {artifacts}/runs/ and
    # let a later resume escape the artifact root past the run-id guard.
    # A child that cannot be classified — vanished mid-scan included,
    # hence no FileNotFoundError carve-out here — is a defect.
    try:
        with scan:
            run_ids = sorted(
                entry.name
                for entry in scan
                if entry.is_dir(follow_symlinks=False) and not _entry_is_link(entry)
            )
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    # One id per line is the output contract; a name a line cannot carry
    # is reported, never printed raw as several records.
    corrupt = next((name for name in run_ids if _has_control_characters(name)), None)
    if corrupt is not None:
        print(
            f"driver: run directory name {corrupt!r} contains control characters",
            file=sys.stderr,
        )
        return 2
    for run_id in run_ids:
        print(run_id)
    return 0
