#!/usr/bin/env python3
"""Validate the protocol surface against the schemas in protocol/schemas/.

Eight checks:

- Fixtures: every `protocol/schemas/examples/<name>.valid.yaml` must satisfy
  its schema and every `<name>.invalid.yaml` must be rejected — the
  deliberately broken fixtures are the negative test proving the suite can
  fail at all.
- Spec examples: every ```yaml block embedded in `protocol/spec.md` must be a
  recognized protocol structure — a `metadata.workflow` block or a run-state
  document — and validate, so the spec's illustrative examples cannot drift
  from the normative schemas.
- Workflow blocks: every `metadata.workflow` block in every other markdown
  file — fenced in the body or declared in Agent Skills frontmatter (spec
  §9) — validates against the schema of each structure it declares (`step`,
  `loop`, `trigger`, `stage`); unknown sibling keys are tolerated per the 0.x
  degradation rules (spec §9.5). Placeholders in declared strings must be
  spec-defined — {run}, {N}, {P}, {machine-checks} — and a declared output
  template must exist relative to the declaring file. A step's output may not
  carry {P}, which the step schema rejects: one path per phase cannot name the
  one artifact a step produces (spec §8.1, §9.1).
- Frontmatter: roles, workflows, stages, and skills carry an Agent Skills
  conformant `name` (lowercase alphanumeric plus hyphens, ≤64 chars, equal
  to the file slug) and `description` (non-empty, ≤1024 chars); skills
  additionally carry a `license`, so installed copies state their terms
  standalone.
- Skill budget: every `skills/*/SKILL.md` body stays within the 500-line /
  ~5000-token budget.
- Step parity: a step-bound skill restates the step block its stage declares,
  identically — two copies of one contract drift silently, and spec §9.1
  makes the input declaration the executor's whole view of a step.
- Stage sequences: every stage that declares members carries exactly one
  `stage` sequence block naming each declared step and gate exactly once
  (spec §9.4) — the record order run-state population follows, so a member
  missing from it is a record no run could carry — member ids stay unique
  across stages and off the stage namespace, since composing two stages
  that share one would duplicate the record §10 forbids and a §9.1 target
  naming a stage's id would be ambiguous, and each heading owns exactly one
  contract that agrees with it about the role.
- Run-state documents: every one this repo ships is checked for semantics
  its schema cannot hold — a manifest current with the steps recorded
  `done`, a gate recorded `done` carrying a standing decision, at most one
  record per step, and an import lineage whose every path is manifested and
  named once, whose records name one source run that is not this one, and
  whose set is closed over some producing step's required inputs (spec
  §8.6), and a `steps` list following the composed stages' sequences, which
  is the order §8.5's resume reads (spec §9.4, §10). In every run-state
  document this repo ships, a step recorded `done` has its declared output
  in the manifest, `{N}` resolved from `run.phase` (spec §8.2). The map from step id to output is read off
  the stage contracts, since a run's steps are the composed workflow's, and
  bounded to the phase now executing — what an earlier phase owes cannot be
  read from records the phase reset, see `manifest_problems`.

YAML is parsed as YAML 1.2 (ruamel.yaml) — under PyYAML's YAML 1.1 the `on:`
key of a step block reads as boolean true, spuriously failing every step
against the schemas' `additionalProperties: false`.

Usage:
    python3 scripts/validate_conformance.py [--root DIR]
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, NoReturn

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
except ModuleNotFoundError as missing:
    sys.exit(
        f"validate-conformance: missing dependency '{missing.name}' — "
        "install with: python3 -m pip install -r scripts/requirements.txt"
    )

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
SPEC = Path("protocol/spec.md")
SCHEMA_DIR = Path("protocol/schemas")
FIXTURE_DIR = SCHEMA_DIR / "examples"

STRUCTURES = ("step", "loop", "trigger", "stage")  # metadata.workflow structures, one schema each
RUN_STATE = "run-state"

PLACEHOLDERS = {"run", "N", "P", "machine-checks"}  # spec §8.1 and §9.2
# {token} occurrences; the lookbehind skips ${...} shell expansions in commands.
PLACEHOLDER = re.compile(r"(?<!\$)\{([^{}]*)\}")

# One fence model, two scopes. Masking tolerates what CommonMark writes —
# backticks or tildes, both fence lines up to three spaces in, the closer at
# least the opener's length or absent (an unclosed fence extends to end of
# file) — while extraction takes first-column fences only, §9's own rule for
# where a declaration may live. Container-nested fences (block quotes, list
# items) are outside both scopes deliberately: a declaration there is
# nonconforming by §9, an indented fence is indistinguishable from a list
# item's content without parsing containers, and a container's example
# carries its marker or indent on every line, which already keeps its
# headings and bullets out of the line-anchored structure scans. finditer
# consumes each outermost fence whole, so a block nested inside a longer
# wrapper is never discovered as a declaration — the same fact that lets
# mask_fences blank examples out of the text scans.
FENCE = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?:(?P<bt>```+)(?P<bti>[^`\n]*)\n(?P<btb>.*?)(?:^ {0,3}(?P=bt)`*[ \t]*$|\Z)"
    r"|(?P<td>~~~+)(?P<tdi>[^\n]*)\n(?P<tdb>.*?)(?:^ {0,3}(?P=td)~*[ \t]*$|\Z))",
    re.DOTALL | re.MULTILINE,
)

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64  # Agent Skills frontmatter cap
DESCRIPTION_MAX = 1024  # Agent Skills frontmatter cap
SKILL_BODY_MAX_LINES = 500
SKILL_BODY_MAX_TOKENS = 5000
CHARS_PER_TOKEN = 4  # rough budget heuristic, matches common tokenizer averages

# §9's two carriers, each at one location — the paths a declaration may
# live at, so a block elsewhere is reported rather than executed by nothing.
WORKFLOW_FILE = re.compile(r"workflows/[a-z][a-z0-9-]*\.md")
STAGE_FILE = re.compile(r"workflows/stages/[a-z][a-z0-9-]*\.md")
SKILL_FILE = re.compile(r"skills/[a-z][a-z0-9-]*/SKILL\.md")

FRONTMATTER_GLOBS = (
    "roles/*.md",
    "workflows/*.md",
    "workflows/stages/*.md",
    "skills/*/SKILL.md",
)

YAML_LOADER = YAML(typ="safe", pure=True)


@dataclass(frozen=True)
class Block:
    at: str  # "<repo-relative path>:<fence line>"
    data: Any


def fail(message: str) -> NoReturn:
    sys.exit(f"validate-conformance: {message}")


def first_line(error: object) -> str:
    return (str(error).strip() or "?").splitlines()[0]


def jsonify(value: Any) -> Any:
    """ruamel resolves unquoted YAML timestamps to datetime objects; the
    schemas type them as strings, so serialize them back before validating."""
    if isinstance(value, dict):
        return {key: jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonify(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def load_schemas(root: Path) -> dict[str, Draft202012Validator]:
    validators: dict[str, Draft202012Validator] = {}
    for path in sorted((root / SCHEMA_DIR).glob("*.schema.json")):
        rel = path.relative_to(root).as_posix()
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except (json.JSONDecodeError, SchemaError) as error:
            fail(f"{rel}: not a valid schema: {first_line(error)}")
        validators[path.name.removesuffix(".schema.json")] = Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
    missing = sorted({*STRUCTURES, RUN_STATE} - validators.keys())
    if missing:
        fail(f"{SCHEMA_DIR.as_posix()}: missing schemas: {', '.join(missing)}")
    return validators


def schema_problems(
    at: str, name: str, validator: Draft202012Validator, instance: Any
) -> list[str]:
    errors = sorted(validator.iter_errors(instance), key=lambda error: error.json_path)
    return [f"{at}: [{name}] {error.json_path}: {error.message}" for error in errors]


def yaml_blocks(text: str, rel: str, problems: list[str]) -> list[Block]:
    """Every declaration fence: a `yaml` fence of either marker beginning at
    the first column, which is where spec §9 places a declaration. An
    indented fence is an example — masking tolerates CommonMark's three
    spaces, extraction does not, since a legal top-level indent and a list
    item's content indent are the same bytes. Discovery consumes outermost
    fences whole, so a block inside a longer wrapper is never a
    declaration."""
    blocks: list[Block] = []
    for match in FENCE.finditer(text):
        info = (match.group("bti") or match.group("tdi") or "").strip()
        if info != "yaml":
            continue
        # Declarations begin at the first column (spec §9): a 1-3-space
        # indent is legal CommonMark at top level, but so is a list item's
        # content indent, and no line-anchored rule can tell the two apart —
        # so an indented fence is masked as an example, never extracted.
        if match.group("indent"):
            continue
        body = match.group("btb") if match.group("bt") else match.group("tdb")
        line = text.count("\n", 0, match.start()) + 1
        at = f"{rel}:{line}"
        try:
            data = jsonify(YAML_LOADER.load(body))
        except YAMLError as error:
            problems.append(f"{at}: yaml block does not parse: {first_line(error)}")
            continue
        blocks.append(Block(at, data))
    return blocks


def workflow_value(data: Any) -> Any:
    if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
        return data["metadata"].get("workflow")
    return None


def frontmatter_block(text: str, rel: str) -> Block | None:
    """A `metadata.workflow` declared in Agent Skills frontmatter (spec §9) —
    the same structure as a fenced block, extracted from the frontmatter
    mapping instead. Unparseable frontmatter is the frontmatter check's
    finding, not this one's."""
    found = FRONTMATTER.match(text)
    if found is None:
        return None
    try:
        data = jsonify(YAML_LOADER.load(found.group(1)))
    except YAMLError:
        return None
    return Block(f"{rel}:1", data)


