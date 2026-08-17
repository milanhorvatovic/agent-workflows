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

from .protocol_yaml import ProtocolYamlError, loads

STAGE_REFERENCE = re.compile(r"\(stages/([a-z][a-z0-9-]*)\.md\)")
STEP_HEADING = re.compile(r"^### (?P<id>[a-z][a-z0-9-]*) \(", re.MULTILINE)
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
    except OSError as error:
        raise WorkflowError(f"cannot read workflow {name!r}: {error}") from error
    # Composition order with the first mention winning: the numbered list at
    # the top composes; later prose may re-reference the same stages.
    slugs: list[str] = []
    for match in STAGE_REFERENCE.finditer(text):
        if match.group(1) not in slugs:
            slugs.append(match.group(1))
    if not slugs:
        raise WorkflowError(f"workflow {name!r} composes no stages")
    return Workflow(
        name=name,
        stages=tuple(_load_stage(framework, slug) for slug in slugs),
    )


def _load_stage(framework: Path, slug: str) -> Stage:
    path = framework / "workflows" / "stages" / f"{slug}.md"
    rel = f"workflows/stages/{slug}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
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
            found.append((match.start(), workflow))
    return found


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
        members.append(
            Member(kind=kind, id=member_id, conditional=entry.get("conditional") is True)
        )
    return tuple(members)


def _steps(text: str, rel: str) -> dict[str, StepDeclaration]:
    headings = [(m.start(), m.group("id")) for m in STEP_HEADING.finditer(text)]
    steps: dict[str, StepDeclaration] = {}
    for offset, workflow in _blocks(text, rel):
        declaration = workflow.get("step")
        if not isinstance(declaration, dict):
            continue
        prior = [heading_id for start, heading_id in headings if start < offset]
        if not prior:
            raise WorkflowError(f"{rel}: step block above the first step heading")
        step_id = prior[-1]
        if step_id in steps:
            raise WorkflowError(f"{rel}: step {step_id!r} declares two step blocks")
        steps[step_id] = _step_declaration(declaration, step_id, rel)
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
    for entry in declaration.get("inputs") or []:
        input_artifact = entry.get("artifact") if isinstance(entry, dict) else None
        if not isinstance(input_artifact, str) or not input_artifact:
            raise WorkflowError(f"{at}: input without an artifact")
        inputs.append(
            InputDeclaration(
                artifact=input_artifact,
                # §9.1 has no default in prose; the schemas require the field
                # only when false matters, and every shipped block states it.
                # Reading absence as required errs toward blocking, never
                # toward silently running without a declared dependency.
                required=entry.get("required") is not False,
            )
        )
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
