"""Run state: the one document the executor maintains (protocol/spec.md §10).

This module owns every read and write of `{run}/workflow-state.yaml` — the
single-writer rule is enforced by shape: nothing else in the driver touches
the file, and every mutation lands through `save`, which writes a sibling
temp file and replaces atomically, so a crash leaves the previous state
rather than half of the next one.

What lands here is WP-scoped deliberately. Creation bootstraps the intake
records alone — §10 has the list complete only from the intake gate's
acceptance, and §7 makes that acceptance the write that populates the rest,
which is the gate handler's to perform when it lands. Loops (§9.2) and the
import lineage (§8.6, in review) are later modules' too; this one resolves
position (§8.5), enforces verdict edges (§9.1), and keeps the manifest
current as outputs land (§8.2).
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

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
PROTOCOL_VERSION = re.compile(r"^[0-9]+\.[0-9]+$")
# The run-state schema's `{run}`-relative import path (§8.6): anchored
# at `{run}/`, no dot or empty segments, backslashes, control characters
# or Unicode line separators, colons, Windows-forbidden characters,
# reserved device basenames, or trailing dots and spaces. A loader that
# checked the prefix alone would present `{run}/../outside` as validated
# lineage to the materialization that later copies it. The literal is the
# schema's own pattern; test_state pins the two byte-for-byte.
IMPORT_PATH = re.compile('^\\{run\\}(?:/(?!\\.{1,2}(?:/|$))(?!(?:[Cc][Oo][Nn]|[Pp][Rr][Nn]|[Aa][Uu][Xx]|[Nn][Uu][Ll]|[Cc][Oo][Mm][1-9¹²³]|[Ll][Pp][Tt][1-9¹²³])(?:\\.|/|$))[^/\\\\:?*"<>|\x00-\x1f\x7f-\x9f\u2028\u2029]+(?<![. ]))+(?![\\s\\S])')


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


def create_run(
    runs_dir: Path, run_id: str, workflow: Workflow, protocol: str
) -> tuple[Path, RunState]:
    """Create `{artifacts}/runs/<run-id>/` and its bootstrap state: the entry
    stage's records alone, conditional members `skipped`, the rest `pending`
    (§10). The directory MUST NOT pre-exist — concurrent runs and re-runs
    never share one (§8.1)."""
    if not PLAIN_NAME.match(run_id):
        raise StateError(f"not a run id: {run_id!r}")
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = runs_dir / run_id
    try:
        run_dir.mkdir()
    except FileExistsError:
        raise StateError(f"run {run_id!r} already exists") from None
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
    save(state, run_dir)
    return run_dir, state


def load(run_dir: Path) -> RunState:
    path = run_dir / STATE_FILE
    try:
        text = path.read_text(encoding="utf-8")
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


def save(state: RunState, run_dir: Path) -> None:
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


def start_step(state: RunState, step_id: str) -> StepRecord:
    """Mark one record `active`. At most one may be (§10) — a second active
    record would make §8.5's resume ambiguous."""
    for step in state.steps:
        if step.status == "active" and step.id != step_id:
            raise StateError(
                f"step {step.id!r} is already active — a run has at most one"
            )
    record = state.record(step_id)
    if record.status == "done":
        raise StateError(f"step {step_id!r} is already done")
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


def route_verdict(state: RunState, workflow: Workflow, step_id: str, verdict: str) -> str:
    """The target the producing step's `on` declares for `verdict` (§9.1),
    resolved to a member id: a stage id stands for that stage's first
    non-`skipped` step. No edge means escalate — never guess. Routing to a
    record re-enters it: the destination returns to `pending` (a `skipped`
    conditional included, §10) for the resume to find."""
    declaration = workflow.step(step_id)
    if declaration is None:
        raise StateError(f"no declaration for step {step_id!r}")
    target = declaration.edges.get(verdict)
    if target is None:
        raise StateError(
            f"step {step_id!r} has no edge for verdict {verdict!r} — "
            f"escalate rather than guess (spec §9.1)"
        )
    resolved = _resolve_target(state, workflow, target)
    destination = state.record(resolved)
    if destination.status in ("skipped", "done", "blocked"):
        destination.status = "pending"
    return resolved


def _resolve_target(state: RunState, workflow: Workflow, target: str) -> str:
    for stage in workflow.stages:
        if stage.name == target:
            # §9.1: a stage id stands for that stage's first *step*, past the
            # content the run's class skips. Gates are members of the same
            # sequence and are not what a stage target names — routing to one
            # would stop the run at a decision nothing has yet produced work
            # for, where the rule sends it to the work itself.
            for member in stage.members:
                if member.kind != "step":
                    continue
                record = next(
                    (step for step in state.steps if step.id == member.id), None
                )
                if record is not None and record.status != "skipped":
                    return member.id
            raise StateError(
                f"stage {target!r} resolves to no runnable step (spec §9.1)"
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
    if not isinstance(run_id, str) or not PLAIN_NAME.match(run_id):
        raise bad(f"run.id is not a plain directory name: {run_id!r}")
    workflow = run.get("workflow")
    if not isinstance(workflow, str) or not workflow:
        raise bad("run.workflow is missing")
    protocol = run.get("protocol")
    if not isinstance(protocol, str) or not PROTOCOL_VERSION.match(protocol):
        raise bad(f"run.protocol is not <major>.<minor>: {protocol!r}")
    phase = run.get("phase")
    if phase is not None and not _is_count(phase, 1):
        raise bad(f"run.phase is not a positive integer: {phase!r}")
    risk = run.get("risk")
    rationale = run.get("risk_rationale")
    if (risk is None) != (rationale is None):
        raise bad("run.risk and run.risk_rationale move together (spec §10)")
    if risk is not None and risk not in RISKS:
        raise bad(f"run.risk is not one of {'/'.join(RISKS)}: {risk!r}")
    if rationale is not None and (not isinstance(rationale, str) or not rationale):
        raise bad("run.risk_rationale is empty")

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
        if not isinstance(at, str) or not at:
            raise bad(f"import {artifact!r} without a timestamp")
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
    if status not in STATUSES:
        raise bad(f"step {step_id!r} status is not one of {'/'.join(STATUSES)}: {status!r}")
    iterations = entry.get("iterations")
    if iterations is not None and not _is_count(iterations, 0):
        raise bad(f"step {step_id!r} iterations is not a count: {iterations!r}")
    stall_flags = entry.get("stall_flags")
    if stall_flags is not None and (
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
    transport = entry.get("transport")
    if transport not in TRANSPORTS:
        raise bad(f"gate {gate!r} transport is not one of {'/'.join(TRANSPORTS)}")
    outcome = entry.get("outcome")
    if outcome not in OUTCOMES:
        raise bad(f"gate {gate!r} outcome is not one of {'/'.join(OUTCOMES)}")
    at = entry.get("at")
    if not isinstance(at, str) or not at:
        raise bad(f"gate {gate!r} without a timestamp")
    phase = entry.get("phase")
    if phase is not None and not _is_count(phase, 1):
        raise bad(f"gate {gate!r} phase is not a positive integer: {phase!r}")
    return GateRecord(gate=gate, transport=transport, outcome=outcome, at=at, phase=phase)