def strings_of(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_of(item)


def placeholder_problems(at: str, workflow: Any) -> list[str]:
    known = ", ".join("{" + name + "}" for name in sorted(PLACEHOLDERS))
    problems = []
    for value in strings_of(workflow):
        for token in PLACEHOLDER.findall(value):
            if token in PLACEHOLDERS:
                continue
            if token == "artifacts":
                problems.append(
                    f'{at}: "{{artifacts}}" is resolved by the executor, never authored — '
                    "metadata addresses paths relative to {run} (spec §8.1)"
                )
            else:
                problems.append(f'{at}: unknown placeholder "{{{token}}}" (spec defines: {known})')
    return problems


def declared_template(workflow: dict) -> str | None:
    step = workflow.get("step")
    output = step.get("output") if isinstance(step, dict) else None
    template = output.get("template") if isinstance(output, dict) else None
    return template if isinstance(template, str) else None


def template_problems(at: str, template: str, template_dir: Path) -> list[str]:
    if Path(template).is_absolute():
        return [f"{at}: declared template must be relative to the declaring file: {template}"]
    resolved = (template_dir / template).resolve()
    if not resolved.is_relative_to(template_dir.resolve()):
        return [f"{at}: declared template escapes the declaring file's directory: {template}"]
    if not resolved.is_file():
        return [f"{at}: declared template not found: {template}"]
    return []


def validate_workflow_block(
    block: Block,
    workflow: Any,
    validators: dict[str, Draft202012Validator],
    template_dir: Path | None,
) -> list[str]:
    if not isinstance(workflow, dict):
        return [f"{block.at}: metadata.workflow is not a mapping"]
    declared = [structure for structure in STRUCTURES if structure in workflow]
    if not declared:
        return [f"{block.at}: metadata.workflow declares none of: {', '.join(STRUCTURES)}"]
    problems = []
    for structure in declared:
        problems += schema_problems(block.at, structure, validators[structure], workflow)
    problems += placeholder_problems(block.at, workflow)
    template = declared_template(workflow)
    if template_dir is not None and template is not None:
        problems += template_problems(block.at, template, template_dir)
    return problems



def fixture_paths(root: Path, name: str) -> list[tuple[str, Path]]:
    """The fixtures for one schema: the required pair, plus any variants.

    `<name>.valid.yaml` and `<name>.invalid.yaml` are mandatory — their absence
    is a problem. Either kind may add `<name>.<kind>.<variant>.yaml` for a shape
    the pair does not reach: a further legal shape, or a further way to be
    illegal. One invalid fixture proves only that a document with several faults
    is rejected, which says nothing about any single rule — a constraint gets
    its own negative fixture or it has no coverage at all.
    """
    directory = root / FIXTURE_DIR
    found: list[tuple[str, Path]] = []
    for kind in ("valid", "invalid"):
        found.append((kind, directory / f"{name}.{kind}.yaml"))
        found.extend(
            (kind, path) for path in sorted(directory.glob(f"{name}.{kind}.*.yaml"))
        )
    return found


def check_fixtures(
    root: Path, validators: dict[str, Draft202012Validator]
) -> tuple[int, list[str]]:
    problems: list[str] = []
    checked = 0
    for name in sorted(validators):
        for kind, path in fixture_paths(root, name):
            rel = path.relative_to(root).as_posix()
            if not path.is_file():
                problems.append(f"{rel}: fixture missing")
                continue
            checked += 1
            try:
                data = jsonify(YAML_LOADER.load(path.read_text(encoding="utf-8")))
            except YAMLError as error:
                problems.append(f"{rel}: does not parse: {first_line(error)}")
                continue
            errors = schema_problems(rel, name, validators[name], data)
            if kind == "valid":
                problems += errors
            elif not errors:
                problems.append(
                    f"{rel}: deliberately broken fixture validates against "
                    f"{name}.schema.json — the negative test proves nothing"
                )
    return checked, problems


def check_spec_examples(
    root: Path, validators: dict[str, Draft202012Validator]
) -> tuple[int, list[str]]:
    path = root / SPEC
    if not path.is_file():
        return 0, [f"{SPEC.as_posix()}: not found"]
    problems: list[str] = []
    blocks = yaml_blocks(path.read_text(encoding="utf-8"), SPEC.as_posix(), problems)
    for block in blocks:
        workflow = workflow_value(block.data)
        if workflow is not None:
            problems += validate_workflow_block(block, workflow, validators, template_dir=None)
        elif isinstance(block.data, dict) and "run" in block.data:
            problems += schema_problems(block.at, RUN_STATE, validators[RUN_STATE], block.data)
        else:
            problems.append(
                f"{block.at}: unrecognized example — neither a metadata.workflow "
                "block nor a run-state document"
            )
    if not blocks and not problems:
        problems.append(f"{SPEC.as_posix()}: no embedded yaml examples found — nothing validated")
    return len(blocks), problems


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


def check_workflow_blocks(
    root: Path, validators: dict[str, Draft202012Validator]
) -> tuple[int, list[str]]:
    problems: list[str] = []
    validated = 0
    for path in markdown_files(root):
        if path == root / SPEC:
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        # §9's carriers are per file, and each is one location: a workflow
        # or stage file declares in its body, a skill in its frontmatter.
        # A declaration in the other carrier, or in a file that is neither,
        # is reported rather than validated as live — a declaration nothing
        # composes is one nothing executes.
        declares_in_body = WORKFLOW_FILE.fullmatch(rel) or STAGE_FILE.fullmatch(rel)
        declares_in_frontmatter = SKILL_FILE.fullmatch(rel)
        blocks = yaml_blocks(text, rel, problems)
        if not declares_in_body:
            for block in blocks:
                if workflow_value(block.data) is not None:
                    problems.append(
                        f"{block.at}: `metadata.workflow` in the body of a file "
                        f"that is neither a workflow nor a stage — §9 gives them "
                        f"the body carrier and a skill its frontmatter"
                    )
            blocks = []
        front = frontmatter_block(text, rel)
        if front is not None:
            if declares_in_frontmatter:
                blocks.append(front)
            elif workflow_value(front.data) is not None:
                problems.append(
                    f"{front.at}: `metadata.workflow` in the frontmatter of a "
                    f"file that is not a skill — §9 gives skills that carrier "
                    f"and workflow and stage files the body one"
                )
        for block in blocks:
            workflow = workflow_value(block.data)
            if workflow is None:
                continue
            validated += 1
            problems += validate_workflow_block(
                block, workflow, validators, template_dir=path.parent
            )
    if validated == 0:
        problems.append(
            "no metadata.workflow blocks found outside protocol/spec.md — nothing validated"
        )
    return validated, problems


def slug_of(path: Path) -> str:
    return path.parent.name if path.name == "SKILL.md" else path.stem


def name_problems(rel: str, name: Any, slug: str) -> list[str]:
    if not isinstance(name, str) or not name:
        return [f"{rel}: frontmatter has no name"]
    problems = []
    if NAME.fullmatch(name) is None:
        problems.append(
            f"{rel}: name '{name}' is not lowercase-alphanumeric-with-hyphens (Agent Skills)"
        )
    if len(name) > NAME_MAX:
        problems.append(f"{rel}: name is {len(name)} chars, Agent Skills caps it at {NAME_MAX}")
    if name != slug:
        problems.append(f"{rel}: name '{name}' does not match the file slug '{slug}'")
    return problems


def description_problems(rel: str, description: Any) -> list[str]:
    if not isinstance(description, str) or not description.strip():
        return [f"{rel}: frontmatter has no description"]
    if len(description) > DESCRIPTION_MAX:
        return [
            f"{rel}: description is {len(description)} chars, "
            f"Agent Skills caps it at {DESCRIPTION_MAX}"
        ]
    return []


def license_problems(rel: str, license_value: Any) -> list[str]:
    if not isinstance(license_value, str) or not license_value.strip():
        return [
            f"{rel}: frontmatter has no license — installed skill copies "
            "must state their terms standalone"
        ]
    return []


def check_frontmatter(root: Path) -> tuple[int, list[str]]:
    problems: list[str] = []
    paths = sorted(
        path
        for pattern in FRONTMATTER_GLOBS
        for path in root.glob(pattern)
        if path.name != "README.md"
    )
    for path in paths:
        rel = path.relative_to(root).as_posix()
        found = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if found is None:
            problems.append(f"{rel}: no frontmatter block")
            continue
        try:
            frontmatter = jsonify(YAML_LOADER.load(found.group(1)))
        except YAMLError as error:
            problems.append(f"{rel}: frontmatter does not parse: {first_line(error)}")
            continue
        if not isinstance(frontmatter, dict):
            problems.append(f"{rel}: frontmatter is not a mapping")
            continue
        problems += name_problems(rel, frontmatter.get("name"), slug_of(path))
        problems += description_problems(rel, frontmatter.get("description"))
        if path.name == "SKILL.md":
            problems += license_problems(rel, frontmatter.get("license"))
    return len(paths), problems


def check_skill_budgets(root: Path) -> tuple[int, list[str]]:
    problems: list[str] = []
    paths = sorted(root.glob("skills/*/SKILL.md"))
    for path in paths:
        rel = path.relative_to(root).as_posix()
        body = FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1)
        lines = len(body.splitlines())
        tokens = math.ceil(len(body) / CHARS_PER_TOKEN)
        if lines > SKILL_BODY_MAX_LINES:
            problems.append(f"{rel}: body is {lines} lines, budget is {SKILL_BODY_MAX_LINES}")
        if tokens > SKILL_BODY_MAX_TOKENS:
            problems.append(f"{rel}: body is ~{tokens} tokens, budget is {SKILL_BODY_MAX_TOKENS}")
    return len(paths), problems


