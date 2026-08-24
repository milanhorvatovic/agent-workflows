"""Run state: the one document the executor maintains (protocol/spec.md §10).

This module owns every read and write of `{run}/workflow-state.yaml` — the
single-writer rule is enforced by shape: nothing else in the driver touches
the file, and every mutation lands through `save`, which writes a sibling
temp file and replaces atomically, so a crash leaves the previous state
rather than half of the next one.

What lands here stops deliberately short of the rest. Creation bootstraps
the intake records alone — §10 has the list complete only from the intake
gate's acceptance, and §7 makes that acceptance the write that populates
the rest, which is the gate handler's to perform when it lands. Loops
(§9.2) are a later module's, and so is materializing an import (§8.6);
this one loads the lineage that records it, resolves position (§8.5),
enforces verdict edges (§9.1), and keeps the manifest current as outputs
land (§8.2).
"""

from __future__ import annotations

import contextlib
import datetime
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import PROTOCOL, PROTOCOL_VERSION, implements
from .protocol_yaml import ProtocolYamlError, dumps, loads
from .workflow import Workflow

STATE_FILE = "workflow-state.yaml"

STATUSES = ("pending", "active", "blocked", "done", "skipped")
OUTCOMES = ("accept", "revise", "reject")
TRANSPORTS = ("blocking", "inbox")
RISKS = ("R0", "R1", "R2", "R3")

# The run-state schema's plain-directory-name shape for run ids (§8.1):
# no separators, dot entries, control characters or Unicode line
# separators, colons, Windows-forbidden filename characters, reserved
# device basenames, drive prefixes, or trailing dots and spaces — matched
# here because the driver reads state it did not necessarily write, and a
# state file naming an unusable directory is a defect to surface at load,
# not at the next path join. The literal is the schema's own pattern;
# test_state pins the two byte-for-byte so they cannot drift.
PLAIN_NAME = re.compile('^(?![A-Za-z]:)(?!\\.{1,2}$)(?!\\s+$)(?!(?:[Cc][Oo][Nn]|[Pp][Rr][Nn]|[Aa][Uu][Xx]|[Nn][Uu][Ll]|[Cc][Oo][Mm][1-9¹²³]|[Ll][Pp][Tt][1-9¹²³])(?:[.:]|$))[^/\\\\:?*"<>|\x00-\x1f\x7f-\x9f\u2028\u2029]+(?<![. ])(?![\\s\\S])')
# The run-state schema's `{run}`-relative import path (§8.6): anchored
# at `{run}/`, no dot or empty segments, backslashes, control characters
# or Unicode line separators, colons, Windows-forbidden characters,
# reserved device basenames, or trailing dots and spaces. A loader that
# checked the prefix alone would present `{run}/../outside` as validated
# lineage to the materialization that later copies it. The literal is the
# schema's own pattern; test_state pins the two byte-for-byte.
IMPORT_PATH = re.compile('^\\{run\\}(?:/(?!\\.{1,2}(?:/|$))(?!(?:[Cc][Oo][Nn]|[Pp][Rr][Nn]|[Aa][Uu][Xx]|[Nn][Uu][Ll]|[Cc][Oo][Mm][1-9¹²³]|[Ll][Pp][Tt][1-9¹²³])(?:\\.|/|$))[^/\\\\:?*"<>|\x00-\x1f\x7f-\x9f\u2028\u2029]+(?<![. ]))+(?![\\s\\S])')
# What a record id may not carry, whatever else it is. The run-state
# schema asks only for a non-empty string, and the driver does not
# narrow that to §9.4's member-id shape here — a document the suite
# accepts is not this module's to refuse. But an id reaches a terminal:
# `resume` prints the position it resolves, so a record carrying a line
# break or an escape sequence would split that line or rewrite it, which
# is the guard the run id already carries, applied where ids are read.
OUTPUT_BREAKING = re.compile("[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]")
# RFC 3339, the `format: date-time` the run-state schema declares for
# every `at` — a full date and time with an offset, the shape the
# conformance suite's format checker holds the shipped fixtures to.
RFC3339 = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?"
    r"(?:[Zz]|[-+]([0-9]{2}):([0-9]{2}))$"
)


class StateError(Exception):
    """The state file is missing, outside the schema's shape, or an operation
    would violate a §10 rule."""


@dataclass
class StepRecord:
    id: str
    status: str
    iterations: int | None = None
    stall_flags: list[str] | None = None


@dataclass
class ImportRecord:
    artifact: str
    from_run: str
    at: str


@dataclass
class GateRecord:
    gate: str
    transport: str
    outcome: str
    at: str
    phase: int | None = None


@dataclass
class RunState:
    run_id: str
    workflow: str
    protocol: str
    steps: list[StepRecord]
    gates: list[GateRecord]
    artifacts: list[str]
    imports: list[ImportRecord] | None = None
    phase: int | None = None
    risk: str | None = None
    risk_rationale: str | None = None
    instrumentation: object = None
    has_instrumentation: bool = field(default=False, repr=False)

    def record(self, step_id: str) -> StepRecord:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise StateError(f"no record for step {step_id!r}")

    def position(self) -> StepRecord | None:
        """§8.5: the `active` record if there is one, else the first record
        that is neither `done` nor `skipped`; None means nothing is left."""
        for step in self.steps:
            if step.status == "active":
                return step
        for step in self.steps:
            if step.status not in ("done", "skipped"):
                return step
        return None


