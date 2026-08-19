"""Workflow composition: the declared structure the state machine executes.

A workflow file composes stages by reference (protocol/spec.md §6.1); each
stage declares its members in record order (§9.4) and its steps' contracts
(§9.1). This module reads those declarations — nothing else: prose stays
prose, and a declaration the files do not carry is an error here rather
than something to infer, because the conformance suite already holds the
declarations complete and an inference layer would quietly outlive it.

The framework directory is the consuming project's copy of the protocol
content — where `workflows/` and `workflows/stages/` live. Resolving it is
project configuration, like the artifact root (§8.1); the driver takes it
as an argument rather than assuming the two share a parent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import PROTOCOL
from .protocol_yaml import ProtocolYamlError, loads

STAGE_REFERENCE = re.compile(r"\(stages/([a-z][a-z0-9-]*)\.md\)")
PROTOCOL_VERSION = re.compile(r"^([0-9]+)\.([0-9]+)$")
# The complete form, anchored to line end — a truncated `### thing (`
# must not declare a step whose contract then associates (the
# conformance suite holds the same rule).
STEP_HEADING = re.compile(
    r"^### (?P<id>[a-z][a-z0-9-]*) \((?P<role>[a-z]+)\)[ \t]*$", re.MULTILINE
)
YAML_BLOCK = re.compile(r"^```yaml[ \t]*\n(.*?)^```", re.DOTALL | re.MULTILINE)

VERDICTS = ("PASS", "PASS_WITH_CONDITIONS", "FAIL")


class WorkflowError(Exception):
    """The workflow or a stage it composes is missing or malformed."""


@dataclass(frozen=True)
class InputDeclaration:
    artifact: str
    required: bool


@dataclass(frozen=True)
class StepDeclaration:
    """One step's contract (spec §9.1): who acts, what it reads and writes,
    and where each verdict routes. `edges` is empty where the step declares
    no `on` — it then proceeds in composition order, or a loop contract
    consumes its validation verdict."""

    id: str
    role: str
    inputs: tuple[InputDeclaration, ...]
    output_artifact: str
    output_template: str | None
    edges: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Member:
    """One sequence entry (spec §9.4): a step or a gate, in record order,
    `conditional` meaning populated `skipped` until a route reaches it."""

    kind: str  # "step" | "gate"
    id: str
    conditional: bool = False


@dataclass(frozen=True)
class Stage:
    name: str
    members: tuple[Member, ...]
    steps: dict[str, StepDeclaration]

    def member_ids(self) -> tuple[str, ...]:
        return tuple(member.id for member in self.members)


@dataclass(frozen=True)
class Workflow:
    name: str
    stages: tuple[Stage, ...]

    def members(self) -> tuple[tuple[Stage, Member], ...]:
        """Every member of every stage, in composition order — the record
        order §10's populated list follows."""
        return tuple(
            (stage, member) for stage in self.stages for member in stage.members
        )

    def step(self, step_id: str) -> StepDeclaration | None:
        for stage in self.stages:
            if step_id in stage.steps:
                return stage.steps[step_id]
        return None


def load_workflow(framework: Path, name: str) -> Workflow:
    """Read `workflows/<name>.md` and every stage it composes."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise WorkflowError(f"not a workflow name: {name!r}")
    path = framework / "workflows" / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    # Undecodable is malformed, not a missing file: UnicodeDecodeError is a
    # ValueError rather than an OSError, so without this it would leave the
    # driver as a traceback instead of the exit code a defect is reported at.
    except (OSError, UnicodeError) as error:
        raise WorkflowError(f"cannot read workflow {name!r}: {error}") from error
    # The workflow file's own declarations are read for their version even
    # though this module consumes none of them: §9 holds every block to the
    # version it was authored against, and a trigger (§9.3) from a release
    # this driver does not implement, or a block that is not the subset's
    # YAML, is the same mismatched installation a stage file's would be.
    # Executing this file's composition while leaving its own declarations
    # unread is what would make that silent. What the trigger declares is a
    # later module's to act on.
    _blocks(text, f"workflows/{name}.md")
    # Composition order with the first mention winning: the numbered list at
    # the top composes; later prose may re-reference the same stages.
    slugs: list[str] = []
    for match in STAGE_REFERENCE.finditer(text):
        if match.group(1) not in slugs:
            slugs.append(match.group(1))
    if not slugs:
        raise WorkflowError(f"workflow {name!r} composes no stages")
    stages = tuple(_load_stage(framework, slug) for slug in slugs)
    _check_member_ids(stages)
    return Workflow(name=name, stages=stages)


def _check_member_ids(stages: tuple[Stage, ...]) -> None:
    """§9.4: member ids are unique across stages and distinct from every
    stage id. Both are only checkable once composition is known, and both
    bite here: the workflow concatenates these sequences into one record
    list (§10), where an id two stages share is the duplicate record §10
    forbids and `Workflow.step` would answer for with whichever declaration
    came first — and §9.1's targets are untyped strings, so a member wearing
    a stage's id makes every edge naming it ambiguous."""
    stage_names = {stage.name for stage in stages}
    declared_by: dict[str, str] = {}
    for stage in stages:
        for member in stage.members:
            if member.id in stage_names:
                raise WorkflowError(
                    f"stage {stage.name!r} declares member {member.id!r}, "
                    f"which is a stage id (spec §9.4)"
                )
            owner = declared_by.get(member.id)
            if owner is not None:
                raise WorkflowError(
                    f"member {member.id!r} is declared by stages {owner!r} and "
                    f"{stage.name!r} (spec §9.4)"
                )
            declared_by[member.id] = stage.name