# The complete form, anchored to line end: a truncated `### thing (` or a
# heading with trailing text is malformed, not a valid declaration whose
# contract may associate.
STAGE_STEP_HEADING = re.compile(
    r"^### (?P<id>[a-z][a-z0-9-]*) \((?P<role>[a-z]+)\)[ \t]*$", re.MULTILINE
)


def step_of(block: Block | None) -> Any:
    """The `step` mapping inside a `metadata.workflow`, or None."""
    if block is None:
        return None
    workflow = workflow_value(block.data)
    if isinstance(workflow, dict) and isinstance(workflow.get("step"), dict):
        return workflow["step"]
    return None


def items_of(value: Any) -> list[Any]:
    """The entries of a value the schema declares as an array, or nothing.

    A value of the wrong shape is the schema pass's to report and these checks
    run over documents it has already faulted, so a scalar must read as empty
    here rather than raise mid-iteration. Both array fields a run-state
    document offers go through this, so guarding one and not its neighbour is
    not a thing that can be done by accident.
    """
    return value if isinstance(value, list) else []


def output_artifact(step: Any) -> Any:
    """The `artifact` a step declares as its output.

    Returns the raw `output` value where that value is not a mapping. These
    checks run over frontmatter the schema pass has faulted rather than instead
    of it, and `main` prints nothing until every check has run — so a malformed
    declaration must read as a value here and be reported there, never raise
    and take the accumulated problems down with it.
    """
    output = step.get("output") if isinstance(step, dict) else None
    if not isinstance(output, dict):
        return output
    return output.get("artifact")


