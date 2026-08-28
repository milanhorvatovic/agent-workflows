"""Run state: the one document the executor maintains (protocol/spec.md §10).

This module owns every read and write of `{run}/workflow-state.yaml` — the
single-writer rule is enforced by shape: nothing else in the driver touches
the file, and every mutation lands through `save`, which writes a sibling
temp file and replaces atomically, so a crash leaves the previous state
rather than half of the next one. Where the platform syncs a directory,
that holds through a power loss as well: the bytes reach the device, then
the rename publishes them, then the entry naming it is persisted. Where it
does not — Windows, through this library — the write is atomic and the
file's own bytes are synced, and when the entry follows is the
filesystem's to decide.

Creation writes one thing besides: `{run}/request.md`, what the run was
created from (§8.7). It is the one artifact no step produces — nothing
precedes the first step to write it — so it lands here, ahead of the state
that manifests it, rather than through an executor step that cannot exist.

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
import errno
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import (
    PROTOCOL,
    PROTOCOL_VERSION,
    REQUEST_ARTIFACT,
    REQUEST_FILE,
    implements,
    names_request,
)
from .protocol_yaml import ProtocolYamlError, dumps, loads
from .workflow import PHASE, PHASE_SET, RUN_RELATIVE, Workflow, family

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
# The `{run}`-relative import path (§8.6) is the same shape a declared
# artifact takes, and `workflow` owns it: what a contract may name and
# what a lineage record may name are one rule, pinned there against the
# schema's own pattern.
IMPORT_PATH = RUN_RELATIVE
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
    runs_dir: Path, run_id: str, workflow: Workflow, protocol: str, request: str
) -> tuple[Path, RunState]:
    """Create `{artifacts}/runs/<run-id>/`, the request it was created with
    (§8.7), and its bootstrap state: the entry stage's records alone,
    conditional members `skipped`, the rest `pending` (§10). The directory
    MUST NOT pre-exist — concurrent runs and re-runs never share one (§8.1).

    An empty request is refused rather than written. §8.7 has every run hold
    one and the entry step declare it required, so a run created around a file
    with nothing in it is a run whose first step has nothing to restate — the
    same dead run that not writing the file at all would leave, and worth no
    more than the id it would spend.
    """
    if not _is_run_id(run_id):
        raise StateError(f"not a run id: {run_id!r}")
    if not request.strip():
        raise StateError("the request is empty — a run is created from one (spec §8.7)")
    # A request that UTF-8 cannot carry, refused here rather than at the write.
    # POSIX decodes argv with `surrogateescape`, so a byte no encoding claims
    # reaches `--request` as a lone surrogate: it clears the emptiness check,
    # and `_write_request` then raises `UnicodeEncodeError` — a `ValueError`,
    # which the command surface does not catch, so the run leaves as a
    # traceback rather than an exit code. The run-id guard refuses surrogates
    # for this reason already; a request is the other string a caller hands in.
    try:
        request.encode("utf-8")
    except UnicodeEncodeError as error:
        raise StateError(
            f"the request is not text UTF-8 can carry: {error}"
        ) from None
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
    # Which ancestors this creation will make. The entry naming each one
    # lives in its parent, and only that parent's own sync persists it —
    # syncing `runs` alone persists the run inside it while the entry
    # naming `runs` is still nowhere on the device. Read before anything
    # is created, since afterwards they all exist.
    fresh = [path for path in (runs_dir, *runs_dir.parents) if not path.exists()]
    with _runs_directory(runs_dir, create=True) as runs:
        try:
            if runs is None:
                run_dir.mkdir()
            else:
                os.mkdir(run_id, dir_fd=runs)
        except FileExistsError:
            raise StateError(f"run {run_id!r} already exists") from None
        # Before the state that manifests it, so the manifest never names a
        # file that is not there yet — the same order §8.6 gives imports, and
        # for the same reason: the readers include the intake stage, and a
        # manifest only grows.
        try:
            _write_request(run_dir, request, runs)
        except BaseException:
            _remove_run(run_dir, runs)
            raise
        created = _bootstrap(run_dir, run_id, workflow, protocol, runs)
        # The state file's own durability says nothing about the directory
        # holding it: `_bootstrap` syncs the file and the run directory,
        # and the entry naming that run lives one level up. Unsynced, a
        # power loss takes the whole run with it — after this call has
        # already reported it made.
        #
        # These run past the bootstrap that rolls itself back, and a
        # failure here is this creation failing like any other: the
        # directory goes, so the id the call reported failure for is the
        # id a retry can use.
        try:
            if runs is None:
                _sync_directory(runs_dir)
            else:
                _sync_descriptor(runs)
            for path in fresh:
                _sync_directory(path.parent)
        except BaseException:
            _remove_run(run_dir, runs)
            raise
        return created


def _remove_run(run_dir: Path, runs: int | None) -> None:
    """Undo a creation that failed, so its id stays usable.

    The directory exists only to hold this run's own files, and §8.1 makes a
    pre-existing one a refusal — so leaving one behind would burn the id:
    the retry meets "already exists" and the run it names has no state to
    resume. Both files creation writes go with it — the request (§8.7) and
    the state — since either can be left behind by a failure after its own
    write, and a directory holding one is not empty for `rmdir` to take.
    Nothing else has written here: the directory was made moments ago by the
    call now rolling itself back, and the failure it is rolling back from is
    what propagates.
    """
    try:
        if runs is None:
            for name in (STATE_FILE, REQUEST_FILE):
                (run_dir / name).unlink(missing_ok=True)
            run_dir.rmdir()
        else:
            # Bound to the directory rather than named through it. A path
            # with a separator in it is resolved component by component
            # even from a descriptor, so `<run-id>/workflow-state.yaml`
            # would follow whatever `<run-id>` is by then — and this runs
            # while the failure that caused it is still unwinding, which is
            # a window to swap a link into that name. Opened with
            # `O_NOFOLLOW`, a link there is refused instead, and the
            # `rmdir` that follows refuses it too.
            inside = os.open(
                run_dir.name, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=runs
            )
            try:
                for name in (STATE_FILE, REQUEST_FILE):
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(name, dir_fd=inside)
            finally:
                os.close(inside)
            os.rmdir(run_dir.name, dir_fd=runs)
    except OSError:
        pass


def _write_request(run_dir: Path, request: str, runs: int | None) -> None:
    """Write `{run}/request.md` — what the run was created from (§8.7).

    Verbatim, and as bytes. The request is what the run was given rather than
    something authored against a structure, so there is no template to scaffold
    from and nothing to normalize; text mode would translate line endings and
    hand the entry step something other than the words that started the run.

    `O_EXCL` refuses a name already taken. Nothing of this run's can be there —
    the directory was created moments ago by the call this runs inside — so
    what it stops is something planted in the window between, a link included,
    which `O_EXCL` reports as EEXIST as readily as a regular file. The file's
    own bytes are synced here; the directory entry naming it is persisted by
    the state save that follows, which fsyncs this same directory.

    One direct write rather than the temp-and-replace the state file takes,
    and the ordering is what makes that safe: nothing precedes this in a
    directory created moments ago, and the document that would name a partial
    copy is written afterwards — so a crash partway through leaves a run with
    no state at all, which nothing resumes, rather than a manifest pointing at
    half a request.
    """
    text = request.encode("utf-8")
    with run_directory(run_dir, runs) as directory:
        descriptor = os.open(
            REQUEST_FILE if directory is not None else os.fspath(run_dir / REQUEST_FILE),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
            0o666,
            dir_fd=directory,
        )
        # `fdopen` takes ownership only once it returns a stream, so a failure
        # there leaves the descriptor this function's to close.
        try:
            stream = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(text)
            _sync(stream)


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
        # The request is in the manifest from the first write (§8.2, §8.7):
        # `_write_request` has already landed it, and the entry step declares
        # it required, so a bootstrap manifest without it would block the run
        # at the step it was created to run.
        artifacts=[REQUEST_ARTIFACT],
    )
    try:
        save(state, run_dir, runs)
    except BaseException:
        _remove_run(run_dir, runs)
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
# Whether a directory can be opened and synced at all. POSIX names the
# operation; Windows has no handle for a directory's own metadata through
# this library, so the entry a rename creates is persisted when its
# filesystem gets to it and not when this module asks. What the ordering
# below gives there is the atomicity of `replace` and a file whose bytes
# are on the device — not the "previous state or the next one" a power
# loss is held to where the entry can be synced. The README states that
# per-platform, beside the containment guarantee it qualifies the same way.
#
# Decided by the platform rather than read out of an error code: an open
# that fails where the operation exists means no sync happened, which is
# the write not being durable rather than the platform declining to make
# it so.
_SYNCS_DIRECTORIES = hasattr(os, "O_DIRECTORY")
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
def run_directory(run_dir: Path, runs: int | None = None):
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
            with run_directory(run_dir, parent) as descriptor:
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
        with run_directory(run_dir, runs) as directory:
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


def _sync(stream) -> None:
    """The file's own bytes, on the device rather than in a cache.

    `replace` is atomic and says nothing about durability: after a power
    loss the rename can be on the device while the data it published is
    not, which is the half-written state the temp-and-replace exists to
    make impossible. The order — data, then rename, then the directory
    entry that names it — is what makes a crash leave the previous state
    or the next one and nothing between, wherever the third step can be
    taken; where it cannot, this first one still keeps a published name
    from pointing at bytes that never landed.
    """
    stream.flush()
    os.fsync(stream.fileno())


# What `fsync` reports when a directory is not something it applies to,
# rather than when the sync failed. The first is a platform saying it has
# no such operation — nothing was lost — and the second is a device saying
# the write did not land, which is the whole of what the ordering promises.
_UNSUPPORTED = frozenset(
    code
    for code in (
        getattr(errno, "EINVAL", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOSYS", None),
    )
    if code is not None
)


def _sync_descriptor(descriptor: int) -> None:
    """Sync it, and let a real failure through. `EIO` says the write did
    not reach the device, and swallowing it returns a save that promised
    durability and did not deliver it."""
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in _UNSUPPORTED:
            raise


def _sync_directory(path: Path) -> None:
    """The directory entry the rename created, on the device.

    Where the platform has no directory sync there is nothing to attempt
    and nothing to report. Where it has one, every failure is this write's:
    an open that fails means no sync happened at all, and a save that
    swallowed it would report the durability it did not achieve.
    """
    if not _SYNCS_DIRECTORIES:
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        _sync_descriptor(descriptor)
    finally:
        os.close(descriptor)


def save(state: RunState, run_dir: Path, runs: int | None = None) -> None:
    """One atomic write: temp sibling, synced, then replace. The temp file
    lands in the run directory so the replace never crosses a filesystem
    boundary, and the data reaches the device before the rename publishes
    it — atomic and durable, which the module docstring promises and only
    the first half of which a rename gives."""
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
    # The id is the run's identity (§8.1), and `open_run` refuses a document
    # naming a different run than the directory holding it. The write owes
    # the same: a record carried to the wrong directory publishes a file
    # its own loader then refuses, over a run that was fine until this.
    if state.run_id != run_dir.name:
        raise StateError(
            f"state names run {state.run_id!r} and the directory is "
            f"{run_dir.name!r} — the id is the run's identity (spec §8.1)"
        )
    # One writer and one round trip: what this module publishes is what it
    # can read back. The record it serializes is mutable and the handlers
    # to come hold one, so a field put wrong in memory would be written out
    # and refused at the next load — the run left holding a document its
    # own driver rejects. Read here, against the same rules `load` applies.
    _validate(document, run_dir / STATE_FILE)
    try:
        text = dumps(document)
    except (TypeError, ValueError) as error:
        # Every defect this module meets leaves it as a StateError, which
        # is what carries one to an exit code rather than a traceback. The
        # writer refuses a value the subset does not carry — `instrumentation`
        # is an open mapping to the schema and this codec reads and writes
        # what the protocol's own documents use, so the two can disagree.
        raise StateError(f"cannot write this run's state: {error}") from error
    with run_directory(run_dir, runs) as directory:
        if directory is None:
            handle, temp_name = tempfile.mkstemp(
                prefix=f".{STATE_FILE}.", dir=run_dir, text=False
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(text)
                    _sync(stream)
                os.replace(temp_name, run_dir / STATE_FILE)
                _sync_directory(run_dir)
            except BaseException:
                # The temp name is gone once the replace has run, so the
                # cleanup for a failure after it must not raise over the
                # failure it is cleaning up after.
                with contextlib.suppress(OSError):
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
                _sync(stream)
            os.rename(
                temp_name, STATE_FILE, src_dir_fd=directory, dst_dir_fd=directory
            )
            # The directory this run already holds open is the one the
            # rename published into, so the entry is synced through it
            # rather than through a second open of the same path.
            _sync_descriptor(directory)
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
    # And only where the run stands. §8.5 resolves one position, and the
    # record order §10 declares is what makes it mean anything: starting a
    # later `pending` record walks past the work between, and the
    # active-first rule then preserves that skip on every resume after it.
    # Routing keeps the two in step by the same reading — a destination
    # MUST precede every record it invalidates (§10), so what a route
    # re-enters is the position when the write that re-entered it lands.
    position = state.position()
    if position is not None and position.id != step_id:
        raise StateError(
            f"step {step_id!r} is not where the run stands — {position.id!r} is "
            f"(spec §8.5, §10)"
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
    artifact = PHASE.sub(
        str(state.phase if state.phase is not None else 1),
        declaration.output_artifact,
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
    # The list owes every member `order` holds, which `accepted` has already
    # narrowed: the whole composition once a class is accepted, the entry
    # stage's own members before that. `alone` in §10's "the list holds the
    # intake steps alone" bounds both sides — the acceptance is what creates
    # the records after them, and nothing creates the entry stage's own after
    # creation does, which is why the pre-acceptance starter fixture carries
    # the stage whole. Unchecked, an empty list resolved to no position at
    # all and a run that never reached its first step read as finished.
    recorded = {record.id for record in state.steps}
    missing = [member for member in order if member not in recorded]
    if missing:
        raise StateError(
            (
                "the accepted class makes the list complete (spec §10)"
                if accepted
                else "§10's pre-acceptance list is the entry stage's records"
            )
            + f" and these members have no record: {', '.join(missing)}"
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
        # §7 makes `gates` the record of the run's own decisions, so an
        # entry naming a gate no composed stage declares is instrumentation
        # nothing wrote — the same reading `check_records` gives a step id.
        # Every declared gate is in `scopes`, so an absent one is unknown
        # rather than unscoped, and letting it default would exempt it from
        # the phase rule every declared gate is held to.
        if decision.gate not in scopes:
            raise StateError(
                f"gate {decision.gate!r} records a decision and no composed "
                f"stage declares it (spec §7, §9.4)"
            )
        if decision.phase is not None and not scopes[decision.gate]:
            raise StateError(
                f"gate {decision.gate!r} records phase {decision.phase} and its "
                f"stage writes no per-phase output, so it decides once per run "
                f"and records no phase (spec §10)"
            )
    latest: dict[str, GateRecord] = {record.gate: record for record in state.gates}
    # §7 and §10 make the class one write with the decision that accepted
    # it: `run.risk` holds what the intake gate accepted, the gate's record
    # becomes `done`, and the list is populated, together. State is loaded
    # rather than trusted, so a document carrying the class while that gate
    # never decided has the authority of the acceptance without it — and
    # `run.risk` is what every check keyed on the post-intake shape reads,
    # `check_records` first among them. The two directions are the one rule:
    # the class stands where the acceptance does, and nowhere else.
    # A revise is the decision that did not stand — the gate decides again,
    # and in the phase the run is in. §10 has a decision taken while the run
    # carries a phase name the phase it was taken in, and the `done` check
    # below never reaches this one: a revise returns its gate to `pending`.
    # What the run carries is the test, and it is enough of one here: the
    # acceptance that sets `run.phase` is appended after any revise taken
    # before the run had phases, so a revise still standing as the latest
    # entry was taken under this phase. That is why the rule holds of a
    # revise and not of an accept, which a `pending` gate may legitimately
    # carry from the phase before this one.
    if state.phase is not None:
        for gate_id, decision in {
            record.gate: record for record in state.gates
        }.items():
            if decision.outcome != "revise" or not scopes.get(gate_id):
                continue
            if decision.phase != state.phase:
                says = (
                    f"phase {decision.phase}"
                    if decision.phase is not None
                    else "no phase"
                )
                raise StateError(
                    f"gate {gate_id!r} is to decide again at phase {state.phase} "
                    f"and its latest decision records {says} (spec §10)"
                )
    # What is checked here is the decision on file and not the gate's own
    # record, deliberately. §7 makes that record `done` while the decision
    # stands, and a re-entry unmakes exactly that without touching `gates`:
    # a route back into the stage returns the gate to `pending` for it to
    # decide again, and the accept it made before is still the latest entry
    # there, `gates` being append-only. Requiring `done` here refused the
    # state this module's own routing writes.
    # §7: where what ends is the run, "every record still `pending` or
    # `blocked` becomes `skipped` with the outcome, every one but the
    # deciding gate's own" — and a resume looks for the first record
    # neither done nor skipped, so without that write it walks into the
    # work the rejection ended.
    #
    # Read from the decision rather than from the record, since the record
    # is half of what the write owes: the deciding gate is `done`, and
    # nothing after a reject re-enters it — the run is over. A decision on
    # file over a gate still `pending`, `blocked`, or `skipped` is a
    # rejection the resume can return to and ask again.
    #
    # A phased run is no exception, though §7 does describe a write bounded
    # by the phase: ending only the phase "is sound only where nothing the
    # list places after the rejected phase depends on it, and an executor
    # that cannot establish that MUST end the run". This one reads
    # `run.phase`, a number, and never the list that states those
    # dependencies — so it is an executor that cannot establish it.
    # §7 names "an `accept` at the last gate", which is the last gate and
    # not the last member — a sequence may carry work behind its decision —
    # and the last gate of this run rather than of the composition, since
    # the accepted class may skip the one a workflow ends with.
    closing = _closing_gate(state, workflow)
    # `gates` is append-only in decision order (§10), and a decision that
    # ends the run is the end of that order: nothing decides after it.
    # Reading the latest entry per gate collapses the history, so a
    # terminal outcome with anything appended behind it was passed over
    # and the run resumed under whatever came next.
    for index, entry in enumerate(state.gates[:-1]):
        if entry.outcome == "reject" or (
            entry.outcome == "accept" and entry.gate == closing
        ):
            raise StateError(
                f"gate {entry.gate!r} records {entry.outcome!r}, which ends the "
                f"run, and {len(state.gates) - index - 1} decision(s) follow it "
                f"(spec §7, §10)"
            )
    for gate_id, decision in latest.items():
        if gate_id not in scopes:
            continue
        # §7 names two ways a run ends — "a `reject` in a workflow with no
        # phases, an `accept` at the last gate" — and gives both the same
        # write. The accept is only terminal at the gate the composition
        # ends with; anywhere else it is a run proceeding.
        terminal = decision.outcome == "reject" or (
            decision.outcome == "accept" and gate_id == closing
        )
        if not terminal:
            continue
        deciding = next((step for step in state.steps if step.id == gate_id), None)
        if decision.outcome == "reject" and (
            deciding is None or deciding.status != "done"
        ):
            stands = "no record" if deciding is None else f"status {deciding.status!r}"
            raise StateError(
                f"gate {gate_id!r} records a reject, which ends the run, and its "
                f"own entry has {stands} — the decision that ended it is `done` "
                f"(spec §7)"
            )
        # An acceptance at the last gate ends the run once it stands, and
        # its own record says whether it does: a re-entry leaves the gate
        # `pending` or `blocked`, with the run still to reach it.
        if decision.outcome == "accept" and (
            deciding is None or deciding.status != "done"
        ):
            continue
        left = [
            step.id
            for step in state.steps
            if step.id != gate_id and step.status not in ("done", "skipped")
        ]
        if left:
            raise StateError(
                f"gate {gate_id!r} records {decision.outcome!r}, which ends the "
                f"run, and these are neither done nor skipped: "
                f"{', '.join(left)} (spec §7)"
            )
    entry_gate = workflow.entry_gate()
    if entry_gate is not None:
        decision = latest.get(entry_gate)
        accepted = decision is not None and decision.outcome == "accept"
        # And the record it wrote. A re-entry is why this is not held to
        # `done` — the gate returns to `pending` to decide again, and to
        # `blocked` once it is waiting — but `skipped` is neither: nothing
        # writes it over a gate that has accepted, the terminal write of §7
        # reaching the records still pending or blocked and never the
        # deciding gate's own. A class beside one is a class no decision of
        # this run produced.
        standing = next((step for step in state.steps if step.id == entry_gate), None)
        if accepted and standing is not None and standing.status == "skipped":
            raise StateError(
                f"gate {entry_gate!r} records an accept and its own entry is "
                f"skipped — accepting writes it `done` (spec §7, §10)"
            )
        if state.risk is not None and not accepted:
            stands = (
                f"its latest decision is {decision.outcome!r}"
                if decision is not None
                else "no `gates` entry records a decision by it"
            )
            raise StateError(
                f"run state carries risk {state.risk!r} and {stands} at gate "
                f"{entry_gate!r}, which is what accepts a class (spec §7, §10)"
            )
        if accepted and state.risk is None:
            raise StateError(
                f"gate {entry_gate!r} records an accept and run state carries "
                f"no risk — the acceptance is what sets it (spec §7, §10)"
            )
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
        # A gate is a member of its stage's sequence and decides where it
        # stands: `done` with earlier work in that stage still to run is a
        # decision taken about something that had not happened. No
        # transition writes it — the gate is reached after that work, and a
        # route back into the work returns the gate to `pending` with it
        # (§7, §10) — so a document carrying it would have a resume run the
        # earlier step under a decision the same document says came after.
        for stage in workflow.stages:
            ids = [member.id for member in stage.members]
            if record.id not in ids:
                continue
            earlier = [
                step.id
                for step in state.steps
                if step.id in ids[: ids.index(record.id)]
                and step.status not in ("done", "skipped")
            ]
            if earlier:
                raise StateError(
                    f"gate {record.id!r} is done and these stand before it in "
                    f"{stage.name!r}, neither done nor skipped: "
                    f"{', '.join(earlier)} (spec §7, §10)"
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
        produced = PHASE.sub(phase, declaration.output_artifact)
        if produced not in manifest:
            raise StateError(
                f"step {record.id!r} is done and {produced!r} is not in the "
                f"manifest (spec §8.2)"
            )
    # And the other direction. §8.2 makes the manifest the record of what the
    # run produced, imported, or was given at creation, so a path that is none
    # of the three is content nothing wrote, which a later input or phase-set
    # resolution would read as an artifact the run holds. Matched against
    # the family a declaration names rather than the phase now executing: a
    # run that has passed through phases holds each phase's own artifact,
    # and every one of them is that declaration's output.
    families = [
        family(declaration.output_artifact)
        for stage in workflow.stages
        for declaration in stage.steps.values()
    ]
    for artifact in state.artifacts:
        # The request is the third category, and the one entry no step
        # declares: §8.7 has the executor land it at creation, so no `output`
        # names it and matching it against the families would report the one
        # artifact every run is obliged to hold as the one nothing wrote.
        if artifact == REQUEST_ARTIFACT:
            continue
        if not any(family.fullmatch(artifact) for family in families):
            raise StateError(
                f"{artifact!r} is in the manifest and no composed step declares "
                f"it (spec §8.2)"
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
    # that step's output, so the output exists — a record still `pending`
    # or `active` has none, and routing from it would re-enter the
    # destination on the strength of work that has not happened. Starting
    # and completing both check their own status; this is the third
    # transition, and it was the one taking a caller's word.
    #
    # `skipped` is where the two reasons part. §8.6 populates a producer
    # `skipped` where its output was imported, and §9.1 leaves the edges on
    # that same producer while the verdict comes from validating what it
    # holds: import a plan and not its validation, and the validator runs
    # on the copy — the verdict is real and the artifact is in the run.
    # What is missing is the run of a step that had nothing to produce, and
    # refusing that stops an imported plan at its first verdict. A member
    # the class or a condition skipped produced nothing at all, and still
    # routes nothing.
    source = state.record(step_id)
    if source.status not in ("done", "skipped") or (
        source.status == "skipped"
        and step_id not in _import_skipped(state, workflow)
    ):
        raise StateError(
            f"step {step_id!r} is {source.status}, and a verdict routes from a "
            f"step whose output the run holds (spec §9.1, §8.6)"
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
    # A route rewrites records for the resume to find, and §8.5 returns to
    # the active record ahead of every one of them: applied while another
    # step is running, a verdict mutates the list and changes nothing the
    # resume reads — a transition that half happened. The counterpart to
    # the single-active guard on starting a step.
    running = next((step for step in state.steps if step.status == "active"), None)
    if running is not None:
        raise StateError(
            f"step {running.id!r} is active — a verdict routes when the run is "
            f"between steps (spec §8.5, §10)"
        )
    produced = PHASE.sub(
        str(state.phase if state.phase is not None else 1),
        declaration.output_artifact,
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
    # What the walk returned, returned to `pending`: every record that ran,
    # and the derivations §8.6 skipped by import — identifying one and
    # leaving it `skipped` is a resume walking past it exactly as it would
    # have without the walk. A conditional member's own skip is untouched,
    # its condition not having fired for this write to answer.
    reset = {step.id for step in state.steps if step.status == "done"} | _import_skipped(
        state, workflow
    )
    for step_id in _invalidated_by(state, workflow, resolved):
        record = next((step for step in state.steps if step.id == step_id), None)
        if record is not None and record.id in reset:
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
    # What ran, and what stands in for having run. §8.6 populates a step
    # `skipped` where its declared output was imported, and holds that skip
    # "only while the derivation stays imported": once the artifact it was
    # derived from is re-entered, what the import holds was computed from
    # the old input, and a resume walking past it carries that forward.
    ran = {step.id for step in state.steps if step.status == "done"} | _import_skipped(
        state, workflow
    )
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
    # Every stage the walk reached, not the destination's alone: a
    # dependent's output is as stale as what it was computed from, and the
    # gate standing after that dependent decided about the version it is
    # replacing. Left `done`, it is an approval over work its approver
    # never saw, and §8.5 walks straight past it to whatever follows.
    for member_id in {destination, *invalidated}:
        for stage in workflow.stages:
            ids = [member.id for member in stage.members]
            if member_id not in ids:
                continue
            for member in stage.members[ids.index(member_id) + 1 :]:
                if member.kind == "gate" and member.id in after:
                    invalidated.add(member.id)
    return invalidated


def _closing_gate(state: RunState, workflow: Workflow) -> str | None:
    """The gate this run ends at: the last one the composition declares
    that the run's own class did not skip.

    §7 ends a run at "an `accept` at the last gate", and which gate that is
    belongs to the run rather than to the composition. The overlays leave
    R0 with "no structured steps after intake" and no `delivery-approval`
    firing, so the gate a workflow ends with is one that run never reaches
    — and read from the composition alone, such a run has no decision that
    ends it and resumes for ever with its records exhausted.
    """
    return next(
        (
            member.id
            for _, member in reversed(workflow.members())
            if member.kind == "gate"
            and next(
                (step.status for step in state.steps if step.id == member.id), None
            )
            != "skipped"
        ),
        None,
    )


def ended(state: RunState, workflow: Workflow) -> bool:
    """Whether a decision ended this run (§7).

    "Where what ends is the run — a `reject` in a workflow with no phases,
    an `accept` at the last gate" — so a run that has ended says so, and
    one whose records merely ran out has not. The difference is what a
    crash between a step's completion and the verdict that routes it looks
    like: every record done or skipped, and the transition still owed.
    """
    if not state.gates:
        return False
    closing = _closing_gate(state, workflow)
    last = state.gates[-1]
    return last.outcome == "reject" or (
        last.outcome == "accept" and last.gate == closing
    )


def _import_skipped(state: RunState, workflow: Workflow) -> set[str]:
    """Every step whose record is `skipped` because its declared output was
    imported (§8.6), told from the members a class or a condition skipped.

    A member the class or a condition left out produced nothing and derives
    from nothing; one skipped by import has an artifact in the run and a
    lineage behind it. The two wear the same status, so what tells them
    apart is the manifest of imports — matched against the artifact the
    declaration resolves to here, `{N}` taking the phase now executing as
    it does everywhere else. Not the family: at phase 2 an import of
    `{run}/phase-1-plan.md` names a file this phase has yet to write, and
    reading it as this phase's would hand any `skipped` producer of that
    family to the walk, whatever its skip was waiting for.
    """
    imports = set(record.artifact for record in (state.imports or ()))
    if not imports:
        return set()
    phase = str(state.phase if state.phase is not None else 1)
    produced: set[str] = set()
    for stage in workflow.stages:
        for step_id, declaration in stage.steps.items():
            if PHASE.sub(phase, declaration.output_artifact) in imports:
                produced.add(step_id)
    return {
        step.id
        for step in state.steps
        if step.status == "skipped" and step.id in produced
    }


def _phase_free(artifact: str) -> str:
    return PHASE_SET.sub("{phase}", PHASE.sub("{phase}", artifact))


def _resolve_target(state: RunState, workflow: Workflow, target: str) -> str:
    for index, stage in enumerate(workflow.stages):
        if stage.name == target:
            # §9.1: a stage id stands for that stage's first *step*, past the
            # content the run's class skips. Gates are members of the same
            # sequence and are not what a stage target names — routing to one
            # would stop the run at a decision nothing has yet produced work
            # for, where the rule sends it to the work itself.
            #
            # Only what the class excluded is passed over. Three things
            # wear `skipped` and run state records no reason to tell them
            # apart, but the declarations do: a conditional member is one
            # the sequence says so about, an imported derivation is one the
            # manifest of imports names, and a member that is neither was
            # left out by the class. The first two are where the stage's
            # work begins if they are first — §9.1 names the stage's first
            # step, and a route re-enters a conditional member (§10) or an
            # imported one (§8.6) rather than stepping over it.
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
                    if record is not None and (
                        record.status != "skipped"
                        or _re_enterable(state, workflow, member.id)
                    ):
                        return member.id
            raise StateError(
                f"stage {target!r} resolves to no runnable step, here or after "
                f"it (spec §9.1, overlays' skip resolution)"
            )
    record = state.record(target)  # raises if the id names nothing
    if record.status != "skipped" or _re_enterable(state, workflow, target):
        return target
    # The overlays: "an edge or stage id targeting skipped content resolves
    # to the next non-skipped point in composition order". What this
    # destination names is work the class excluded, and re-entering it
    # would resurrect what the accepted class left out — so the edge
    # resolves past it, to the next member the run still runs.
    order = [member.id for _, member in workflow.members()]
    for member_id in order[order.index(target) + 1 :]:
        later = next((step for step in state.steps if step.id == member_id), None)
        if later is not None and (
            later.status != "skipped" or _re_enterable(state, workflow, member_id)
        ):
            return member_id
    raise StateError(
        f"edge target {target!r} is skipped by the accepted class and nothing "
        f"after it runs (spec §9.1, overlays' skip resolution)"
    )


def _re_enterable(state: RunState, workflow: Workflow, member_id: str) -> bool:
    """Whether a `skipped` record is one a route may re-enter.

    Two of the three reasons a record wears that status are re-enterable
    and readable from the declarations: a conditional member is skipped
    until a route fires it (§10), and a step whose output the run imported
    is skipped with the artifact already in place, which §8.6 has a route
    "run on the imported copy as it would on any artifact it is given". The
    third is work the accepted class excluded, which a route may not
    resurrect — and which is what a record is when it is neither of the
    other two.
    """
    for stage in workflow.stages:
        for member in stage.members:
            if member.id == member_id:
                if member.conditional:
                    return True
    return member_id in _import_skipped(state, workflow)


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
    # Every run holds the request it was created from, and the manifest is
    # where a reader finds it (§8.2, §8.7) — the `contains` the run-state
    # schema carries, mirrored here because this driver reads state it did not
    # write. A document without it describes a run whose entry step could never
    # have been given what it restates, and `save` round-trips through this
    # function, so it refuses writing such a document as readily as reading one.
    if REQUEST_ARTIFACT not in artifacts_data:
        raise bad(f"artifacts does not carry {REQUEST_ARTIFACT!r} (spec §8.7)")

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
        # The request is never imported (§8.7), which the schema excludes
        # outright: an import adopts an artifact a step of the source run
        # produced, and the request has no producing step. Checked ahead of the
        # manifest, since it is in every manifest and would otherwise pass the
        # test that catches an unmanifested lineage. Case folding aside: the copy
        # lands at the path the record names, and `{run}/REQUEST.md` is that
        # same file wherever the filesystem folds case, so an exact comparison
        # would let a lineage record overwrite the request it cannot name.
        if names_request(artifact):
            raise bad(
                f"import {artifact!r} names {REQUEST_ARTIFACT} — the request is "
                f"never imported (spec §8.7)"
            )
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