def _load_stage(framework: Path, slug: str) -> Stage:
    path = framework / "workflows" / "stages" / f"{slug}.md"
    rel = f"workflows/stages/{slug}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorkflowError(f"cannot read stage {rel}: {error}") from error
    members = _members(text, rel)
    steps = _steps(text, rel)
    declared = {member.id for member in members if member.kind == "step"}
    for member_id in sorted(declared - set(steps)):
        raise WorkflowError(f"{rel}: sequence step {member_id!r} has no step block")
    for step_id in sorted(set(steps) - declared):
        raise WorkflowError(f"{rel}: step {step_id!r} is not in the sequence")
    return Stage(name=slug, members=members, steps=steps)


def _blocks(text: str, rel: str) -> list[tuple[int, dict]]:
    """Every `metadata.workflow` value in the file's fenced blocks, with the
    text offset it starts at — position is what ties a step block to the
    heading above it."""
    found: list[tuple[int, dict]] = []
    for match in YAML_BLOCK.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        try:
            data = loads(match.group(1))
        except ProtocolYamlError as error:
            raise WorkflowError(f"{rel}:{line}: {error}") from error
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata")
        workflow = metadata.get("workflow") if isinstance(metadata, dict) else None
        if isinstance(workflow, dict):
            _check_protocol(workflow, rel, line)
            found.append((match.start(), workflow))
    return found


def _check_protocol(block: dict, rel: str, line: int) -> None:
    """§9: every `metadata.workflow` block declares the protocol version it
    was authored against, and §11 forbids a client silently interpreting
    structures from a version it does not implement. A different major is
    that case outright; a newer minor is it during `0.x` too, where any
    minor MAY carry breaking changes — the driver and the protocol content
    it reads ship as one release, so a version it does not implement is a
    mismatched installation to report, not a document to guess at."""
    version = block.get("protocol")
    if not isinstance(version, str) or not PROTOCOL_VERSION.match(version):
        raise WorkflowError(
            f"{rel}:{line}: declaration without a protocol version: {version!r}"
        )
    declared = tuple(int(part) for part in version.split("."))
    implemented = tuple(int(part) for part in PROTOCOL.split("."))
    if declared[0] != implemented[0] or declared[1] > implemented[1]:
        raise WorkflowError(
            f"{rel}:{line}: declaration is protocol {version}, and this driver "
            f"implements {PROTOCOL} (spec §11)"
        )


def _members(text: str, rel: str) -> tuple[Member, ...]:
    sequences = [
        workflow["stage"]
        for _, workflow in _blocks(text, rel)
        if isinstance(workflow.get("stage"), dict)
    ]
    if len(sequences) != 1:
        raise WorkflowError(f"{rel}: {len(sequences)} stage sequence blocks, need 1")
    entries = sequences[0].get("sequence")
    if not isinstance(entries, list) or not entries:
        raise WorkflowError(f"{rel}: stage sequence is empty")
    members: list[Member] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise WorkflowError(f"{rel}: sequence entry is not a mapping: {entry!r}")
        step = entry.get("step")
        gate = entry.get("gate")
        if isinstance(step, str) and gate is None:
            kind, member_id = "step", step
        elif isinstance(gate, str) and step is None:
            kind, member_id = "gate", gate
        else:
            raise WorkflowError(f"{rel}: sequence entry is not one member: {entry!r}")
        if any(member.id == member_id for member in members):
            raise WorkflowError(f"{rel}: sequence names {member_id!r} twice")
        # §9.4 admits `conditional: true` and absence, nothing else — the
        # schema declares the field `const: true`. Reading any other value as
        # unconditional would populate a revising member or a conditional
        # gate `pending` rather than `skipped`, and a resume would reach it
        # before the route that is supposed to fire it ever did.
        if "conditional" in entry and entry["conditional"] is not True:
            raise WorkflowError(
                f"{rel}: member {member_id!r} declares conditional "
                f"{entry['conditional']!r} — the form is `true` or absent"
            )
        members.append(
            Member(kind=kind, id=member_id, conditional="conditional" in entry)
        )
    return tuple(members)