def _is_run_id(value: object) -> bool:
    """The schema's plain-directory-name shape, and encodable besides.

    `PLAIN_NAME` is the schema's pattern carried verbatim, and the schema
    describes documents rather than the strings a caller may pass — a lone
    surrogate is a `str` Python holds and UTF-8 cannot encode, so it clears
    the pattern and then raises inside `mkdir` or the YAML write, which is
    the traceback every guard here exists to prevent. Checked beside the
    pattern rather than inside it, so the pin against the schema holds.
    """
    return (
        isinstance(value, str)
        and bool(PLAIN_NAME.match(value))
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    )


def create_run(
    runs_dir: Path, run_id: str, workflow: Workflow, protocol: str
) -> tuple[Path, RunState]:
    """Create `{artifacts}/runs/<run-id>/` and its bootstrap state: the entry
    stage's records alone, conditional members `skipped`, the rest `pending`
    (§10). The directory MUST NOT pre-exist — concurrent runs and re-runs
    never share one (§8.1)."""
    if not _is_run_id(run_id):
        raise StateError(f"not a run id: {run_id!r}")
    # The version is written into the document and `load` holds every
    # document to it, so an unchecked one here creates a durable run this
    # same module refuses to read back — a directory and a state file that
    # exist and cannot be resumed.
    if not PROTOCOL_VERSION.fullmatch(protocol) or not implements(protocol):
        raise StateError(
            f"cannot create a run under protocol {protocol!r}: this driver "
            f"implements {PROTOCOL} (spec §11)"
        )
    run_dir = runs_dir / run_id
    with _runs_directory(runs_dir, create=True) as runs:
        try:
            if runs is None:
                run_dir.mkdir()
            else:
                os.mkdir(run_id, dir_fd=runs)
        except FileExistsError:
            raise StateError(f"run {run_id!r} already exists") from None
        return _bootstrap(run_dir, run_id, workflow, protocol, runs)


def _bootstrap(
    run_dir: Path, run_id: str, workflow: Workflow, protocol: str, runs: int | None
) -> tuple[Path, RunState]:
    entry_stage = workflow.stages[0]
    state = RunState(
        run_id=run_id,
        workflow=workflow.name,
        protocol=protocol,
        steps=[
            StepRecord(id=member.id, status="skipped" if member.conditional else "pending")
            for member in entry_stage.members
        ],
        gates=[],
        artifacts=[],
    )
    try:
        save(state, run_dir, runs)
    except BaseException:
        # The directory exists only to hold this state, and §8.1 makes a
        # pre-existing one a refusal — so leaving an empty one behind after
        # the write that fills it failed would burn the id: the retry meets
        # "already exists" and the run it names has no state to resume.
        # Only an empty directory is removed, nothing else having written
        # into it yet, and the failure itself is what propagates.
        try:
            if runs is None:
                run_dir.rmdir()
            else:
                os.rmdir(run_dir.name, dir_fd=runs)
        except OSError:
            pass
        raise
    return run_dir, state