def stage_steps(root: Path, problems: list[str]) -> dict[str, tuple[str, Any]]:
    """Every step a stage contract declares, keyed by its `### <id>` heading.

    A stage's fenced block sits under the heading that names the step, so the
    nearest preceding heading is the step id.
    """
    found: dict[str, tuple[str, Any]] = {}
    for path in sorted(root.glob("workflows/stages/*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        # Headings come from the masked text: a `### fake (role)` inside a
        # fenced example between a real heading and its contract would
        # otherwise key the contract as `fake`, corrupting parity and the
        # output maps. The mask keeps offsets, so block association holds.
        headings = [
            (m.start(), m.group("id"))
            for m in STAGE_STEP_HEADING.finditer(mask_fences(text))
        ]
        for block in yaml_blocks(text, rel, problems):
            step = step_of(block)
            if step is None:
                continue
            line = int(block.at.rsplit(":", 1)[1])
            offset = sum(len(x) + 1 for x in text.splitlines(keepends=False)[: line - 1])
            prior = [name for start, name in headings if start < offset]
            if prior:
                found[prior[-1]] = (block.at, step)
    return found


def check_step_parity(root: Path) -> tuple[int, list[str]]:
    """A step-bound skill restates the step block its stage declares. Two
    copies of one contract drift silently, so they must stay identical —
    spec §9.1 makes the input declaration the executor's whole view of a
    step, and a skill promising inputs its stage does not is unexecutable
    under the stage."""
    problems: list[str] = []
    stages = stage_steps(root, problems)
    checked = 0
    for path in sorted(root.glob("skills/*/SKILL.md")):
        rel = path.relative_to(root).as_posix()
        step = step_of(frontmatter_block(path.read_text(encoding="utf-8"), rel))
        if step is None:
            continue
        step_id = path.parent.name.removeprefix("awf-")
        if step_id not in stages:
            continue  # standalone skill: no stage declares it
        checked += 1
        at, declared = stages[step_id]
        for field in ("role", "inputs", "on"):
            if step.get(field) != declared.get(field):
                problems.append(
                    f"{rel}: step `{field}` differs from the one {at} declares "
                    f"for `{step_id}`; two copies of one contract must agree"
                )
        skill_out = output_artifact(step)
        stage_out = output_artifact(declared)
        if skill_out != stage_out:
            problems.append(
                f"{rel}: step output artifact differs from the one {at} declares "
                f"for `{step_id}`; two copies of one contract must agree"
            )
    return checked, problems


def step_outputs(root: Path) -> dict[str, str]:
    """Every output a stage contract declares, keyed by step id.

    Read from the stages rather than from `skills/`, because a run's `steps`
    are the composed workflow's steps and it is the stages that compose it. The
    two are not the same set in either direction: a standalone skill is not a
    step, so keying by skill would let one lend its output to any run-state
    record that happened to share its id, and a stage step whose skill is
    missing would be silently exempt from the manifest rule instead of held to
    the output its stage declares. Parse problems are discarded here — every
    stage file is a markdown file, so `check_workflow_blocks` reports them
    already, and `check_step_parity` reports them again from its own read.
    """
    found: dict[str, str] = {}
    for step_id, (_, step) in stage_steps(root, []).items():
        # Stricter than the parity check's use of the same field, and for the
        # opposite reason: parity compares whatever is declared, so a malformed
        # value is a value to compare, while a step id mapped to a malformed
        # value here would be read back as an artifact path and reported as
        # missing from a manifest that could never have listed it.
        output = step.get("output") if isinstance(step, dict) else None
        artifact = output.get("artifact") if isinstance(output, dict) else None
        if isinstance(artifact, str):
            found[step_id] = artifact
    return found


def manifest_problems(at: str, data: Any, outputs: dict[str, str]) -> list[str]:
    """Spec §8.2: the manifest lists what the run has produced, so the output
    of a step recorded `done` belongs in it.

    Only `done` is checked, and deliberately. A record reading `pending` may
    still have produced its output — a `revise` routing back to it, or entering
    a phase, resets the record and leaves the artifact where it was — so its
    absence from the manifest proves nothing either way. `done` is the one
    status that always implies the output landed.
    """
    if not isinstance(data, dict) or not isinstance(data.get("run"), dict):
        return []
    phase = data["run"].get("phase", 1)
    manifest = {x for x in items_of(data.get("artifacts")) if isinstance(x, str)}
    problems: list[str] = []
    # Only the phase now executing is checked. What a prior phase owes cannot
    # be read from this document: records are one per step and are reset when a
    # phase is entered, so a `skipped` record may have run in an earlier phase
    # and a running one may have been skipped there — reading either as evidence
    # about the phase before is inference, not fact, and it has been wrong in
    # both directions here. §8.2's growth rule still binds the executor across
    # phases; nothing here can confirm it until run state records per-phase
    # participation the way `gates` now records the phase a decision belongs to.
    for step in items_of(data.get("steps")):
        if not isinstance(step, dict) or step.get("status") != "done":
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str):
            continue  # not a usable id; check_fixtures faults it against the schema
        artifact = outputs.get(step_id)
        if artifact is None:
            continue  # a gate, or a step no skill declares
        resolved = artifact.replace("{N}", str(phase))
        if resolved not in manifest:
            problems.append(
                f"{at}: `{step_id}` is done and its output {resolved} is not in "
                f"the manifest — spec §8.2 has the executor keep it current"
            )
    return problems


GATE_HEADING = re.compile(r"^- \*\*(?P<id>[a-z][a-z0-9-]*)\*\*", re.MULTILINE)
# Anything bullet-and-bold in a Gates section is gate-shaped; one that then
# fails GATE_HEADING's id form is a malformed gate to report, never silence.
GATE_SHAPED = re.compile(r"^- \*\*(?P<raw>[^*\n]+)\*\*", re.MULTILINE)


# The closing run must be at least as long as the opener (CommonMark): a
# four-backtick wrapper demonstrating a triple-backtick block would
# otherwise close at the inner fence and leave the example's tail
# unmasked.

GENERIC_H3 = re.compile(r"^### ", re.MULTILINE)
GENERIC_H2 = re.compile(r"^## ", re.MULTILINE)
GATES_HEADING = re.compile(r"^## Gates[ \t]*$", re.MULTILINE)


def mask_fences(text: str) -> str:
    """Fenced code blanked to spaces with newlines kept: an exact `## Gates`
    or a `### <id> (<role>)` inside an example must not read as structure,
    and preserving every offset and line number is what lets the scans that
    follow keep pointing into the raw text."""
    def blank(match: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in match.group(0))

    return FENCE.sub(blank, text)


def gates_section(text: str) -> str:
    """The `## Gates` section's own text — from the exact level-2 heading
    (an inline mention or a `### Gates` would otherwise pose as the section
    start) to the next level-2 heading, since stages place `## Notes` after
    it and a lowercase bold bullet there must not read as a gate. Fenced
    code is masked first, so an example carrying the heading is not a
    second section and its bullets are not gates."""
    text = mask_fences(text)
    match = GATES_HEADING.search(text)
    if match is None:
        return ""
    tail = text[match.end() :]
    boundary = tail.find("\n## ")
    return tail if boundary == -1 else tail[:boundary]


def gate_scopes(root: Path) -> dict[str, bool]:
    """Every gate a stage declares, mapped to whether a phase repeats it.

    A stage repeats per phase when its steps write per-phase outputs — `{N}` in
    a declared output artifact — and the gates it declares repeat with it. Read
    from the stage contracts rather than from the records being checked: whether
    a gate needs a `phase` cannot be inferred from whether its records carry
    one, or omitting the field would decide that the field was never required
    and bypass the check it exists for.
    """
    found: dict[str, bool] = {}
    for path in sorted(root.glob("workflows/stages/*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        phased = any(
            isinstance(artifact, str) and "{N}" in artifact
            for artifact in (
                output_artifact(step_of(block))
                for block in yaml_blocks(text, rel, [])
                if step_of(block) is not None
            )
        )
        for match in GATE_HEADING.finditer(gates_section(text)):
            found[match.group("id")] = phased
    return found


def gate_record_problems(at: str, data: Any, gates: dict[str, bool]) -> list[str]:
    """Spec §5.3 and §7: a gate's decision is recorded in `gates` like any other
    outcome, and §10 makes its own `steps` entry `done` only once that decision
    stands. So a gate recorded `done` with no entry has lost the decision — the
    intake gate's especially, since that is what accepted the class `run.risk`
    holds. Only `done` is checked: `blocked` is a gate still waiting, `pending`
    one not yet reached, and `skipped` one that never decided anything.
    """
    if not isinstance(data, dict):
        return []
    # `gates` is appended in decision order (§10), so the last entry naming a
    # gate is its latest — and it is that entry which has to stand, never the
    # best one on file. Filtering the others out first would let a stale accept
    # vouch for a gate whose newest decision was a revise.
    phase = data["run"].get("phase") if isinstance(data.get("run"), dict) else None
    latest: dict[str, Any] = {}
    for record in items_of(data.get("gates")):
        if isinstance(record, dict) and isinstance(record.get("gate"), str):
            latest[record["gate"]] = record
    problems: list[str] = []
    for step in items_of(data.get("steps")):
        if not isinstance(step, dict) or step.get("status") != "done":
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or step_id not in gates:
            continue
        record = latest.get(step_id)
        if record is None:
            problems.append(
                f"{at}: gate `{step_id}` is done and no `gates` entry records its "
                f"outcome — spec §7 keeps every decision"
            )
            continue
        # A gate a phase repeats decides once per phase, so its standing
        # decision is the one taken at the phase now executing. An entry naming
        # another phase, or none — recorded before the run had phases, which a
        # re-cut does not reach back into (§10) — is not this phase's.
        if phase is not None and gates[step_id] and record.get("phase") != phase:
            named = record.get("phase")
            says = f"phase {named}" if named is not None else "no phase"
            problems.append(
                f"{at}: gate `{step_id}` is done at phase {phase} and its latest "
                f"decision records {says} — spec §10 has a decision taken while the "
                f"run is phased name the phase it was taken in"
            )
        elif record.get("outcome") not in ("accept", "reject"):
            problems.append(
                f"{at}: gate `{step_id}` is done and its latest outcome is "
                f"`{record.get('outcome')}` — spec §7 has a `revise` return the gate "
                f"to `pending`, so only an accept or a reject stands"
            )
    return problems


def duplicate_record_problems(at: str, data: Any) -> list[str]:
    """Spec §10: at most one record per step and per gate.

    The schema cannot hold this one. `uniqueItems` compares whole records, so
    `plan-create: done` and `plan-create: pending` are two distinct items and
    both pass, and JSON Schema has no way to say "unique by this property" for
    an open set of ids. It is left to this check for that reason rather than as
    an oversight, and it has no negative fixture for the same reason: an invalid
    fixture here must fail its schema, and a document with duplicate ids does
    not.

    `gates` is deliberately not checked. It carries one entry per decision, so a
    gate decided more than once appears more than once by design (§10).
    """
    counts: dict[str, int] = {}
    for step in items_of(data.get("steps")) if isinstance(data, dict) else []:
        if isinstance(step, dict) and isinstance(step.get("id"), str):
            counts[step["id"]] = counts.get(step["id"], 0) + 1
    return [
        f"{at}: `{step_id}` has {n} records in `steps` — spec §10 keeps at most "
        f"one per step, and resume and `iterations` have no single record to read"
        for step_id, n in sorted(counts.items())
        if n > 1
    ]


def import_record_problems(
    at: str, data: Any, contracts: dict[str, tuple[str, Any]]
) -> list[str]:
    """Spec §8.6 and §10: an import is adoption, and every rule here is a
    cross-field semantic the schema cannot hold.

    Every path `imports` names must be in `artifacts` — §8.2 defines the
    manifest as what the run produced or imported, so an import the manifest
    omits is invisible to every reader that resolves against it. `from` must
    name another run: §8.6 copies from an earlier run's directory, so a run
    importing from itself records lineage that leads nowhere — the string
    comparison is this suite's document-level half, canonical directory
    identity being the executor's (§8.6) — and one run
    only, since a set drawn from several runs holds artifacts that never
    descended from one another and the rewritten headers hide it. §10 keeps
    one entry per imported artifact — two records naming different sources
    for one destination copy is lineage with no single answer, and the
    schema cannot reject it for the same reason it cannot reject a duplicate
    step id: `uniqueItems` compares whole records. And §8.6 keeps the set
    closed over derivation: an imported artifact needs some producing step
    whose required step-output inputs are all imported too, or the set holds
    a certificate of something the run does not hold. Some, not every: an
    output two steps share — creation and revision — descends via either,
    and holding the set to the revision's inputs would refuse the importer
    who leaves the validation report out precisely to have it re-rendered.
    An import matching no declared output at any phase is refused outright:
    §8.2's manifest lists what steps declare, so no conforming source run
    holds such an artifact to copy.
    """
    if not isinstance(data, dict):
        return []
    run = data.get("run")
    run_id = run.get("id") if isinstance(run, dict) else None
    phase = str(run.get("phase", 1)) if isinstance(run, dict) else "1"
    manifest = {x for x in items_of(data.get("artifacts")) if isinstance(x, str)}
    # Output declarations matched as templates, `{N}` standing for any phase:
    # lineage persists, so a phase-2 document may carry phase-1 imports, and
    # resolving `{N}` at `run.phase` would leave those without a producer and
    # wave the closure check off exactly where it should bind. A match hands
    # back the artifact's own phase, which is what the producer's inputs then
    # resolve at; an output with no `{N}` resolves them at the document's.
    templates: list[tuple[re.Pattern[str], Any]] = []
    for _, step in contracts.values():
        output = output_artifact(step)
        if isinstance(output, str):
            # Every `{N}` in one declaration is the same executing phase, so
            # the first occurrence captures and the rest backreference it — a
            # fresh group per occurrence would match impossible paths like
            # `phase-1/report-2.md` and misattribute them to phase 1.
            parts = [re.escape(part) for part in output.split("{N}")]
            expression = parts[0]
            for index, part in enumerate(parts[1:]):
                # Named, because a numeric backreference merges with a digit
                # that starts the next literal: a template ending `{N}0`
                # would build a reference to group ten and fail to compile.
                expression += (
                    "(?P<phase>[1-9][0-9]*)" if index == 0 else "(?P=phase)"
                ) + part
            templates.append((re.compile(expression), step))

    def producing(path: str) -> list[tuple[Any, str]]:
        return [
            (step, match.group(1) if expression.groups else phase)
            for expression, step in templates
            for match in (expression.fullmatch(path),)
            if match
        ]

    problems: list[str] = []
    counts: dict[str, int] = {}
    sources: set[str] = set()
    for record in items_of(data.get("imports")):
        if not isinstance(record, dict):
            continue  # not a usable record; check_fixtures faults it against the schema
        artifact = record.get("artifact")
        if isinstance(artifact, str):
            counts[artifact] = counts.get(artifact, 0) + 1
            if artifact not in manifest:
                problems.append(
                    f"{at}: import {artifact} is not in the manifest — spec §8.6 "
                    f"adds every copy to `artifacts`, which is what readers resolve against"
                )
        source = record.get("from")
        if isinstance(source, str):
            sources.add(source)
            if source == run_id:
                problems.append(
                    f"{at}: import {artifact} names this run (`{source}`) as its "
                    f"source — spec §8.6 copies from an earlier run's directory"
                )
    if len(sources) > 1:
        problems.append(
            f"{at}: imports name {len(sources)} source runs "
            f"({', '.join(sorted(sources))}) — spec §8.6 has a run import from one, "
            f"since artifacts from several never descended from one another"
        )
    problems += [
        f"{at}: import {artifact} has {n} records in `imports` — spec §10 keeps "
        f"one entry per imported artifact, and its lineage has no single source to read"
        for artifact, n in sorted(counts.items())
        if n > 1
    ]
    imported = set(counts)
    for artifact in sorted(imported):
        candidates = producing(artifact)
        if not candidates:
            problems.append(
                f"{at}: import {artifact} matches no step output — spec §8.2's "
                f"manifest lists what steps declare, so no source run produced this"
            )
            continue
        unmet_per_producer = [
            sorted(
                {
                    resolved
                    for entry in items_of(step.get("inputs"))
                    if isinstance(entry, dict)
                    # The step schema defaults `required` to true, so only an
                    # explicit false is optional — reading absence as optional
                    # would wave the closure past a prerequisite the contract
                    # requires.
                    and entry.get("required") is not False
                    and isinstance(entry.get("artifact"), str)
                    and "{P}" not in entry["artifact"]
                    for resolved in (entry["artifact"].replace("{N}", artifact_phase),)
                    if producing(resolved) and resolved not in imported
                }
            )
            for step, artifact_phase in candidates
        ]
        if all(unmet_per_producer):
            missing = min(unmet_per_producer, key=len)
            problems.append(
                f"{at}: import {artifact} arrives without {', '.join(missing)} — "
                f"spec §8.6 keeps an import set closed over some producing step's "
                f"required inputs, or the copy certifies work the run does not hold"
            )
    return problems


STAGE_LINK = re.compile(r"\(stages/([a-z][a-z0-9-]*)\.md\)")


def composed_stage_files(root: Path, workflow: Any) -> set[str] | None:
    """The stage files the named workflow composes, read from its
    by-reference links (spec §6.1) — or None where the workflow cannot be
    resolved, which callers read as "filter nothing" so a document that is
    broken elsewhere still gets best-effort checks.
    """
    if not isinstance(workflow, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", workflow):
        return None
    path = root / "workflows" / f"{workflow}.md"
    if not path.is_file():
        return None
    stages = {
        f"workflows/stages/{match.group(1)}.md"
        for match in STAGE_LINK.finditer(path.read_text(encoding="utf-8"))
    }
    return stages or None


def sequence_members(workflow: Any) -> tuple[list[str], list[str], list[str]]:
    """The step ids, gate ids, and malformed entries of one stage block's
    sequence, in declaration order. Malformed entries are counted rather than
    read: the schema already faults them, and guessing a kind here would
    double-report every fault as a parity problem too."""
    steps: list[str] = []
    gates: list[str] = []
    malformed: list[str] = []
    stage = workflow.get("stage") if isinstance(workflow, dict) else None
    entries = stage.get("sequence") if isinstance(stage, dict) else None
    for entry in items_of(entries):
        step = entry.get("step") if isinstance(entry, dict) else None
        gate = entry.get("gate") if isinstance(entry, dict) else None
        if isinstance(step, str) and gate is None:
            steps.append(step)
        elif isinstance(gate, str) and step is None:
            gates.append(gate)
        else:
            malformed.append(repr(entry))
    return steps, gates, malformed


def check_stage_sequences(root: Path) -> tuple[int, list[str]]:
    """Spec §9.4: a stage that declares members carries exactly one sequence
    block naming every declared step and gate exactly once. The schema sees
    one block at a time, so completeness — sequence against the stage's own
    headings and Gates bullets — is this check's to hold: run-state
    population follows the sequence verbatim, and a member missing from it is
    a record no run could carry. Ids are held unique across stages too:
    workflows concatenate stage sequences into one record list, so an id two
    stages share — or one stage declares twice at the source — duplicates
    the §10 record the moment a workflow composes them."""
    problems: list[str] = []
    checked = 0
    # Member ids accumulate across stages: workflows concatenate stage
    # sequences into one record list, and §10 keeps one record per member
    # there — an id two stages share duplicates the moment they compose,
    # whichever kinds it wears in each.
    owners: dict[str, str] = {}
    stage_slugs = {
        path.stem
        for path in root.glob("workflows/stages/*.md")
        if path.name != "README.md"
    }
    for path in sorted(root.glob("workflows/stages/*.md")):
        if path.name == "README.md":
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        # Structure scans run on the masked text: a heading or bullet inside
        # a fenced example is illustration, not declaration.
        masked = mask_fences(text)
        # A second Gates section would sit past the boundary gates_section
        # returns, its every gate invisible to parity and gate scoping — an
        # incomplete sequence would pass on the strength of what nobody read.
        if len(GATES_HEADING.findall(masked)) > 1:
            problems.append(
                f"{rel}: more than one `## Gates` section — gates past the "
                f"first are invisible to the sequence checks"
            )
        # Lists, not sets: a member declared twice at the source — two
        # identical headings, two identical gate bullets — must surface as
        # the duplicate it is, not be erased before the comparison.
        step_list = [m.group("id") for m in STAGE_STEP_HEADING.finditer(masked)]
        section = gates_section(text)
        gate_list = [m.group("id") for m in GATE_HEADING.finditer(section)]
        # A gate-shaped bullet whose id fails the strict form must not make
        # the file read as declaring nothing: `**Demo-approval**` is a typo
        # to report, and it still marks the file as a stage contract.
        malformed_gates = 0
        for match in GATE_SHAPED.finditer(section):
            if not GATE_HEADING.match(section, match.start()):
                malformed_gates += 1
                problems.append(
                    f"{rel}: gate bullet `{match.group('raw')}` does not match "
                    f"the `- **<id>**` form — ids are lowercase kebab-case "
                    f"(spec §9.4)"
                )
        # A step-contract block owes the well-formed heading nearest above it:
        # with none at all it has no id a sequence could name, and under a
        # malformed one — `### second` without the role — it would silently
        # attribute to the previous valid step and its member could vanish
        # from the sequence while conformance passed. And the association is
        # one-to-one both ways: a heading with no contract is a record the
        # driver has no role or handoff for, and one with two has no single
        # contract to execute.
        headings = [
            (m.start(), m.group("id"), m.group("role"))
            for m in STAGE_STEP_HEADING.finditer(masked)
        ]
        heading_offsets = [start for start, _, _ in headings]
        roles_at = {start: role for start, _, role in headings}
        h3_offsets = [m.start() for m in GENERIC_H3.finditer(masked)]
        h2_offsets = [m.start() for m in GENERIC_H2.finditer(masked)]
        contracts_under: dict[int, int] = {start: 0 for start in heading_offsets}
        step_blocks = 0
        sequence_blocks = []
        for block in yaml_blocks(text, rel, []):
            line = int(block.at.rsplit(":", 1)[1])
            offset = sum(len(x) + 1 for x in text.splitlines(keepends=False)[: line - 1])
            workflow = workflow_value(block.data)
            if isinstance(workflow, dict) and "stage" in workflow:
                sequence_blocks.append(block)
            if not isinstance(workflow, dict) or "step" not in workflow:
                continue
            step_blocks += 1
            nearest_h3 = max((s for s in h3_offsets if s < offset), default=None)
            nearest_valid = max((s for s in heading_offsets if s < offset), default=None)
            nearest_h2 = max((s for s in h2_offsets if s < offset), default=None)
            if nearest_h3 is not None and nearest_h2 is not None and nearest_h2 > nearest_h3:
                # An H2 closes the step section above it — `## Gates`, `## Notes` —
                # so this block sits under no step heading at all, however
                # many valid ones precede it.
                problems.append(
                    f"{block.at}: step block below a `## ` heading that closed "
                    f"the step section above it — it belongs to no step, and no "
                    f"sequence can name it (spec §9.4)"
                )
            elif nearest_h3 is None:
                problems.append(
                    f"{block.at}: step block without a `### <id> (<role>)` heading "
                    f"above it — no sequence can name what has no id (spec §9.4)"
                )
            elif nearest_valid is None or nearest_valid < nearest_h3:
                problems.append(
                    f"{block.at}: step block under a heading that does not match "
                    f"`### <id> (<role>)` — it would attribute to the previous "
                    f"step, and no sequence can name it (spec §9.4)"
                )
            else:
                contracts_under[nearest_valid] += 1
                # The heading is what a human executing the prose reads, the
                # contract what a driver executes: a disagreement about the
                # role hands the same step to two different roles.
                # A schema-invalid `step` value is the schema check's
                # finding; reading a role off it would abort the pass before
                # that finding prints.
                declaration = workflow["step"]
                declared_role = (
                    declaration.get("role") if isinstance(declaration, dict) else None
                )
                if (
                    isinstance(declared_role, str)
                    and declared_role != roles_at[nearest_valid]
                ):
                    problems.append(
                        f"{block.at}: contract declares role `{declared_role}` "
                        f"under a heading that says `{roles_at[nearest_valid]}` — "
                        f"prose and driver would execute it as different roles "
                        f"(spec §9.1)"
                    )
        for start, step_id, _ in headings:
            if contracts_under[start] == 0:
                problems.append(
                    f"{rel}: step `{step_id}` declares no contract block — a "
                    f"sequence names it, and the driver would have no role or "
                    f"handoff to execute (spec §9.1, §9.4)"
                )
            elif contracts_under[start] > 1:
                problems.append(
                    f"{rel}: step `{step_id}` declares {contracts_under[start]} "
                    f"contract blocks — a step has one contract (spec §9.1)"
                )
        for kind, names in (("step", step_list), ("gate", gate_list)):
            for name in sorted({x for x in names if names.count(x) > 1}):
                problems.append(
                    f"{rel}: {kind} `{name}` is declared {names.count(name)} times — "
                    f"population can carry only one record (spec §10)"
                )
        for name in step_list + gate_list:
            # A member wearing a stage's id would make every §9.1 edge naming
            # it ambiguous: a target is an untyped string that may resolve to
            # a member or to a stage's first runnable record.
            if name in stage_slugs:
                problems.append(
                    f"{rel}: member `{name}` carries a stage's id — a §9.1 "
                    f"target naming it could mean the member or the stage "
                    f"(spec §9.4)"
                )
            owner = owners.get(name)
            if owner is not None and owner != rel:
                problems.append(
                    f"{rel}: member `{name}` is also declared by {owner} — a "
                    f"workflow composing both stages would carry two records "
                    f"with one id (spec §10)"
                )
            else:
                owners[name] = rel
        declared_steps = set(step_list)
        declared_gates = set(gate_list)
        blocks = sequence_blocks
        if (
            not declared_steps
            and not declared_gates
            and not blocks
            and not step_blocks
            and not malformed_gates
        ):
            continue  # nothing declared any way; not a stage contract yet
        checked += 1
        if len(blocks) != 1:
            problems.append(
                f"{rel}: {len(blocks)} stage sequence blocks — spec §9.4 has a "
                f"stage declare its members once"
            )
            continue
        steps, gates, malformed = sequence_members(workflow_value(blocks[0].data))
        at = blocks[0].at
        for kind, named, declared in (
            ("step", steps, declared_steps),
            ("gate", gates, declared_gates),
        ):
            for name in sorted(set(named) - declared):
                problems.append(
                    f"{at}: sequence names {kind} `{name}`, which the stage does "
                    f"not declare — spec §9.4 sequences only declared members"
                )
            # A malformed entry could have been any member, so with one in
            # the block the missing-member direction would cascade a parity
            # error onto every name the broken entry might have carried —
            # the schema already faults the entry, and that is the report.
            if malformed:
                continue
            for name in sorted(declared - set(named)):
                problems.append(
                    f"{at}: {kind} `{name}` is missing from the sequence — spec "
                    f"§9.4 names every member, or population cannot carry its record"
                )
            for name in sorted({x for x in named if named.count(x) > 1}):
                problems.append(
                    f"{at}: {kind} `{name}` appears {named.count(name)} times in "
                    f"the sequence — spec §10 keeps one record per member"
                )
        # Across kinds too: a step and a gate sharing a name would populate
        # two `steps` records with one id, which §10 forbids no less for
        # being differently flavored.
        for name in sorted(set(steps) & set(gates)):
            problems.append(
                f"{at}: `{name}` is both a step and a gate in the sequence — "
                f"spec §10 keeps one record per member"
            )
    return checked, problems


def run_workflow(data: Any) -> Any:
    """The document's declared workflow, or None where the shape is not a
    run state at all — the schema check's finding, never this one's."""
    run = data.get("run") if isinstance(data, dict) else None
    return run.get("workflow") if isinstance(run, dict) else None


def composed_member_order(root: Path, workflow: Any) -> tuple[list[str], int] | None:
    """The member ids a workflow's composed stages declare, in composition
    order — §9.4's sequences concatenated, which §10 makes the order of the
    populated `steps` list — with the count the entry stage contributes,
    since §10's pre-acceptance list is that stage's members alone. None
    where the workflow or any stage's sequence cannot be read; a document
    broken elsewhere is not this check's finding.
    """
    if not isinstance(workflow, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", workflow):
        return None
    path = root / "workflows" / f"{workflow}.md"
    if not path.is_file():
        return None
    slugs: list[str] = []
    for match in STAGE_LINK.finditer(path.read_text(encoding="utf-8")):
        if match.group(1) not in slugs:
            slugs.append(match.group(1))
    order: list[str] = []
    entry_count = 0
    for index, slug in enumerate(slugs):
        stage_path = root / "workflows" / "stages" / f"{slug}.md"
        if not stage_path.is_file():
            return None
        text = stage_path.read_text(encoding="utf-8")
        blocks = [
            block
            for block in yaml_blocks(text, stage_path.name, [])
            if isinstance(workflow_value(block.data), dict)
            and "stage" in workflow_value(block.data)
        ]
        if len(blocks) != 1:
            return None
        steps, gates, malformed = sequence_members(workflow_value(blocks[0].data))
        if malformed:
            return None
        stage = workflow_value(blocks[0].data).get("stage")
        if not isinstance(stage, dict):
            return None  # schema-invalid: its own finding, not an order
        for entry in items_of(stage.get("sequence")):
            member = entry.get("step") or entry.get("gate") if isinstance(entry, dict) else None
            if isinstance(member, str):
                order.append(member)
        if index == 0:
            entry_count = len(order)
    return (order, entry_count) if order else None


def record_order_problems(
    at: str, data: Any, composed: tuple[list[str], int] | None
) -> list[str]:
    """Spec §10: the populated `steps` list follows the composed stages'
    sequences, which is what makes §8.5's resume — the first record neither
    done nor skipped — mean what the stages declared. The schema cannot
    constrain id order, so swapping two records would silently change where
    a resume lands; only this check stands between that and a green run.

    Which part of the composition a document owes depends on where it is,
    and `run.risk` is what says which — the class the intake gate accepted,
    absent before and present after. Before that acceptance §10's list is
    the entry stage's members alone, so ids are bounded to that stage and
    read as a subsequence of it: a later stage's member has no record yet,
    the acceptance being the write that creates them. From the acceptance
    onward the list is complete, so a populated state owes every member of
    every composed stage, in the declared order.
    """
    if composed is None or not isinstance(data, dict):
        return []
    order, entry_count = composed
    run = data.get("run") if isinstance(data, dict) else None
    accepted = isinstance(run, dict) and run.get("risk") is not None
    if not accepted:
        # §10: until the intake gate accepts, the list holds the entry
        # stage's records alone — the acceptance is the write that creates
        # the rest, so a later stage's member here is a record nothing wrote.
        order = order[:entry_count]
    recorded = [
        step["id"]
        for step in items_of(data.get("steps"))
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    ]
    problems: list[str] = []
    position = 0
    for step_id in recorded:
        if step_id not in order:
            problems.append(
                f"{at}: step `{step_id}` is not a member "
                + (
                    "any composed stage declares"
                    if accepted
                    else "the entry stage declares, and no class is accepted "
                    "yet — §10's pre-acceptance list is that stage's alone"
                )
                + " (spec §9.4)"
            )
            continue
        index = order.index(step_id)
        if index < position:
            problems.append(
                f"{at}: step `{step_id}` is recorded after `{order[position - 1]}` "
                f"but the composed sequences declare it before — §10's order is "
                f"what §8.5's resume reads (spec §9.4)"
            )
            continue
        position = index + 1
    if accepted:
        missing = [member for member in order if member not in set(recorded)]
        if missing:
            problems.append(
                f"{at}: the accepted class makes the list complete (spec §10) "
                f"and these members have no record: {', '.join(missing)}"
            )
    return problems


def check_manifests(root: Path) -> tuple[int, list[str]]:
    """Every run-state document this repo ships models a state an executor may
    resume from, so a stale manifest in one is a nonconforming example rather
    than a cosmetic slip: §8.5 resumes into a run whose artifacts it can only
    find here."""
    outputs = step_outputs(root)
    gates = gate_scopes(root)
    contracts = stage_steps(root, [])
    problems: list[str] = []
    checked = 0

    def order_problems(at: str, data: Any) -> list[str]:
        """The record-order check, plus the diagnostic that keeps it from
        disabling itself: `run.workflow` is only schema-checked as a
        non-empty string, so a typo would resolve to no composition and
        every membership, completeness, and order rule would pass by
        vacuously. An unresolvable name is the finding instead."""
        workflow = run_workflow(data)
        if workflow is None:
            return []  # not a run state's shape; the schema check reports it
        composed_order = composed_member_order(root, workflow)
        if composed_order is None:
            return [
                f"{at}: run.workflow `{workflow}` names no workflow whose stages "
                f"declare their sequences — §10's order cannot be checked against "
                f"a composition that cannot be read (spec §9.4)"
            ]
        return record_order_problems(at, data, composed_order)

    def composed(at: str, data: Any) -> tuple[dict[str, tuple[str, Any]], list[str]]:
        """The contracts scoped to the document's own workflow: §8.6 bounds
        imports to step outputs of the composed workflow, so a `plan` state
        must not find a producer in a delivery stage it never composes. A
        malformed document (no mapping, no string workflow) is the schema
        check's finding and filters nothing — but a well-formed name that
        resolves to no workflow file is a defect of its own, reported here:
        falling back to every contract would accept a typo's imports against
        producers the run never composes."""
        run = data.get("run") if isinstance(data, dict) else None
        workflow = run.get("workflow") if isinstance(run, dict) else None
        if not isinstance(workflow, str) or not workflow:
            return contracts, []
        stages = composed_stage_files(root, workflow)
        if stages is None:
            return {}, [
                f"{at}: run.workflow `{workflow}` names no workflow that "
                f"composes stages — its imports cannot be checked against any "
                f"composed contract"
            ]
        return {
            step_id: entry
            for step_id, entry in contracts.items()
            if entry[0].rsplit(":", 1)[0] in stages
        }, []
    for kind, path in fixture_paths(root, RUN_STATE):
        if kind != "valid" or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            data = jsonify(YAML_LOADER.load(path.read_text(encoding="utf-8")))
        except YAMLError:
            continue  # check_fixtures reports the parse failure
        checked += 1
        problems += manifest_problems(rel, data, outputs)
        problems += gate_record_problems(rel, data, gates)
        problems += duplicate_record_problems(rel, data)
        problems += order_problems(rel, data)
        if isinstance(data, dict) and data.get("imports"):
            scoped, scope_problems = composed(rel, data)
            problems += scope_problems
            if not scope_problems:
                problems += import_record_problems(rel, data, scoped)
    spec = root / SPEC
    if spec.is_file():
        for block in yaml_blocks(spec.read_text(encoding="utf-8"), SPEC.as_posix(), []):
            if isinstance(block.data, dict) and "run" in block.data:
                checked += 1
                problems += manifest_problems(block.at, block.data, outputs)
                problems += gate_record_problems(block.at, block.data, gates)
                problems += duplicate_record_problems(block.at, block.data)
                problems += order_problems(block.at, block.data)
                if isinstance(block.data, dict) and block.data.get("imports"):
                    scoped, scope_problems = composed(block.at, block.data)
                    problems += scope_problems
                    if not scope_problems:
                        problems += import_record_problems(block.at, block.data, scoped)
    return checked, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repository root to validate (default: this script's repository)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / SCHEMA_DIR).is_dir():
        fail(f"{(root / SCHEMA_DIR)}: not found")
    # jsonschema only asserts `format` for formats whose checker dependency is
    # importable; without this guard a missing rfc3339-validator would silently
    # stop enforcing the schemas' date-time constraints.
    if "date-time" not in Draft202012Validator.FORMAT_CHECKER.checkers:
        fail(
            "date-time format assertion unavailable — "
            "install rfc3339-validator (scripts/requirements.txt)"
        )
    validators = load_schemas(root)

    fixtures, problems = check_fixtures(root, validators)
    examples, spec_problems = check_spec_examples(root, validators)
    blocks, block_problems = check_workflow_blocks(root, validators)
    files, frontmatter_problems = check_frontmatter(root)
    skills, skill_problems = check_skill_budgets(root)
    bound, parity_problems = check_step_parity(root)
    sequences, sequence_problems = check_stage_sequences(root)
    manifests, manifest_faults = check_manifests(root)
    problems += spec_problems + block_problems + frontmatter_problems + skill_problems
    problems += parity_problems + sequence_problems + manifest_faults

    for problem in problems:
        print(problem)
    if problems:
        print(f"conformance: {len(problems)} problem(s)")
        return 1
    print(
        f"conformance: OK — {fixtures} fixtures, {examples} spec examples, "
        f"{blocks} workflow blocks, {files} frontmatter files, {skills} skill bodies, "
        f"{bound} step-bound skills, {sequences} stage sequences, "
        f"{manifests} run-state documents"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