def _steps(text: str, rel: str) -> dict[str, StepDeclaration]:
    headings = [
        (m.start(), m.group("id"), m.group("role")) for m in STEP_HEADING.finditer(text)
    ]
    steps: dict[str, StepDeclaration] = {}
    for offset, workflow in _blocks(text, rel):
        declaration = workflow.get("step")
        if not isinstance(declaration, dict):
            continue
        prior = [(x, role) for start, x, role in headings if start < offset]
        if not prior:
            raise WorkflowError(f"{rel}: step block above the first step heading")
        step_id, heading_role = prior[-1]
        if step_id in steps:
            raise WorkflowError(f"{rel}: step {step_id!r} declares two step blocks")
        step = _step_declaration(declaration, step_id, rel)
        # The heading is what a human executing the prose reads and the
        # contract what this driver executes; a disagreement would run the
        # step as a role its own stage does not name (the conformance suite
        # holds the same rule).
        if step.role != heading_role:
            raise WorkflowError(
                f"{rel}: step {step_id!r} declares role {step.role!r} under a "
                f"heading that says {heading_role!r}"
            )
        steps[step_id] = step
    return steps


def _step_declaration(declaration: dict, step_id: str, rel: str) -> StepDeclaration:
    at = f"{rel}: step {step_id!r}"
    role = declaration.get("role")
    if not isinstance(role, str) or not role:
        raise WorkflowError(f"{at}: missing role")
    output = declaration.get("output")
    artifact = output.get("artifact") if isinstance(output, dict) else None
    if not isinstance(artifact, str) or not artifact:
        raise WorkflowError(f"{at}: missing output artifact")
    template = output.get("template") if isinstance(output, dict) else None
    if template is not None and not isinstance(template, str):
        raise WorkflowError(f"{at}: template is not a string")
    inputs: list[InputDeclaration] = []
    # Absence is the only thing that means "no declared inputs". A present
    # `inputs` that is not a list — `false`, `null`, a mapping — is an
    # authoring error, and reading it as absence would drop the step's whole
    # handoff contract rather than report the one line that broke it.
    declared_inputs = declaration.get("inputs", [])
    if not isinstance(declared_inputs, list):
        raise WorkflowError(f"{at}: `inputs` is not a list: {declared_inputs!r}")
    for entry in declared_inputs:
        input_artifact = entry.get("artifact") if isinstance(entry, dict) else None
        if not isinstance(input_artifact, str) or not input_artifact:
            raise WorkflowError(f"{at}: input without an artifact")
        # §9.1 has no default in prose; the schemas require the field only
        # when false matters, and every shipped block states it. Reading
        # absence as required errs toward blocking, never toward silently
        # running without a declared dependency — but only absence: a
        # present non-boolean would otherwise be coerced to required and
        # change what blocks the step without saying so.
        required = entry.get("required", True)
        if not isinstance(required, bool):
            raise WorkflowError(
                f"{at}: input {input_artifact!r} declares required {required!r}, "
                f"which is not a boolean"
            )
        inputs.append(InputDeclaration(artifact=input_artifact, required=required))
    edges: dict[str, str] = {}
    on = declaration.get("on")
    if on is not None:
        if not isinstance(on, dict):
            raise WorkflowError(f"{at}: `on` is not a mapping")
        for verdict, target in on.items():
            if verdict not in VERDICTS or not isinstance(target, str) or not target:
                raise WorkflowError(f"{at}: bad edge {verdict!r}: {target!r}")
            edges[verdict] = target
        # §9.1: a declared `on` routes at least PASS and FAIL.
        if "PASS" not in edges or "FAIL" not in edges:
            raise WorkflowError(f"{at}: `on` must route PASS and FAIL")
    return StepDeclaration(
        id=step_id,
        role=role,
        inputs=tuple(inputs),
        output_artifact=artifact,
        output_template=template,
        edges=edges,
    )