# Whether this platform can bind a file operation to a directory it already
# holds open. POSIX can; Windows has no `dir_fd` at all, and there the link
# checks below are the whole of what the driver can do.
_BINDS_TO_DIRECTORY = (
    {os.open, os.rename, os.unlink, os.mkdir, os.rmdir} <= os.supports_dir_fd
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# Opening a FIFO blocks until the other end is written; non-blocking
# turns that wait into a descriptor this module can look at and refuse.
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


@contextlib.contextmanager
def _runs_directory(runs_dir: Path, create: bool = False):
    """Hold `{artifacts}/runs` open and yield its descriptor, or `None`.

    The runs segment is the spec's, derived by the driver rather than
    configured (§8.1), so a link in its place redirects every run the
    artifact root is supposed to contain — and binding the run directory
    alone does not notice: the child of a linked `runs` is an ordinary
    directory inside the target, which passes its own link check and its
    own `O_NOFOLLOW` open. Where the operator's configured artifact root
    itself is a link, that is their configuration and not an escape.
    """
    # Refused before anything is created: a `runs` link that already points
    # somewhere would otherwise be followed by the very mkdir that makes the
    # directory, and the first run would land in the target before any
    # descriptor was opened to notice.
    if is_link(runs_dir):
        raise StateError(f"{runs_dir} is a link, not the runs directory")
    if create:
        runs_dir.mkdir(parents=True, exist_ok=True)
    if not _BINDS_TO_DIRECTORY:
        yield None
        return
    try:
        descriptor = os.open(runs_dir, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW)
    except OSError as error:
        raise StateError(f"cannot open {runs_dir}: {error}") from error
    try:
        yield descriptor
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _run_directory(run_dir: Path, runs: int | None = None):
    """Hold the run directory open and yield its descriptor, or `None` where
    the platform cannot bind operations to one.

    Checking that a path is not a link and then opening what is inside it
    are two steps, and between them the directory can be replaced — after
    which the read, and the next write, land wherever the replacement
    points. Opening the directory once and naming the state file relative
    to that descriptor collapses the two steps into one: `O_NOFOLLOW`
    refuses a symlink at the open itself, and everything that follows is
    bound to the directory that was opened, not to a path that can be
    re-pointed underneath it.
    """
    if not _BINDS_TO_DIRECTORY:
        # Where the platform cannot bind, the checks are what there is — and
        # they have to happen here rather than at the callers, since `save`
        # would otherwise follow a linked run directory and replace a state
        # file outside the run root, which is the containment `O_NOFOLLOW`
        # provides on every other platform. Both levels, for the reason the
        # bound path acquires both: a link at `runs` leaves the child inside
        # its target an ordinary directory, so checking the run alone sees
        # nothing wrong and the write still lands outside the root.
        with _runs_directory(run_dir.parent):
            if is_link(run_dir):
                raise StateError(f"{run_dir} is a link, not a run directory")
            yield None
        return
    if runs is None:
        # No descriptor from the caller means the parent is a path again,
        # and `O_NOFOLLOW` on the run directory cannot see past it: with
        # `runs` replaced by a link, the child it reaches is an ordinary
        # directory inside the target and the open succeeds. A save after
        # `open_run` has returned — the only way a caller holds a run
        # directory and no descriptor — would write there. So the parent is
        # bound here too, and the run named relative to it.
        with _runs_directory(run_dir.parent) as parent:
            with _run_directory(run_dir, parent) as descriptor:
                yield descriptor
        return
    # Named relative to the runs descriptor, never by path: the parent is as
    # re-pointable as the child was, so the whole way down from the artifact
    # root is bound rather than resolved again.
    descriptor = os.open(
        run_dir.name, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=runs
    )
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def is_link(path: Path) -> bool:
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


def open_run(runs_dir: Path, run_id: str) -> tuple[Path, RunState]:
    """Resolve a run by id under `{artifacts}/runs/` and load its state.

    Three things hold the run to the directory the caller named. Neither the
    runs directory nor the run's own may be a link: `status` refuses to list
    one for the reason that bites here — following either would read, and
    later write, a run outside the artifact root the id was validated
    against — and the runs descriptor is what the run's open is named
    against, so the whole path down from the root is bound rather than
    resolved twice. And the state must name this run: a copied or corrupt
    document declaring another id would be reported and resumed as that run
    while every path it resolves stayed under this directory, which is the
    identity §8.1 gives each run.
    """
    # The same guard creation applies, and for the same reason: the id joins
    # under the runs directory, so `../other` would leave it before any link
    # check or bound descriptor could have an opinion. The command surface
    # validates its own argument, but containment cannot rest on the caller
    # being that one.
    if not _is_run_id(run_id):
        raise StateError(f"not a run id: {run_id!r}")
    run_dir = runs_dir / run_id
    with _runs_directory(runs_dir) as runs:
        if is_link(run_dir):
            raise StateError(f"{run_dir} is a link, not a run directory")
        state = load(run_dir, runs)
    if state.run_id != run_id:
        raise StateError(
            f"{run_dir / STATE_FILE} names run {state.run_id!r}, not {run_id!r}"
        )
    return run_dir, state


def load(run_dir: Path, runs: int | None = None) -> RunState:
    path = run_dir / STATE_FILE
    if is_link(path):
        raise StateError(f"{path} is a link, not this run's state file")
    try:
        # Both components refuse a link: the directory at its own open, the
        # state file at this one. The state file is the single document this
        # module owns, and a link in either place would hand that ownership
        # to a file outside the run.
        with _run_directory(run_dir, runs) as directory:
            target = STATE_FILE if directory is not None else os.fspath(path)
            # `O_NOFOLLOW` says the name is not a link and nothing about what
            # kind of file it is. A FIFO in the state file's place would
            # block this open until something wrote to the other end — a
            # resume that hangs rather than reporting, which is worse than
            # any refusal — so the open is non-blocking where the platform
            # has it and the descriptor is checked before it is read.
            descriptor = os.open(
                target, os.O_RDONLY | _NOFOLLOW | _NONBLOCK, dir_fd=directory
            )
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise StateError(f"{path} is not a regular file")
                text = stream.read()
    # An undecodable state file is a defect in the document, and its
    # UnicodeDecodeError is a ValueError rather than an OSError — uncaught,
    # it would escape the driver as a traceback rather than as the state
    # error every other malformation is reported as.
    except (OSError, UnicodeError) as error:
        raise StateError(f"cannot read {path}: {error}") from error
    try:
        data = loads(text)
    except ProtocolYamlError as error:
        raise StateError(f"{path}: {error}") from error
    return _validate(data, path)


def save(state: RunState, run_dir: Path, runs: int | None = None) -> None:
    """One atomic write: temp sibling, then replace. The temp file lands in
    the run directory so the replace never crosses a filesystem boundary."""
    document: dict[str, object] = {"run": _run_mapping(state)}
    document["steps"] = [_step_mapping(step) for step in state.steps]
    document["gates"] = [_gate_mapping(gate) for gate in state.gates]
    if state.has_instrumentation:
        document["instrumentation"] = state.instrumentation
    document["artifacts"] = list(state.artifacts)
    if state.imports is not None:
        document["imports"] = [
            {"artifact": record.artifact, "from": record.from_run, "at": record.at}
            for record in state.imports
        ]
    text = dumps(document)
    with _run_directory(run_dir, runs) as directory:
        if directory is None:
            handle, temp_name = tempfile.mkstemp(
                prefix=f".{STATE_FILE}.", dir=run_dir, text=False
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(text)
                os.replace(temp_name, run_dir / STATE_FILE)
            except BaseException:
                os.unlink(temp_name)
                raise
            return
        # The same write, bound to the directory this run already holds
        # open: the temp file is created in it, and the rename that
        # publishes it names both sides relative to it, so no part of the
        # write can be re-pointed by a swap of the path. On POSIX `rename`
        # is the atomic overwrite `replace` exists to give Windows.
        temp_name = f".{STATE_FILE}.{os.getpid()}.{os.urandom(4).hex()}"
        handle = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.rename(
                temp_name, STATE_FILE, src_dir_fd=directory, dst_dir_fd=directory
            )
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name, dir_fd=directory)
            raise


def start_step(state: RunState, workflow: Workflow, step_id: str) -> StepRecord:
    """Mark one record `active`. At most one may be (§10) — a second active
    record would make §8.5's resume ambiguous.

    Only a declared step starts, and only from a status a start means
    something in. `steps` holds gates too (§10), and a gate has no role and
    no output to produce: marking one `active` would have to be undone by a
    completion that refuses it, after the state was already written. The
    startable statuses are `pending` and `active` — the second because a
    resume returns to the record that was running and starts it again —
    while `done`, `skipped`, and `blocked` each mean something a start
    would erase: work finished, a route that has not fired, a gate waiting
    on its outcome.
    """
    if workflow.step(step_id) is None:
        raise StateError(f"{step_id!r} is not a declared step (spec §9.1)")
    for step in state.steps:
        if step.status == "active" and step.id != step_id:
            raise StateError(
                f"step {step.id!r} is already active — a run has at most one"
            )
    record = state.record(step_id)
    if record.status not in ("pending", "active"):
        raise StateError(
            f"step {step_id!r} is {record.status}, and a step starts from pending"
        )
    record.status = "active"
    return record


def complete_step(state: RunState, workflow: Workflow, step_id: str) -> None:
    """Mark a record `done` and manifest its declared output (§8.2), `{N}`
    resolved from `run.phase` or 1 (§8.1). The manifest only grows."""
    record = state.record(step_id)
    if record.status != "active":
        raise StateError(f"step {step_id!r} is not active")
    # The declaration is resolved before anything is written: completing is
    # defined as manifesting the declared output, so an id the composition
    # declares no step for — a gate's record, which its outcome closes (§7),
    # or a record naming nothing at all — has no completion to perform, and
    # marking it `done` regardless would retire it from resume while leaving
    # the manifest silently short of what §8.2 says a finished step produced.
    declaration = workflow.step(step_id)
    if declaration is None:
        raise StateError(f"{step_id!r} is not a declared step (spec §9.1)")
    record.status = "done"
    artifact = declaration.output_artifact.replace(
        "{N}", str(state.phase if state.phase is not None else 1)
    )
    if artifact not in state.artifacts:
        state.artifacts.append(artifact)


def check_records(state: RunState, workflow: Workflow) -> None:
    """§10: the populated list follows the composed stages' sequences, which
    is what makes §8.5's resume mean what the stages declared.

    The schema cannot constrain id order, so a swapped pair changes where a
    resume lands with nothing to say it did — and an id no stage declares is
    a record nothing wrote. `run.risk` says which part of the composition a
    document owes: absent, §10's list is the entry stage's alone, since the
    acceptance is the write that creates the rest; present, the list is
    complete and owes every member of every composed stage. The conformance
    suite holds every shipped document to exactly this.
    """
    order, entry_count = workflow.sequence()
    accepted = state.risk is not None
    if not accepted:
        order = order[:entry_count]
    position = 0
    for record in state.steps:
        if record.id not in order:
            raise StateError(
                f"step {record.id!r} is not a member "
                + (
                    "any composed stage declares"
                    if accepted
                    else "the entry stage declares, and no class is accepted yet"
                )
                + " (spec §9.4)"
            )
        index = order.index(record.id)
        if index < position:
            raise StateError(
                f"step {record.id!r} is recorded after {order[position - 1]!r} and "
                f"the composed sequences declare it before (spec §10)"
            )
        position = index + 1
    # §10 gives the two working statuses to different kinds: `active` is the
    # record of the step currently running, and `blocked` is a gate waiting
    # on its outcome. A step marked `blocked` or a gate marked `active` is a
    # position neither path can advance — `start_step` refuses a record the
    # composition declares no step for, and the gate handler will not find a
    # decision to make on a step — so a resume would land there and stop.
    for record in state.steps:
        kind = workflow.member_kind(record.id)
        if record.status == "blocked" and kind != "gate":
            raise StateError(
                f"step {record.id!r} is blocked, and `blocked` is a gate waiting "
                f"on its outcome (spec §7, §10)"
            )
        if record.status == "active" and kind != "step":
            raise StateError(
                f"gate {record.id!r} is active, and `active` is the step currently "
                f"running (spec §10)"
            )
    if accepted:
        recorded = {record.id for record in state.steps}
        missing = [member for member in order if member not in recorded]
        if missing:
            raise StateError(
                f"the accepted class makes the list complete (spec §10) and these "
                f"members have no record: {', '.join(missing)}"
            )


def check_gates(state: RunState, workflow: Workflow) -> None:
    """§5.3, §7, §10: a gate's decision is recorded in `gates`, and its own
    `steps` entry is `done` only once that decision stands.

    `gates` is appended in decision order, so the last entry naming a gate
    is its latest — and it is that entry which has to stand, never the best
    one on file, or a stale accept would vouch for a gate whose newest
    decision was a revise. Only `done` is checked: `blocked` is a gate still
    waiting, `pending` one not yet reached, `skipped` one that never decided
    anything. A gate a phase repeats decides once per phase, so its standing
    decision is the one taken at the phase now executing.

    The `phase` field is checked in both directions §10 states it: a gate a
    phase repeats names the phase its decision was taken in, and a gate that
    decides once per run records none. The second holds of every entry rather
    than only the standing one — a superseded decision carries the field it
    was never entitled to just as plainly — and it holds whatever the run
    carries, since which kind a gate is comes from its stage's contracts and
    no re-cut of the phase list changes them.
    """
    scopes = workflow.gate_scopes()
    for decision in state.gates:
        if decision.phase is not None and scopes.get(decision.gate, True) is False:
            raise StateError(
                f"gate {decision.gate!r} records phase {decision.phase} and its "
                f"stage writes no per-phase output, so it decides once per run "
                f"and records no phase (spec §10)"
            )
    latest: dict[str, GateRecord] = {record.gate: record for record in state.gates}
    for record in state.steps:
        if record.status != "done" or record.id not in scopes:
            continue
        decision = latest.get(record.id)
        if decision is None:
            raise StateError(
                f"gate {record.id!r} is done and no `gates` entry records its "
                f"outcome (spec §7)"
            )
        if state.phase is not None and scopes[record.id] and decision.phase != state.phase:
            says = f"phase {decision.phase}" if decision.phase is not None else "no phase"
            raise StateError(
                f"gate {record.id!r} is done at phase {state.phase} and its latest "
                f"decision records {says} (spec §10)"
            )
        if decision.outcome not in ("accept", "reject"):
            raise StateError(
                f"gate {record.id!r} is done and its latest outcome is "
                f"{decision.outcome!r} — a revise returns the gate to `pending`, "
                f"so only an accept or a reject stands (spec §7)"
            )


def check_manifest(state: RunState, workflow: Workflow) -> None:
    """§8.2: the manifest lists what the run produced, so a `done` step's
    `{N}`-resolved output belongs in it.

    Routing already refuses to act on a done record the manifest does not
    account for, and reporting a run finished is the other place the same
    document is trusted: a manifest truncated or edited by hand would make
    `resume` answer "nothing left to run" for a run the conformance suite
    rejects. Only the phase now executing is checked, which is the scope the
    suite checks in — what an earlier phase owes cannot be read from this
    document.
    """
    phase = str(state.phase if state.phase is not None else 1)
    manifest = set(state.artifacts)
    for record in state.steps:
        if record.status != "done":
            continue
        declaration = workflow.step(record.id)
        if declaration is None:
            continue  # a gate, or a record no step declares
        produced = declaration.output_artifact.replace("{N}", phase)
        if produced not in manifest:
            raise StateError(
                f"step {record.id!r} is done and {produced!r} is not in the "
                f"manifest (spec §8.2)"
            )


def route_verdict(state: RunState, workflow: Workflow, step_id: str, verdict: str) -> str:
    """The target the producing step's `on` declares for `verdict` (§9.1),
    resolved to a member id: a stage id stands for that stage's first
    non-`skipped` step. No edge means escalate — never guess. Routing to a
    record re-enters it: the destination returns to `pending` (a `skipped`
    conditional included, §10) for the resume to find."""
    declaration = workflow.step(step_id)
    if declaration is None:
        raise StateError(f"no declaration for step {step_id!r}")
    # §9.1: the verdict that routes a step is produced by the validation of
    # that step's output, so the step has produced one — a record still
    # `pending`, `active`, or `skipped` has not, and routing from it would
    # re-enter the destination on the strength of work that has not
    # happened. Starting and completing both check their own status; this
    # is the third transition, and it was the one taking a caller's word.
    source = state.record(step_id)
    if source.status != "done":
        raise StateError(
            f"step {step_id!r} is {source.status}, and a verdict routes from a "
            f"step that has produced its output (spec §9.1)"
        )
    # `done` is a status, and §8.2 makes the manifest the record of what was
    # produced — the conformance suite holds every shipped document to
    # exactly this, a done step's `{N}`-resolved output listed in
    # `artifacts`. `complete_step` writes both together, so state this
    # driver wrote always agrees; state it merely loaded may not, and
    # routing from a done record with nothing manifested would re-enter the
    # destination on an output no document says exists. `{N}` resolves from
    # the phase now executing, which is the scope the suite checks too:
    # what an earlier phase owes cannot be read from this document.
    produced = declaration.output_artifact.replace(
        "{N}", str(state.phase if state.phase is not None else 1)
    )
    if produced not in state.artifacts:
        raise StateError(
            f"step {step_id!r} is done and {produced!r} is not in the manifest "
            f"(spec §8.2)"
        )
    target = declaration.edges.get(verdict)
    if target is None:
        raise StateError(
            f"step {step_id!r} has no edge for verdict {verdict!r} — "
            f"escalate rather than guess (spec §9.1)"
        )
    resolved = _resolve_target(state, workflow, target)
    destination = state.record(resolved)
    # A `skipped` destination re-enters, which is §9.4's rule for a
    # conditional member — "populated `skipped` until a route returns to
    # it". The overlays state the opposite for the other kind of skip:
    # "an edge or stage id targeting skipped content resolves to the next
    # non-skipped point in composition order". Both are shipped rules, they
    # disagree about a conditional target, and run state records no reason
    # to tell the two kinds apart — so whichever this driver implements is
    # wrong for the other. It re-enters here and passes over in
    # `_resolve_target`, matching each rule where that rule is written, and
    # the disagreement is recorded rather than silently settled.
    if destination.status in ("skipped", "done", "blocked"):
        destination.status = "pending"
    # §7: a step run again "invalidates what its output fed: the validator
    # that must re-check it, the gate that must decide again" — and what
    # that is "differs by route and MUST be read from the stage rather than
    # assumed", because "resetting a fixed shape would both miss a dependent
    # and run a step the overlay excludes". Only `done` records move, so a
    # validator the class skipped "stays `skipped` and is not resurrected by
    # a rule expecting it", and a `blocked` gate is a decision still open
    # rather than one this write undoes.
    for step_id in _invalidated_by(state, workflow, resolved):
        record = next((step for step in state.steps if step.id == step_id), None)
        if record is not None and record.status == "done":
            record.status = "pending"
    return resolved


def _invalidated_by(state: RunState, workflow: Workflow, destination: str) -> set[str]:
    """What a re-entry into `destination` invalidates, read from the stage.

    A step is invalidated where it declares the re-entered output among its
    inputs — the validator that must re-check it, the classifier that read
    it — and then whatever consumed *that* step's output in turn, since a
    dependent's output is as stale as what it was computed from. Intake is
    §7's own illustration: re-entering `brief-confirm` invalidates
    `risk-route`, which is no validator but did read the brief.

    A gate declares no inputs and is invalidated by position within its own
    stage, being "the gate that must decide again" about the artifact its
    stage just changed.

    `{N}` and `{P}` both stand for a phase in these paths, so both normalize
    to one token before the comparison: a step reading `{P}` of an artifact
    family depends on the phase being rewritten as surely as one reading
    `{N}` does.
    """
    produced: dict[str, str] = {}
    consumers: dict[str, set[str]] = {}
    for stage in workflow.stages:
        for step_id, declaration in stage.steps.items():
            produced[step_id] = _phase_free(declaration.output_artifact)
            for declared_input in declaration.inputs:
                consumers.setdefault(_phase_free(declared_input.artifact), set()).add(
                    step_id
                )
    # §10 bounds the set as well as §7 deriving it: "its destination MUST
    # precede every record it invalidates". Without that bound the walk runs
    # backwards through the declarations — the planning stage's `plan-revise`
    # both reads and rewrites the plan, so re-entering it reached
    # `plan-create`, which produced the plan before it and sits ahead of it
    # in the record order, and a resume would then have picked `plan-create`
    # over the destination the edge named. Only what ran after the
    # destination can be what its output fed, and only a `done` record ran
    # at all — the two together are what "what actually ran on the
    # artifact" means once the order is read as well as the declarations.
    order = [step.id for step in state.steps]
    after = set(order[order.index(destination) + 1 :]) if destination in order else set()
    ran = {step.id for step in state.steps if step.status == "done"}
    invalidated: set[str] = set()
    pending = [destination]
    while pending:
        artifact = produced.get(pending.pop())
        if artifact is None:
            continue
        for consumer in sorted(consumers.get(artifact, ())):
            if consumer in after and consumer in ran and consumer not in invalidated:
                invalidated.add(consumer)
                pending.append(consumer)
    for stage in workflow.stages:
        ids = [member.id for member in stage.members]
        if destination not in ids:
            continue
        for member in stage.members[ids.index(destination) + 1 :]:
            if member.kind == "gate" and member.id in after:
                invalidated.add(member.id)
    return invalidated


def _phase_free(artifact: str) -> str:
    return artifact.replace("{N}", "{phase}").replace("{P}", "{phase}")


def _resolve_target(state: RunState, workflow: Workflow, target: str) -> str:
    for index, stage in enumerate(workflow.stages):
        if stage.name == target:
            # §9.1: a stage id stands for that stage's first *step*, past the
            # content the run's class skips. Gates are members of the same
            # sequence and are not what a stage target names — routing to one
            # would stop the run at a decision nothing has yet produced work
            # for, where the rule sends it to the work itself.
            #
            # Every `skipped` record is passed over, which is wider than the
            # rule's words: a class exclusion, a conditional whose route has
            # not fired, and a step whose output the run imported (§8.6) all
            # wear that one status, and run state records no reason to tell
            # them apart. Nothing shipped reaches the difference — the only
            # stage-id targets declared today enter `planning`, whose first
            # member is unconditional — but a stage whose first step is
            # conditional would be entered past it. Narrowing this needs the
            # protocol to carry why a record was skipped; until it does,
            # reading all three alike is the only reading available.
            # Resolution continues past the stage where the stage itself is
            # skipped whole: the overlays say "an edge or stage id targeting
            # skipped content resolves to the next non-skipped point in
            # composition order", and composition order does not stop at a
            # stage boundary — a class that skips ideation entirely leaves
            # an edge naming it pointing at the stage that follows, not at
            # nothing.
            for later in workflow.stages[index:]:
                for member in later.members:
                    if member.kind != "step":
                        continue
                    record = next(
                        (step for step in state.steps if step.id == member.id), None
                    )
                    if record is not None and record.status != "skipped":
                        return member.id
            raise StateError(
                f"stage {target!r} resolves to no runnable step, here or after "
                f"it (spec §9.1, overlays' skip resolution)"
            )
    state.record(target)  # raises if the id names nothing
    return target


def _run_mapping(state: RunState) -> dict[str, object]:
    run: dict[str, object] = {"id": state.run_id, "workflow": state.workflow}
    if state.phase is not None:
        run["phase"] = state.phase
    if state.risk is not None:
        run["risk"] = state.risk
    if state.risk_rationale is not None:
        run["risk_rationale"] = state.risk_rationale
    run["protocol"] = state.protocol
    return run


def _step_mapping(step: StepRecord) -> dict[str, object]:
    mapping: dict[str, object] = {"id": step.id, "status": step.status}
    if step.iterations is not None:
        mapping["iterations"] = step.iterations
    if step.stall_flags is not None:
        mapping["stall_flags"] = list(step.stall_flags)
    return mapping


def _gate_mapping(gate: GateRecord) -> dict[str, object]:
    mapping: dict[str, object] = {"gate": gate.gate}
    if gate.phase is not None:
        mapping["phase"] = gate.phase
    mapping["transport"] = gate.transport
    mapping["outcome"] = gate.outcome
    mapping["at"] = gate.at
    return mapping


def _is_timestamp(value: object) -> bool:
    """An RFC 3339 date-time, which is what the run-state schema declares
    every `at` to be and what the conformance suite asserts with its
    format checker — offset included, since a timestamp without one names
    a different instant to every reader that resolves it. Accepted as a
    bare non-empty string, `not-a-timestamp` would load and `save` would
    write it back, making the driver the author of state the suite it
    ships beside rejects."""
    match = RFC3339.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return False
    year, month, day, hour, minute, second = (
        int(part) for part in match.group(1, 2, 3, 4, 5, 6)
    )
    # The shape is the pattern's; whether the date exists is the calendar's,
    # and February 30th passes any regex written for it. Second 60 is RFC
    # 3339's leap second and is refused here all the same: the format
    # assertion behind the schema — `rfc3339-validator`, which the
    # conformance suite fails loudly without — rejects every `:60`, boundary
    # or not, so accepting one would put state the driver wrote outside what
    # the suite it ships beside will validate. Agreement with the checker
    # that guards the fixtures is what this function is for.
    if hour > 23 or minute > 59 or second > 59:
        return False
    # An offset is two numbers, not four digits: `+99:99` is the shape and
    # not the thing, and it names no zone any reader can resolve.
    offset_hour, offset_minute = match.group(7, 8)
    if offset_hour is not None and (int(offset_hour) > 23 or int(offset_minute) > 59):
        return False
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def _is_count(value: object, minimum: int) -> bool:
    """An integer the schema would accept. `bool` subclasses `int` in Python
    and is a separate type in JSON Schema, so the exclusion is what keeps
    `phase: true` from loading as phase 1 and resolving a `{N}` path to
    `True` — a wrong artifact from a document the schema rejects."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _validate(data: object, path: Path) -> RunState:
    def bad(message: str) -> StateError:
        return StateError(f"{path}: {message}")

    if not isinstance(data, dict):
        raise bad("not a mapping")
    unknown = sorted(
        set(data) - {"run", "steps", "gates", "instrumentation", "artifacts", "imports"}
    )
    if unknown:
        raise bad(f"unknown keys: {', '.join(unknown)}")
    for key in ("run", "steps", "gates", "artifacts"):
        if key not in data:
            raise bad(f"missing {key!r}")

    run = data["run"]
    if not isinstance(run, dict):
        raise bad("run is not a mapping")
    unknown = sorted(
        set(run) - {"id", "workflow", "phase", "risk", "risk_rationale", "protocol"}
    )
    if unknown:
        raise bad(f"run has unknown keys: {', '.join(unknown)}")
    run_id = run.get("id")
    if not _is_run_id(run_id):
        raise bad(f"run.id is not a plain directory name: {run_id!r}")
    workflow = run.get("workflow")
    if not isinstance(workflow, str) or not workflow:
        raise bad("run.workflow is missing")
    protocol = run.get("protocol")
    if not isinstance(protocol, str) or not PROTOCOL_VERSION.fullmatch(protocol):
        raise bad(f"run.protocol is not <major>.<minor>: {protocol!r}")
    # The same §11 rule the declarations are held to: a run recorded under a
    # version this driver does not implement is state whose statuses, edges,
    # and record order it would be guessing at, and resuming such a run is
    # the silent interpretation §11 forbids.
    if not implements(protocol):
        raise bad(
            f"run.protocol is {protocol}, and this driver implements {PROTOCOL} "
            f"(spec §11)"
        )
    # Every optional field below is read by the key's presence, not by its
    # value. The schema admits none of them as null, and this module writes
    # back what it loads: read as absence, `phase: null` would be dropped by
    # the next save and the document would come out valid — malformed state
    # laundered into well-formed state by a round trip through the driver,
    # with nothing anywhere saying it happened.
    phase = run.get("phase")
    if "phase" in run and not _is_count(phase, 1):
        raise bad(f"run.phase is not a positive integer: {phase!r}")
    risk = run.get("risk")
    rationale = run.get("risk_rationale")
    if ("risk" in run) != ("risk_rationale" in run):
        raise bad("run.risk and run.risk_rationale move together (spec §10)")
    if "risk" in run and risk not in RISKS:
        raise bad(f"run.risk is not one of {'/'.join(RISKS)}: {risk!r}")
    if "risk_rationale" in run and (not isinstance(rationale, str) or not rationale):
        raise bad(f"run.risk_rationale is empty: {rationale!r}")

    steps_data = data["steps"]
    if not isinstance(steps_data, list):
        raise bad("steps is not a list")
    steps: list[StepRecord] = []
    active = 0
    for entry in steps_data:
        steps.append(_validate_step(entry, bad))
        active += steps[-1].status == "active"
    if active > 1:
        raise bad("more than one active record (spec §10)")
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            raise bad(f"step {step.id!r} has more than one record (spec §10)")
        seen.add(step.id)

    gates_data = data["gates"]
    if not isinstance(gates_data, list):
        raise bad("gates is not a list")
    gates = [_validate_gate(entry, bad) for entry in gates_data]

    artifacts_data = data["artifacts"]
    if not isinstance(artifacts_data, list) or not all(
        isinstance(x, str) and x for x in artifacts_data
    ):
        raise bad("artifacts is not a list of paths")

    # §10's enrichment is a mapping or null, and this module is the one
    # writer of the file: a string or a list accepted here is a string or a
    # list `save` writes back, so the driver would be the source of the
    # schema-invalid state rather than merely the reader of it.
    instrumentation = data.get("instrumentation")
    if "instrumentation" in data and not isinstance(instrumentation, (dict, type(None))):
        raise bad(f"instrumentation is not a mapping: {instrumentation!r}")

    imports = _validate_imports(data, run_id, set(artifacts_data), bad)

    return RunState(
        run_id=run_id,
        workflow=workflow,
        protocol=protocol,
        steps=steps,
        gates=gates,
        artifacts=list(artifacts_data),
        imports=imports,
        phase=phase,
        risk=risk,
        risk_rationale=rationale,
        instrumentation=data.get("instrumentation"),
        has_instrumentation="instrumentation" in data,
    )


def _validate_imports(
    data: dict, run_id: str, manifest: set[str], bad
) -> list[ImportRecord] | None:
    """The §8.6 lineage, held to the schema's essentials: one mapping per
    copy with `artifact`, `from`, and `at`, every path manifested, the
    source a plain name that is not this run. Deeper §8.6 semantics — the
    derivation closure, canonical directory identity — belong to the import
    materialization that a later module performs."""
    if "imports" not in data:
        return None
    entries = data["imports"]
    if not isinstance(entries, list) or not entries:
        raise bad("imports must be a non-empty list when present (spec §10)")
    records: list[ImportRecord] = []
    # §8.6 and §10 both bound the list, and the conformance suite holds the
    # shipped documents to each: one record per imported artifact, since a
    # second gives that artifact two lineages and no single source to read,
    # and one source run for the whole list, since artifacts from several
    # never descended from one another. Accepted here, either would be
    # written back by the next save as validated lineage.
    seen: set[str] = set()
    sources: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or sorted(entry) != ["artifact", "at", "from"]:
            raise bad(f"import record must carry artifact, from, at: {entry!r}")
        artifact, source, at = entry["artifact"], entry["from"], entry["at"]
        if not isinstance(artifact, str) or not IMPORT_PATH.match(artifact):
            raise bad(f"import artifact is not a {{run}}-relative path: {artifact!r}")
        if artifact not in manifest:
            raise bad(f"import {artifact!r} is not in the manifest (spec §8.6)")
        if not isinstance(source, str) or not PLAIN_NAME.match(source):
            raise bad(f"import source is not a plain run id: {source!r}")
        if source == run_id:
            raise bad(f"import {artifact!r} names this run as its source (spec §8.6)")
        if not _is_timestamp(at):
            raise bad(f"import {artifact!r} without an RFC 3339 timestamp: {at!r}")
        if artifact in seen:
            raise bad(f"import {artifact!r} has more than one record (spec §10)")
        seen.add(artifact)
        sources.add(source)
        if len(sources) > 1:
            raise bad(
                f"imports name {len(sources)} source runs "
                f"({', '.join(sorted(sources))}) — a run imports from one (spec §8.6)"
            )
        records.append(ImportRecord(artifact=artifact, from_run=source, at=at))
    return records


def _validate_step(entry: object, bad) -> StepRecord:
    if not isinstance(entry, dict):
        raise bad(f"step record is not a mapping: {entry!r}")
    unknown = sorted(set(entry) - {"id", "status", "iterations", "stall_flags"})
    if unknown:
        raise bad(f"step record has unknown keys: {', '.join(unknown)}")
    step_id = entry.get("id")
    status = entry.get("status")
    if not isinstance(step_id, str) or not step_id:
        raise bad(f"step record without an id: {entry!r}")
    if OUTPUT_BREAKING.search(step_id):
        raise bad(f"step record id carries a control character: {step_id!r}")
    if status not in STATUSES:
        raise bad(f"step {step_id!r} status is not one of {'/'.join(STATUSES)}: {status!r}")
    iterations = entry.get("iterations")
    if "iterations" in entry and not _is_count(iterations, 0):
        raise bad(f"step {step_id!r} iterations is not a count: {iterations!r}")
    stall_flags = entry.get("stall_flags")
    if "stall_flags" in entry and (
        not isinstance(stall_flags, list)
        or not all(isinstance(x, str) and x for x in stall_flags)
    ):
        raise bad(f"step {step_id!r} stall_flags is not a list of signals")
    return StepRecord(
        id=step_id, status=status, iterations=iterations, stall_flags=stall_flags
    )


def _validate_gate(entry: object, bad) -> GateRecord:
    if not isinstance(entry, dict):
        raise bad(f"gate record is not a mapping: {entry!r}")
    unknown = sorted(set(entry) - {"gate", "phase", "transport", "outcome", "at"})
    if unknown:
        raise bad(f"gate record has unknown keys: {', '.join(unknown)}")
    gate = entry.get("gate")
    if not isinstance(gate, str) or not gate:
        raise bad(f"gate record without a gate id: {entry!r}")
    if OUTPUT_BREAKING.search(gate):
        raise bad(f"gate record id carries a control character: {gate!r}")
    transport = entry.get("transport")
    if transport not in TRANSPORTS:
        raise bad(f"gate {gate!r} transport is not one of {'/'.join(TRANSPORTS)}")
    outcome = entry.get("outcome")
    if outcome not in OUTCOMES:
        raise bad(f"gate {gate!r} outcome is not one of {'/'.join(OUTCOMES)}")
    at = entry.get("at")
    if not _is_timestamp(at):
        raise bad(f"gate {gate!r} without an RFC 3339 timestamp: {at!r}")
    phase = entry.get("phase")
    if "phase" in entry and not _is_count(phase, 1):
        raise bad(f"gate {gate!r} phase is not a positive integer: {phase!r}")
    return GateRecord(gate=gate, transport=transport, outcome=outcome, at=at, phase=phase)
