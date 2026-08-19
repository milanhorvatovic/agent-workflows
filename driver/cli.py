"""Command-line surface: `python3 -m driver <run|resume|status> --config <path>`,
with `run` naming the workflow and the new run's id, and `resume` naming the
run to resume.

Exit codes: 0 success, 1 the command cannot run yet (a module it needs has
not landed), 2 bad usage or a defective config or environment. `run` creates
the run — directory and bootstrap state — and then exits 1 at the point
execution would start, because executing a step needs the context assembler
and an invocation backend; `resume` resolves the position the same way. The
created run is durable either way, which is the point: the state machine's
writes are real, and the later modules pick up exactly where these commands
stop.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

from . import PROTOCOL
from . import state as run_state
from .config import Config, ConfigError, load_config
from .workflow import WorkflowError, load_workflow


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


def _is_link(path: Path) -> bool:
    """Symlinks and NTFS junctions alike — anything that redirects the path
    elsewhere without being the content itself (setup/init.py applies the
    same rule to managed directories)."""
    if path.is_symlink():
        return True
    try:
        attributes = path.lstat().st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        # No lstat means no path to redirect; no attribute means POSIX,
        # which has no junctions.
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _entry_is_link(entry: os.DirEntry) -> bool:
    """The DirEntry twin of _is_link: is_dir(follow_symlinks=False) already
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
    return _report_position(created)


def _resume(config: Config, run_id: str) -> int:
    """Resolve the resume position (spec §8.5) and stop where execution
    would continue."""
    try:
        loaded = run_state.load(config.runs_dir / run_id)
    except run_state.StateError as error:
        print(f"driver: {error}", file=sys.stderr)
        return 2
    return _report_position(loaded)


def _report_position(loaded: run_state.RunState) -> int:
    position = loaded.position()
    if position is None:
        print(f"run {loaded.run_id}: nothing left to run")
        return 0
    print(f"run {loaded.run_id}: next is {position.id} ({position.status})")
    print(
        "driver: cannot execute it yet — the context assembler and "
        "invocation backend modules have not landed",
        file=sys.stderr,
    )
    return 1


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
    try:
        scan = os.scandir(config.runs_dir)
    except FileNotFoundError:
        # True absence only: the same error arises when any component of
        # the path is a dangling link — the runs directory itself, or the
        # configured artifact root above it — and that is a defect the
        # first run's mkdir can only trip over, not an empty state.
        dangling = next(
            (
                path
                for path in (config.runs_dir, *config.runs_dir.parents)
                if _is_link(path) and not path.exists()
            ),
            None,
        )
        if dangling is not None:
            print(f"driver: {dangling} is a dangling link", file=sys.stderr)
            return 2
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
