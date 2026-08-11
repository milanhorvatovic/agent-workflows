#!/usr/bin/env python3
"""Validate the protocol surface against the schemas in protocol/schemas/.

Five checks:

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
  `loop`, `trigger`); unknown sibling keys are tolerated per the 0.x
  degradation rules (spec §9.4). Placeholders in declared strings must be
  spec-defined — {run}, {N}, {machine-checks} — and a declared output
  template must exist relative to the declaring file.
- Frontmatter: roles, workflows, stages, and skills carry an Agent Skills
  conformant `name` (lowercase alphanumeric plus hyphens, ≤64 chars, equal
  to the file slug) and `description` (non-empty, ≤1024 chars); skills
  additionally carry a `license`, so installed copies state their terms
  standalone.
- Skill budget: every `skills/*/SKILL.md` body stays within the 500-line /
  ~5000-token budget.

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

STRUCTURES = ("step", "loop", "trigger")  # metadata.workflow structures, one schema each
RUN_STATE = "run-state"

PLACEHOLDERS = {"run", "N", "machine-checks"}  # spec §8.1 and §9.2
# {token} occurrences; the lookbehind skips ${...} shell expansions in commands.
PLACEHOLDER = re.compile(r"(?<!\$)\{([^{}]*)\}")

YAML_BLOCK = re.compile(r"^```yaml[ \t]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64  # Agent Skills frontmatter cap
DESCRIPTION_MAX = 1024  # Agent Skills frontmatter cap
SKILL_BODY_MAX_LINES = 500
SKILL_BODY_MAX_TOKENS = 5000
CHARS_PER_TOKEN = 4  # rough budget heuristic, matches common tokenizer averages

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
    blocks: list[Block] = []
    for match in YAML_BLOCK.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        at = f"{rel}:{line}"
        try:
            data = jsonify(YAML_LOADER.load(match.group(1)))
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
        blocks = yaml_blocks(text, rel, problems)
        front = frontmatter_block(text, rel)
        if front is not None:
            blocks.append(front)
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


STAGE_STEP_HEADING = re.compile(r"^### (?P<id>[a-z][a-z0-9-]*) \(", re.MULTILINE)


def step_of(block: Block | None) -> Any:
    """The `step` mapping inside a `metadata.workflow`, or None."""
    if block is None:
        return None
    workflow = workflow_value(block.data)
    if isinstance(workflow, dict) and isinstance(workflow.get("step"), dict):
        return workflow["step"]
    return None


def stage_steps(root: Path, problems: list[str]) -> dict[str, tuple[str, Any]]:
    """Every step a stage contract declares, keyed by its `### <id>` heading.

    A stage's fenced block sits under the heading that names the step, so the
    nearest preceding heading is the step id.
    """
    found: dict[str, tuple[str, Any]] = {}
    for path in sorted(root.glob("workflows/stages/*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        headings = [(m.start(), m.group("id")) for m in STAGE_STEP_HEADING.finditer(text)]
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
        skill_out = (step.get("output") or {}).get("artifact")
        stage_out = (declared.get("output") or {}).get("artifact")
        if skill_out != stage_out:
            problems.append(
                f"{rel}: step output artifact differs from the one {at} declares "
                f"for `{step_id}`; two copies of one contract must agree"
            )
    return checked, problems


def step_outputs(root: Path) -> dict[str, str]:
    """Every step-bound skill's declared output artifact, keyed by step id."""
    found: dict[str, str] = {}
    for path in sorted(root.glob("skills/*/SKILL.md")):
        rel = path.relative_to(root).as_posix()
        step = step_of(frontmatter_block(path.read_text(encoding="utf-8"), rel))
        if step is None:
            continue
        artifact = (step.get("output") or {}).get("artifact")
        if isinstance(artifact, str):
            found[path.parent.name.removeprefix("awf-")] = artifact
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
    manifest = {x for x in (data.get("artifacts") or []) if isinstance(x, str)}
    problems: list[str] = []
    for step in data.get("steps") or []:
        if not isinstance(step, dict) or step.get("status") != "done":
            continue
        artifact = outputs.get(step.get("id"))
        if artifact is None:
            continue  # a gate, or a step no skill declares
        resolved = artifact.replace("{N}", str(phase))
        if resolved not in manifest:
            problems.append(
                f"{at}: `{step['id']}` is done and its output {resolved} is not in "
                f"the manifest — spec §8.2 has the executor keep it current"
            )
    return problems


def check_manifests(root: Path) -> tuple[int, list[str]]:
    """Every run-state document this repo ships models a state an executor may
    resume from, so a stale manifest in one is a nonconforming example rather
    than a cosmetic slip: §8.5 resumes into a run whose artifacts it can only
    find here."""
    outputs = step_outputs(root)
    problems: list[str] = []
    checked = 0
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
    spec = root / SPEC
    if spec.is_file():
        for block in yaml_blocks(spec.read_text(encoding="utf-8"), SPEC.as_posix(), []):
            if isinstance(block.data, dict) and "run" in block.data:
                checked += 1
                problems += manifest_problems(block.at, block.data, outputs)
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
    manifests, manifest_faults = check_manifests(root)
    problems += spec_problems + block_problems + frontmatter_problems + skill_problems
    problems += parity_problems + manifest_faults

    for problem in problems:
        print(problem)
    if problems:
        print(f"conformance: {len(problems)} problem(s)")
        return 1
    print(
        f"conformance: OK — {fixtures} fixtures, {examples} spec examples, "
        f"{blocks} workflow blocks, {files} frontmatter files, {skills} skill bodies, "
        f"{bound} step-bound skills, {manifests} run-state manifests"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
