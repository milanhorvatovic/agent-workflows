"""Unit tests for validate_conformance.py.

Run from the repo root: python3 -m unittest discover -s scripts
(requires scripts/requirements.txt installed)
"""

from __future__ import annotations

import contextlib
import io
import re
import json
import tempfile
import unittest
from pathlib import Path

import validate_conformance

PROTOCOL = {"type": "string", "pattern": "^[0-9]+\\.[0-9]+$"}

# Trimmed mirrors of the real schemas — enough structure to exercise every
# validator path (required keys, enums, additionalProperties rejection, the
# `on` key, string-typed timestamps) without coupling tests to schema content.
STEP_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["protocol", "step"],
    "properties": {
        "protocol": PROTOCOL,
        "step": {
            "type": "object",
            "additionalProperties": False,
            "required": ["role", "output"],
            "properties": {
                "role": {"enum": ["analyst", "planner", "implementer", "validator"]},
                "inputs": {"type": "array"},
                "output": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["artifact"],
                    "properties": {
                        # {P} resolves to one path per phase and a step produces
                        # one artifact, so the real schema forbids it here.
                        "artifact": {"type": "string", "not": {"pattern": r"\{P\}"}},
                        "template": {"type": "string"},
                    },
                },
                "on": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["PASS", "FAIL"],
                    "properties": {
                        "PASS": {"type": "string"},
                        "PASS_WITH_CONDITIONS": {"type": "string"},
                        "FAIL": {"type": "string"},
                    },
                },
            },
        },
    },
}

LOOP_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["protocol", "loop"],
    "properties": {
        "protocol": PROTOCOL,
        "loop": {
            "type": "object",
            "additionalProperties": False,
            "required": ["exit_criteria", "max_iterations"],
            "properties": {
                "exit_criteria": {"type": "array"},
                "max_iterations": {"type": "integer"},
            },
        },
    },
}

TRIGGER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["protocol", "trigger"],
    "properties": {
        "protocol": PROTOCOL,
        "trigger": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"enum": ["manual", "interval"]},
                "until": {"type": "object"},
            },
        },
    },
}

STAGE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["protocol", "stage"],
    "properties": {
        "protocol": PROTOCOL,
        "stage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["sequence"],
            "properties": {
                "sequence": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "step": {"type": "string"},
                            "gate": {"type": "string"},
                            "conditional": {"const": True},
                        },
                        "oneOf": [{"required": ["step"]}, {"required": ["gate"]}],
                    },
                }
            },
        },
    },
}

RUN_STATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["run", "gates"],
    "properties": {
        "run": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "workflow": {"type": "string"},
                "phase": {"type": "integer"},
            },
        },
        # Enough of the real shape for the manifest check to have something to
        # read; the schema itself is exercised by its own fixtures.
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "status"],
                "properties": {
                    "id": {"type": "string"},
                    "status": {"type": "string"},
                    "iterations": {"type": "integer"},
                },
            },
        },
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "gates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["gate", "at"],
                "properties": {
                    "gate": {"type": "string"},
                    "outcome": {"enum": ["accept", "revise", "reject"]},
                    "phase": {"type": "integer", "minimum": 1},
                    "at": {"type": "string", "format": "date-time"},
                },
            },
        },
        "imports": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["artifact", "from", "at"],
                "properties": {
                    "artifact": {"type": "string"},
                    "from": {"type": "string"},
                    "at": {"type": "string", "format": "date-time"},
                },
            },
        },
    },
}

STEP_BLOCK = """\
```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
      output:
        artifact: "{run}/grounding.md"
      on:
        PASS: next-step
        FAIL: revise-step
```
"""

TRIGGER_BLOCK = """\
```yaml
metadata:
  workflow:
    protocol: "0.2"
    trigger:
      kind: manual
```
"""

# The run-state example deliberately carries an unquoted timestamp: ruamel
# resolves it to datetime, and validation succeeds only through jsonify().
SPEC = f"""\
# Spec

A step example:

{STEP_BLOCK}
A run-state example:

```yaml
run:
  id: 2026-08-03-demo
gates:
  - gate: intake
    at: 2026-08-03T14:12:00Z
```
"""


def frontmatter(name: str, description: str = "A description.") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"


def stage_file(block: str) -> str:
    """A well-formed scratch stage: one heading, the block under it, and the
    §9.4 sequence naming the one member — the shape every stage now owes."""
    return (
        frontmatter("build")
        + "\n### builder (analyst)\n\nProse.\n\n"
        + block
        + "\n```yaml\nmetadata:\n  workflow:\n    protocol: \"0.2\"\n"
        + "    stage:\n      sequence:\n        - step: builder\n```\n"
    )


def skill_frontmatter(name: str, extra: str = "license: MIT\n") -> str:
    return f"---\nname: {name}\ndescription: A description.\n{extra}---\n\n# {name}\n"


# A step block declared in Agent Skills frontmatter — the skill-tier
# counterpart of STEP_BLOCK, template included (skills own their templates).
SKILL_WORKFLOW = """\
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
      output:
        artifact: "{run}/grounding.md"
        template: references/g.template.md
"""


class ValidateConformanceTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, schema in (
            ("step", STEP_SCHEMA),
            ("loop", LOOP_SCHEMA),
            ("trigger", TRIGGER_SCHEMA),
            ("stage", STAGE_SCHEMA),
            ("run-state", RUN_STATE_SCHEMA),
        ):
            self.write(f"protocol/schemas/{name}.schema.json", json.dumps(schema))
        self.write(
            "protocol/schemas/examples/stage.valid.yaml",
            'protocol: "0.2"\nstage:\n  sequence:\n    - step: thing\n',
        )
        self.write(
            "protocol/schemas/examples/stage.invalid.yaml",
            'protocol: "0.2"\nstage:\n  sequence:\n    - step: thing\n      gate: also-a-gate\n',
        )
        self.write(
            "protocol/schemas/examples/step.valid.yaml",
            'protocol: "0.2"\nstep:\n  role: analyst\n  output:\n    artifact: "{run}/a.md"\n',
        )
        self.write(
            "protocol/schemas/examples/step.invalid.yaml",
            'protocol: "0.2"\nstep:\n  role: orchestrator\n',
        )
        self.write(
            "protocol/schemas/examples/loop.valid.yaml",
            'protocol: "0.2"\nloop:\n  exit_criteria: []\n  max_iterations: 3\n',
        )
        self.write(
            "protocol/schemas/examples/loop.invalid.yaml",
            'protocol: "0.2"\nloop:\n  exit_criteria: []\n',
        )
        self.write(
            "protocol/schemas/examples/trigger.valid.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: manual\n',
        )
        self.write(
            "protocol/schemas/examples/trigger.invalid.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: quantum\n',
        )
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            'run:\n  id: demo\ngates: []\n',
        )
        self.write(
            "protocol/schemas/examples/run-state.invalid.yaml",
            'run:\n  id: demo\ngates: []\nsurprise: true\n',
        )
        self.write("protocol/spec.md", SPEC)
        self.write("roles/analyst.md", frontmatter("analyst"))
        self.write("workflows/demo.md", frontmatter("demo") + "\n" + TRIGGER_BLOCK)
        self.write("workflows/stages/build.md", stage_file(STEP_BLOCK))

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_main(self) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = validate_conformance.main(["--root", str(self.root)])
        return code, stdout.getvalue()

    def run_main_expecting_exit(self) -> str:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                validate_conformance.main(["--root", str(self.root)])
        return str(caught.exception.code)

    def assert_problem(self, fragment: str) -> str:
        code, output = self.run_main()
        self.assertEqual(code, 1, output)
        self.assertIn(fragment, output)
        return output

    # A fully valid tree passes, and the summary proves the checks matched
    # real content. This is also the YAML 1.2 regression guard: the step
    # blocks carry `on:` keys, which a YAML 1.1 loader would read as boolean
    # true and fail against additionalProperties: false — and the spec's
    # run-state example carries an unquoted timestamp that validates only
    # after datetime-to-string conversion.
    def test_valid_tree_passes_with_tallies(self) -> None:
        code, output = self.run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("conformance: OK", output)
        self.assertIn("10 fixtures", output)
        self.assertIn("2 spec examples", output)
        self.assertIn("3 workflow blocks", output)
        self.assertIn("3 frontmatter files", output)
        self.assertIn("1 stage sequences", output)

    def test_schema_violation_in_workflow_block_reported_with_location(self) -> None:
        broken = STEP_BLOCK.replace("role: analyst", "role: analyst\n      rogue: true")
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + broken)
        output = self.assert_problem("workflows/stages/build.md:8")
        self.assertIn("[step]", output)
        self.assertIn("rogue", output)

    def test_block_declaring_no_structure_reported(self) -> None:
        self.write(
            "workflows/demo.md",
            frontmatter("demo") + '\n```yaml\nmetadata:\n  workflow:\n    protocol: "0.2"\n```\n',
        )
        self.assert_problem("declares none of: step, loop, trigger")

    def test_non_mapping_workflow_value_reported(self) -> None:
        self.write(
            "workflows/demo.md",
            frontmatter("demo") + "\n```yaml\nmetadata:\n  workflow: soon\n```\n",
        )
        self.assert_problem("metadata.workflow is not a mapping")

    def test_unparseable_yaml_block_reported(self) -> None:
        self.write(
            "workflows/demo.md",
            frontmatter("demo") + "\n```yaml\nmetadata: [unclosed\n```\n" + TRIGGER_BLOCK,
        )
        self.assert_problem("workflows/demo.md:8: yaml block does not parse")

    def test_yaml_blocks_without_workflow_metadata_are_ignored(self) -> None:
        self.write(
            "workflows/demo.md",
            frontmatter("demo") + "\n```yaml\n- just\n- a list\n```\n" + TRIGGER_BLOCK,
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_no_workflow_blocks_anywhere_reported(self) -> None:
        self.write("workflows/demo.md", frontmatter("demo"))
        self.write("workflows/stages/build.md", frontmatter("build"))
        self.assert_problem("no metadata.workflow blocks found")

    def test_unrecognized_spec_example_reported(self) -> None:
        self.write("protocol/spec.md", SPEC + "\n```yaml\nnot: recognized\n```\n")
        self.assert_problem("unrecognized example")

    def test_spec_without_examples_reported(self) -> None:
        self.write("protocol/spec.md", "# Spec\n\nNo examples.\n")
        self.assert_problem("no embedded yaml examples found")

    def test_invalid_spec_run_state_example_reported(self) -> None:
        self.write(
            "protocol/spec.md",
            SPEC.replace("gate: intake", "gate: intake\n    rogue: true"),
        )
        output = self.assert_problem("protocol/spec.md")
        self.assertIn("[run-state]", output)

    def test_invalid_timestamp_fails_date_time_format(self) -> None:
        self.write(
            "protocol/spec.md",
            SPEC.replace("at: 2026-08-03T14:12:00Z", 'at: "not-a-timestamp"'),
        )
        output = self.assert_problem("[run-state]")
        self.assertIn("not-a-timestamp", output)

    def test_timezone_less_timestamp_fails_date_time_format(self) -> None:
        # A naive YAML timestamp serializes without a UTC offset, which RFC
        # 3339 date-time requires — run-state timestamps must carry a zone.
        self.write(
            "protocol/spec.md",
            SPEC.replace("at: 2026-08-03T14:12:00Z", "at: 2026-08-03T14:12:00"),
        )
        self.assert_problem("[run-state]")

    def test_valid_fixture_failing_its_schema_reported(self) -> None:
        self.write(
            "protocol/schemas/examples/trigger.valid.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: quantum\n',
        )
        output = self.assert_problem("trigger.valid.yaml")
        self.assertIn("[trigger]", output)

    def test_invalid_fixture_passing_its_schema_reported(self) -> None:
        self.write(
            "protocol/schemas/examples/trigger.invalid.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: manual\n',
        )
        self.assert_problem("the negative test proves nothing")

    def test_missing_fixture_reported(self) -> None:
        (self.root / "protocol/schemas/examples/loop.invalid.yaml").unlink()
        self.assert_problem("loop.invalid.yaml: fixture missing")

    def test_valid_variant_fixture_is_validated(self) -> None:
        # A schema whose document has more than one legal shape proves the
        # extra shape with a `<name>.valid.<variant>.yaml`, and that fixture
        # is validated like the required one rather than merely present.
        self.write(
            "protocol/schemas/examples/trigger.valid.manual.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: quantum\n',
        )
        output = self.assert_problem("trigger.valid.manual.yaml")
        self.assertIn("[trigger]", output)

    def test_invalid_variant_fixture_must_still_fail_its_schema(self) -> None:
        # An invalid variant carries one fault so it covers one rule. A variant
        # that validates proves nothing, exactly as the required pair's does.
        self.write(
            "protocol/schemas/examples/trigger.invalid.pairing.yaml",
            'protocol: "0.2"\ntrigger:\n  kind: manual\n',
        )
        self.assert_problem("the negative test proves nothing")

    def test_valid_variant_fixture_counts_toward_the_tally(self) -> None:
        # A conforming variant does not fail the run, and the summary counts
        # it — otherwise a fixture could be silently ignored rather than checked.
        source = (
            self.root / "protocol/schemas/examples/run-state.valid.yaml"
        ).read_text(encoding="utf-8")
        _, before = self.run_main()
        self.write("protocol/schemas/examples/run-state.valid.copy.yaml", source)
        code, after = self.run_main()
        self.assertEqual(code, 0, after)
        self.assertEqual(self.fixture_tally(after), self.fixture_tally(before) + 1)

    @staticmethod
    def fixture_tally(output: str) -> int:
        match = re.search(r"(\d+) fixtures", output)
        assert match is not None, output
        return int(match.group(1))

    def test_unknown_placeholder_reported(self) -> None:
        self.write(
            "workflows/stages/build.md",
            frontmatter("build") + "\n" + STEP_BLOCK.replace("{run}/brief.md", "{phase}/brief.md"),
        )
        self.assert_problem('unknown placeholder "{phase}"')

    def test_the_completed_phase_placeholder_is_known(self) -> None:
        """`{P}` joins `{N}` in the vocabulary: one artifact per completed phase,
        for the stages that run after the last one and for a step reading what
        the phases behind it bound."""
        self.write(
            "workflows/stages/build.md",
            stage_file(STEP_BLOCK.replace("{run}/brief.md", "{run}/phase-{P}-impl-log.md")),
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_phase_set_output_is_reported(self) -> None:
        """A step produces one artifact, so `{P}` — one path per phase — cannot
        name an output. Held by the step schema rather than by this script, so
        any standard validator catches it too, and with a negative fixture of
        its own like every other schema rule here."""
        self.write(
            "workflows/stages/build.md",
            frontmatter("build")
            + "\n"
            + STEP_BLOCK.replace('artifact: "{run}/grounding.md"', 'artifact: "{run}/phase-{P}-x.md"'),
        )
        self.assert_problem("should not be valid")

    def test_artifacts_placeholder_rejected_with_spec_pointer(self) -> None:
        block = STEP_BLOCK.replace("{run}/brief.md", "{artifacts}/runs/x/brief.md")
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + block)
        output = self.assert_problem('"{artifacts}" is resolved by the executor')
        self.assertIn("relative to {run}", output)

    def test_shell_parameter_expansion_is_not_a_placeholder(self) -> None:
        block = (
            "```yaml\n"
            "metadata:\n"
            "  workflow:\n"
            '    protocol: "0.2"\n'
            "    loop:\n"
            "      exit_criteria:\n"
            '        - command: "echo ${HOME}"\n'
            "      max_iterations: 2\n"
            "```\n"
        )
        self.write("workflows/demo.md", frontmatter("demo") + "\n" + TRIGGER_BLOCK + "\n" + block)
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_missing_template_reported(self) -> None:
        block = STEP_BLOCK.replace(
            'artifact: "{run}/grounding.md"',
            'artifact: "{run}/grounding.md"\n        template: references/g.template.md',
        )
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + block)
        self.assert_problem("declared template not found: references/g.template.md")

    def test_existing_template_passes(self) -> None:
        block = STEP_BLOCK.replace(
            'artifact: "{run}/grounding.md"',
            'artifact: "{run}/grounding.md"\n        template: references/g.template.md',
        )
        self.write("workflows/stages/build.md", stage_file(block))
        self.write("workflows/stages/references/g.template.md", "# template\n")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_absolute_template_path_rejected_even_when_it_exists(self) -> None:
        self.write("abs.template.md", "# exists outside the declaring dir\n")
        absolute = str(self.root / "abs.template.md")
        block = STEP_BLOCK.replace(
            'artifact: "{run}/grounding.md"',
            f'artifact: "{{run}}/grounding.md"\n        template: "{absolute}"',
        )
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + block)
        self.assert_problem("declared template must be relative to the declaring file")

    def test_template_escaping_declaring_directory_rejected(self) -> None:
        self.write("workflows/shared.template.md", "# exists, but outside stages/\n")
        block = STEP_BLOCK.replace(
            'artifact: "{run}/grounding.md"',
            'artifact: "{run}/grounding.md"\n        template: ../shared.template.md',
        )
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + block)
        self.assert_problem("declared template escapes the declaring file's directory")

    def test_spec_example_templates_are_not_existence_checked(self) -> None:
        block = STEP_BLOCK.replace(
            'artifact: "{run}/grounding.md"',
            'artifact: "{run}/grounding.md"\n        template: references/nowhere.template.md',
        )
        self.write("protocol/spec.md", SPEC + "\nAnother example:\n\n" + block)
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_frontmatter_name_mismatching_slug_reported(self) -> None:
        self.write("roles/analyst.md", frontmatter("analyzer"))
        self.assert_problem("name 'analyzer' does not match the file slug 'analyst'")

    def test_skill_name_uses_directory_slug(self) -> None:
        self.write("skills/demo-skill/SKILL.md", skill_frontmatter("demo-skill"))
        code, output = self.run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("1 skill bodies", output)

    def test_skill_missing_license_reported(self) -> None:
        self.write("skills/demo-skill/SKILL.md", skill_frontmatter("demo-skill", extra=""))
        self.assert_problem("skills/demo-skill/SKILL.md: frontmatter has no license")

    def test_skill_blank_license_reported(self) -> None:
        self.write("skills/demo-skill/SKILL.md", skill_frontmatter("demo-skill", 'license: ""\n'))
        self.assert_problem("skills/demo-skill/SKILL.md: frontmatter has no license")

    def test_frontmatter_workflow_block_validated_and_tallied(self) -> None:
        self.write(
            "skills/demo-skill/SKILL.md",
            skill_frontmatter("demo-skill", "license: MIT\n" + SKILL_WORKFLOW),
        )
        self.write("skills/demo-skill/references/g.template.md", "# template\n")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("4 workflow blocks", output)

    def test_frontmatter_workflow_schema_violation_reported_at_line_one(self) -> None:
        broken = SKILL_WORKFLOW.replace("role: analyst", "role: analyst\n      rogue: true")
        self.write(
            "skills/demo-skill/SKILL.md",
            skill_frontmatter("demo-skill", "license: MIT\n" + broken),
        )
        self.write("skills/demo-skill/references/g.template.md", "# template\n")
        output = self.assert_problem("skills/demo-skill/SKILL.md:1")
        self.assertIn("[step]", output)
        self.assertIn("rogue", output)

    def test_frontmatter_workflow_template_missing_reported(self) -> None:
        self.write(
            "skills/demo-skill/SKILL.md",
            skill_frontmatter("demo-skill", "license: MIT\n" + SKILL_WORKFLOW),
        )
        self.assert_problem("declared template not found: references/g.template.md")

    def test_frontmatter_workflow_template_escaping_skill_directory_rejected(self) -> None:
        self.write("skills/shared.template.md", "# exists, but outside the skill directory\n")
        escaped = SKILL_WORKFLOW.replace("references/g.template.md", "../shared.template.md")
        self.write(
            "skills/demo-skill/SKILL.md",
            skill_frontmatter("demo-skill", "license: MIT\n" + escaped),
        )
        self.assert_problem("declared template escapes the declaring file's directory")

    def test_unparseable_frontmatter_reported_once_by_frontmatter_check(self) -> None:
        self.write("skills/demo-skill/SKILL.md", "---\nname: [unclosed\n---\n\n# demo\n")
        output = self.assert_problem("frontmatter does not parse")
        self.assertEqual(output.count("skills/demo-skill/SKILL.md"), 1, output)

    def test_uppercase_frontmatter_name_reported(self) -> None:
        self.write("roles/analyst.md", frontmatter("Analyst"))
        self.assert_problem("not lowercase-alphanumeric-with-hyphens")

    def test_overlong_frontmatter_name_reported(self) -> None:
        long_name = "a" * 65
        self.write("roles/analyst.md", frontmatter(long_name))
        self.assert_problem("name is 65 chars")

    def test_missing_frontmatter_reported(self) -> None:
        self.write("roles/analyst.md", "# no frontmatter\n")
        self.assert_problem("roles/analyst.md: no frontmatter block")

    def test_missing_description_reported(self) -> None:
        self.write("roles/analyst.md", "---\nname: analyst\n---\n")
        self.assert_problem("roles/analyst.md: frontmatter has no description")

    def test_overlong_description_reported(self) -> None:
        self.write("roles/analyst.md", frontmatter("analyst", "d" * 1025))
        self.assert_problem("description is 1025 chars")

    def test_readme_files_skip_frontmatter_checks(self) -> None:
        self.write("roles/README.md", "# roles/\n")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_skill_body_over_line_budget_reported(self) -> None:
        body = "line\n" * 501
        self.write("skills/big/SKILL.md", frontmatter("big") + body)
        self.assert_problem("body is 503 lines, budget is 500")

    def test_skill_body_over_token_budget_reported(self) -> None:
        body = ("x" * 100 + "\n") * 210  # ~5300 tokens in ~211 lines
        self.write("skills/dense/SKILL.md", frontmatter("dense") + body)
        self.assert_problem("tokens, budget is 5000")


    # A step-bound skill restates its stage's step block; the two copies are
    # one contract and must agree (spec §9.1).

    STAGE = """---
name: demo
description: A stage.
---

# Stage: demo

### thing (analyst)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/b.md"
      on:
        PASS: next-step
        FAIL: fix-step
```

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: thing
```
"""

    SKILL = """---
name: awf-thing
description: A description.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/a.md"
          required: %s
      output:
        artifact: "{run}/b.md"
        template: references/t.template.md
      on:
        PASS: next-step
        FAIL: fix-step
---

# awf-thing
"""

    def write_pair(self, required: str = "true") -> None:
        self.write("workflows/stages/demo.md", self.STAGE)
        self.write("skills/awf-thing/SKILL.md", self.SKILL % required)
        self.write("skills/awf-thing/references/t.template.md", "# t\n")

    def test_matching_step_blocks_pass(self) -> None:
        self.write_pair()
        code, output = self.run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("step-bound skills", output)

    def test_step_input_drift_reported(self) -> None:
        self.write_pair(required="false")
        self.assert_problem("step `inputs` differs from the one")

    def test_skill_template_is_not_drift(self) -> None:
        """The stage cannot carry a skill-relative template path, so the
        skill declaring one is structure rather than drift."""
        self.write_pair()
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_standalone_skill_lends_its_output_to_no_run_state_record(self) -> None:
        """A standalone skill is not a step of any composed workflow, so a
        run-state record sharing its id must not be held to its output — the
        manifest rule applies to what the stages compose, and reading the map
        out of `skills/` would have let any of them lend an artifact to a run
        that never ran it."""
        self.write("skills/awf-loner/SKILL.md", self.SKILL.replace("awf-thing", "awf-loner") % "true")
        self.write("skills/awf-loner/references/t.template.md", "# t\n")
        self.write_run_state("  - id: loner\n    status: done\n", " []")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_standalone_skill_without_a_stage_is_skipped(self) -> None:
        self.write("skills/awf-loner/SKILL.md", self.SKILL.replace("awf-thing", "awf-loner") % "true")
        self.write("skills/awf-loner/references/t.template.md", "# t\n")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_missing_schema_file_exits(self) -> None:
        (self.root / "protocol/schemas/trigger.schema.json").unlink()
        message = self.run_main_expecting_exit()
        self.assertIn("missing schemas: trigger", message)

    def test_malformed_schema_file_exits(self) -> None:
        self.write("protocol/schemas/step.schema.json", "{not json")
        message = self.run_main_expecting_exit()
        self.assertIn("step.schema.json: not a valid schema", message)

    def test_missing_schema_directory_exits(self) -> None:
        message = self.run_main_expecting_exit_with_root(self.root / "elsewhere")
        self.assertIn("not found", message)

    # ---- stage sequences (spec §9.4) ----

    def test_a_stage_with_a_complete_sequence_passes_and_tallies(self) -> None:
        self.write("workflows/stages/demo.md", self.STAGE)
        code, output = self.run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("2 stage sequences", output)

    def test_an_orphaned_step_block_is_reported(self) -> None:
        """A step contract above the first heading has no id a sequence could
        name — skipping it silently would let a stage with contracts but
        malformed headings bypass §9.4 as "declaring nothing"."""
        self.write("workflows/stages/demo.md", frontmatter("demo") + "\n" + STEP_BLOCK)
        self.assert_problem("step block without a `### <id> (<role>)` heading")

    def test_a_second_gates_section_is_reported(self) -> None:
        """Gates past the first section sit beyond the boundary the scan
        returns — invisible to parity, so the file is refused instead."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE + "\n## Gates\n\n- **extra-gate** — unseen.\n",
        )
        self.assert_problem("more than one `## Gates` section")

    def test_a_stage_declaring_members_without_a_sequence_is_reported(self) -> None:
        """§9.4 has every member-declaring stage carry the sequence: run-state
        population follows it verbatim, so a stage without one is a stage no
        run can be populated from."""
        self.write(
            "workflows/stages/demo.md",
            self.STAGE.replace("\n```yaml\nmetadata:\n  workflow:\n    protocol: \"0.2\"\n    stage:\n      sequence:\n        - step: thing\n```\n", ""),
        )
        self.assert_problem("0 stage sequence blocks")

    def test_a_sequence_missing_a_declared_member_is_reported(self) -> None:
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE.replace("        - gate: demo-approval\n", "        - gate: other-gate\n").replace(
                "- **demo-approval** — collects the human decision.",
                "- **demo-approval** — collects the human decision.\n- **other-gate** — another decision.",
            ),
        )
        self.assert_problem("gate `demo-approval` is missing from the sequence")

    def test_a_sequence_naming_an_undeclared_member_is_reported(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            self.STAGE.replace(
                "      sequence:\n        - step: thing\n",
                "      sequence:\n        - step: thing\n        - step: phantom\n",
            ),
        )
        self.assert_problem("sequence names step `phantom`, which the stage does not declare")

    def test_an_inline_gates_mention_does_not_start_the_section(self) -> None:
        """Only the exact level-2 heading opens the Gates section: a prose
        mention of `## Gates` — or a `### Gates`, which contains the same
        substring — must not make the real heading read as the boundary and
        every actual gate as undeclared."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE.replace(
                "# Stage: gated\n",
                "# Stage: gated\n\nProse that mentions `## Gates` inline.\n\n"
                "### Gates prelude\n\nMore prose.\n",
            ),
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_fenced_gates_example_is_not_a_second_section(self) -> None:
        """A `## Gates` line inside a fenced example is illustration: the
        raw scan would count it as a real section and reject the stage as
        carrying two, or read its bullets into parity."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE + "\n## Notes\n\nAn example:\n\n"
            "```markdown\n## Gates\n\n- **fake-gate** — an example bullet.\n```\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_step_block_under_a_malformed_heading_is_reported(self) -> None:
        """After one valid heading, a block under `### second` (no role)
        would silently attribute to the previous step and its member could
        vanish from the sequence — the nearest heading above a step block
        must itself be well-formed."""
        self.write(
            "workflows/stages/demo.md",
            self.STAGE
            + "\n### second\n\nProse.\n\n"
            + "```yaml\nmetadata:\n  workflow:\n    protocol: \"0.2\"\n"
            + "    step:\n      role: analyst\n      output:\n"
            + "        artifact: \"{run}/second.md\"\n```\n",
        )
        self.assert_problem("under a heading that does not match")

    def test_a_bold_bullet_in_notes_is_not_a_gate(self) -> None:
        """The gate scan is bounded to the Gates section: stages place
        `## Notes` after it, and a lowercase bold bullet there must not make
        a complete sequence fail parity."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE
            + "\n## Notes\n\n- **run-state** — a bold term, not a gate.\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_malformed_entry_does_not_cascade_parity_errors(self) -> None:
        """A both-kinds entry could have been any member, so the schema error
        it already earns must not be joined by a missing-member report for
        every name the broken entry might have carried."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE.replace(
                "        - gate: demo-approval\n",
                "        - gate: demo-approval\n          step: also-a-step\n",
            ),
        )
        code, output = self.run_main()
        self.assertEqual(code, 1, output)
        self.assertIn("[stage]", output)
        self.assertNotIn("missing from the sequence", output)

    def test_a_member_declared_twice_at_the_source_is_reported(self) -> None:
        """Sets would erase a doubled heading before the parity comparison —
        the source declares the member twice, and population can carry only
        one record for it."""
        self.write(
            "workflows/stages/demo.md",
            self.STAGE.replace(
                "### thing (analyst)",
                "### thing (analyst)\n\nProse.\n\n### thing (analyst)",
            ),
        )
        self.assert_problem("step `thing` is declared 2 times")

    def test_a_member_shared_across_stages_is_reported(self) -> None:
        """Workflows concatenate stage sequences into one record list, so an
        id two stages share duplicates the §10 record the moment they
        compose — each stage passing alone proves nothing about the pair."""
        self.write("workflows/stages/demo.md", self.STAGE)
        self.write(
            "workflows/stages/second.md",
            self.STAGE.replace("name: demo", "name: second").replace(
                "# Stage: demo", "# Stage: second"
            ),
        )
        self.assert_problem("member `thing` is also declared by workflows/stages/demo.md")

    def test_a_name_shared_across_kinds_is_reported(self) -> None:
        """A step and a gate sharing a name would populate two `steps`
        records with one id — §10 forbids that no less for the two being
        differently flavored, and the per-kind duplicate checks cannot see
        across the kinds."""
        self.write(
            "workflows/stages/gated.md",
            self.GATED_STAGE.replace("# Stage: gated", "# Stage: gated\n\n### demo-approval (analyst)\n\nProse.\n").replace(
                "      sequence:\n        - gate: demo-approval\n",
                "      sequence:\n        - step: demo-approval\n        - gate: demo-approval\n",
            ),
        )
        self.assert_problem("`demo-approval` is both a step and a gate")

    def test_a_duplicate_sequence_member_is_reported(self) -> None:
        """§10 keeps one record per member, and the sequence is the record
        order population follows — a member named twice is two records."""
        self.write(
            "workflows/stages/demo.md",
            self.STAGE.replace(
                "      sequence:\n        - step: thing\n",
                "      sequence:\n        - step: thing\n        - step: thing\n",
            ),
        )
        self.assert_problem("step `thing` appears 2 times in the sequence")

    # ---- run-state documents (spec §8.2, §7, §10) ----

    # A stage, not a skill: the manifest check reads what composes the
    # workflow, so a step it should know about has to be declared by one.
    PHASED_STAGE = """---
name: phased
description: A stage whose step output carries the phase placeholder.
---

# Stage: phased

### phased (planner)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: planner
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-plan.md"
```

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: phased
```
"""

    def write_run_state(
        self, steps: str, artifacts: str, run: str = "", extra: str = ""
    ) -> None:
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            f"run:\n  id: demo\n{run}steps:\n{steps}gates: []\n"
            f"artifacts:{artifacts}\n{extra}",
        )

    def test_done_step_output_missing_from_the_manifest_is_reported(self) -> None:
        self.write_pair()
        self.write_run_state("  - id: thing\n    status: done\n", " []")
        self.assert_problem("`thing` is done and its output {run}/b.md is not in the manifest")

    def test_manifest_listing_the_done_step_output_passes(self) -> None:
        self.write_pair()
        self.write_run_state("  - id: thing\n    status: done\n", '\n  - "{run}/b.md"')
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_reset_record_is_not_held_to_the_manifest(self) -> None:
        """A `pending` record may still have produced its output — a `revise`
        routing back to it, or entering a phase, resets the record and leaves
        the artifact where it was. Its absence from the manifest proves nothing
        either way, so only `done` is checked."""
        self.write_pair()
        self.write_run_state(
            "  - id: thing\n    status: pending\n    iterations: 1\n", " []"
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_gate_record_has_no_output_to_look_for(self) -> None:
        """Gates take `steps` entries and declare no output, so a `done` gate
        must not be read as an artifact the manifest is missing."""
        self.write_pair()
        self.write_run_state("  - id: plan-approval\n    status: done\n", " []")
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_the_phase_placeholder_resolves_from_run_phase(self) -> None:
        """`{N}` in a declared output resolves from `run.phase`, so a phase-2
        run wants phase 2's artifact and phase 1's does not stand in for it."""
        self.write("workflows/stages/phased.md", self.PHASED_STAGE)
        self.write_run_state(
            "  - id: phased\n    status: done\n",
            '\n  - "{run}/phase-1-plan.md"',
            run="  phase: 2\n",
        )
        self.assert_problem("its output {run}/phase-2-plan.md is not in the manifest")

    def test_a_decided_gate_without_a_record_is_reported(self) -> None:
        """§7 keeps every gate decision and §10 makes a gate's own entry `done`
        only once its decision stands, so a `done` gate with no `gates` entry
        has lost one — the intake gate's especially, that being what accepted
        the class `run.risk` holds."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\nsteps:\n  - id: demo-approval\n    status: done\n"
            "gates: []\nartifacts: []\n",
        )
        self.assert_problem("gate `demo-approval` is done and no `gates` entry records")

    def test_a_duplicate_step_id_is_reported(self) -> None:
        """§10 keeps at most one record per step, and the schema cannot: it
        would have to say "unique by this property" for an open set of ids, and
        `uniqueItems` compares whole records — `done` and `pending` for the same
        id are two distinct items and both pass."""
        self.write_pair()
        self.write_run_state(
            "  - id: thing\n    status: done\n  - id: thing\n    status: pending\n",
            '\n  - "{run}/b.md"',
        )
        self.assert_problem("`thing` has 2 records in `steps`")

    def test_the_schema_alone_does_not_catch_a_duplicate_step_id(self) -> None:
        """The reason the rule lives here rather than in the schema, pinned so
        a later reader does not move it back and lose the coverage."""
        schema = json.loads(
            (self.root / "protocol/schemas/run-state.schema.json").read_text()
        )
        validator = validate_conformance.Draft202012Validator(schema)
        doc = {
            "run": {"id": "demo"},
            "gates": [],
            "steps": [
                {"id": "thing", "status": "done"},
                {"id": "thing", "status": "pending"},
            ],
        }
        self.assertEqual(list(validator.iter_errors(doc)), [])

    def test_a_list_shaped_run_state_fixture_reports_schema_errors_only(self) -> None:
        """A malformed top-level document is the schema check's finding: the
        semantic passes must step around it rather than crash on the shape
        they exist to reject."""
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "- not\n- a\n- mapping\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 1, output)
        self.assertNotIn("Traceback", output)

    def test_a_manifested_import_from_another_run_passes(self) -> None:
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: thing\n    status: skipped\n",
            '\n  - "{run}/a.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_an_import_missing_from_the_manifest_is_reported(self) -> None:
        """§8.6 adds every copy to `artifacts`; an import the manifest omits is
        invisible to every reader that resolves against it. Cross-field, so it
        lives here rather than in the schema."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: thing\n    status: skipped\n",
            " []",
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/a.md is not in the manifest")

    def test_an_import_sourced_from_this_run_is_reported(self) -> None:
        """§8.6 copies from an earlier run's directory, so a run importing from
        itself records lineage that leads nowhere."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: thing\n    status: skipped\n",
            '\n  - "{run}/a.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: demo\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("names this run (`demo`) as its source")

    # Two steps in one stage: `maker` produces {run}/a.md from nothing and
    # `thing` derives {run}/b.md from it — the smallest derivation chain the
    # import-closure check can bind to.
    CHAINED_STAGE = """---
name: chained
description: A stage whose second step derives from the first.
---

# Stage: chained

### maker (analyst)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs: []
      output:
        artifact: "{run}/a.md"
```

### thing (analyst)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/b.md"
```

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: maker
        - step: thing
```
"""

    def test_an_import_set_closed_over_derivation_passes(self) -> None:
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: maker\n    status: skipped\n  - id: thing\n    status: skipped\n",
            '\n  - "{run}/a.md"\n  - "{run}/b.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n"
            "  - artifact: \"{run}/b.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_an_import_without_its_producers_required_input_is_reported(self) -> None:
        """§8.6 keeps the set closed over derivation: importing what a step
        derived without what it derived it from adopts a certificate of
        content this run will produce fresh — the re-run `maker` writes a new
        a.md that the imported b.md never descended from."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: maker\n    status: pending\n  - id: thing\n    status: skipped\n",
            '\n  - "{run}/b.md"',
            extra="imports:\n  - artifact: \"{run}/b.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/b.md arrives without {run}/a.md")

    def test_closure_reads_an_omitted_required_as_required(self) -> None:
        """The step schema defaults `required` to true, so an input that
        omits the field is a prerequisite — reading absence as optional
        would wave the closure past it."""
        self.write(
            "workflows/stages/chained.md",
            self.CHAINED_STAGE.replace(
                '        - artifact: "{run}/a.md"\n          required: true\n',
                '        - artifact: "{run}/a.md"\n',
            ),
        )
        self.write_run_state(
            "  - id: maker\n    status: pending\n  - id: thing\n    status: skipped\n",
            '\n  - "{run}/b.md"',
            extra="imports:\n  - artifact: \"{run}/b.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/b.md arrives without {run}/a.md")

    def test_imports_from_several_source_runs_are_reported(self) -> None:
        """§8.6 has a run import from one source run: artifacts drawn from
        several never descended from one another, and the rewritten headers
        hide it from every later reader."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: maker\n    status: skipped\n  - id: thing\n    status: skipped\n",
            '\n  - "{run}/a.md"\n  - "{run}/b.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: run-one\n"
            "    at: '2026-08-16T09:00:00Z'\n"
            "  - artifact: \"{run}/b.md\"\n    from: run-two\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("imports name 2 source runs (run-one, run-two)")

    def test_an_unresolvable_workflow_is_reported_not_defaulted(self) -> None:
        """A well-formed `run.workflow` that names no workflow file must not
        fall back to every stage contract: a typo such as `featur` would
        otherwise have its imports accepted against producers the run never
        composes."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: maker\n    status: skipped\n",
            '\n  - "{run}/a.md"',
            run="  workflow: featur\n",
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        output = self.assert_problem("run.workflow `featur` names no workflow")
        self.assertNotIn("matches no step output", output)

    def test_an_import_matching_no_step_output_is_reported(self) -> None:
        """§8.2's manifest lists what steps declare, so an import no composed
        step's output template matches is an artifact no conforming source
        run holds — silently accepting it would also wave the closure check
        off exactly where nothing is known about the copy."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: thing\n    status: skipped\n",
            '\n  - "{run}/nobody.md"',
            extra="imports:\n  - artifact: \"{run}/nobody.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/nobody.md matches no step output")

    TWICE_PHASED_STAGE = """---
name: twicephased
description: A stage whose step output names the phase twice.
---

# Stage: twicephased

### twicephased (planner)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: planner
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-of-{N}.md"
```

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: twicephased
```
"""

    def test_a_digit_leading_literal_after_the_phase_compiles(self) -> None:
        """A numeric backreference would merge with a digit that starts the
        next literal — a template ending `{N}0` built a reference to group
        ten and crashed compilation; the named reference cannot merge."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write(
            "workflows/stages/twicephased.md",
            self.TWICE_PHASED_STAGE.replace(
                'artifact: "{run}/phase-{N}-of-{N}.md"',
                'artifact: "{run}/phase-{N}-of-{N}0.md"',
            ),
        )
        self.write_run_state(
            "  - id: twicephased\n    status: skipped\n",
            '\n  - "{run}/phase-1-of-20.md"',
            extra="imports:\n  - artifact: \"{run}/phase-1-of-20.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/phase-1-of-20.md matches no step output")

    def test_every_phase_placeholder_in_one_template_is_one_phase(self) -> None:
        """Two `{N}`s in a declaration denote one executing phase, so a path
        pairing different numbers matches no step output — a fresh capture
        per occurrence would accept it and misattribute the phase."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write("workflows/stages/twicephased.md", self.TWICE_PHASED_STAGE)
        self.write_run_state(
            "  - id: twicephased\n    status: skipped\n",
            '\n  - "{run}/phase-1-of-2.md"',
            extra="imports:\n  - artifact: \"{run}/phase-1-of-2.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/phase-1-of-2.md matches no step output")

    def test_a_consistent_doubled_phase_template_still_matches(self) -> None:
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write("workflows/stages/twicephased.md", self.TWICE_PHASED_STAGE)
        self.write_run_state(
            "  - id: twicephased\n    status: skipped\n",
            '\n  - "{run}/a.md"\n  - "{run}/phase-2-of-2.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n"
            "  - artifact: \"{run}/phase-2-of-2.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_phase_one_import_still_binds_closure_in_a_phase_two_state(self) -> None:
        """Lineage persists, so a phase-2 document may carry phase-1 imports.
        Outputs are matched as templates — resolving `{N}` at `run.phase`
        instead would leave the phase-1 report producerless and skip the
        required-input check exactly where it should bind."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write("workflows/stages/phased.md", self.PHASED_STAGE)
        self.write_run_state(
            "  - id: maker\n    status: pending\n  - id: phased\n    status: pending\n",
            '\n  - "{run}/phase-1-plan.md"',
            run="  phase: 2\n",
            extra="imports:\n  - artifact: \"{run}/phase-1-plan.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/phase-1-plan.md arrives without {run}/a.md")

    def test_an_import_outside_the_composed_workflow_is_reported(self) -> None:
        """§8.6 bounds imports to step outputs of the composed workflow: a
        state whose workflow composes only one stage must not find a producer
        in a stage it never composes, however real that stage's contract is
        elsewhere in the repository."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write("workflows/stages/phased.md", self.PHASED_STAGE)
        self.write(
            "workflows/composed.md",
            frontmatter("composed")
            + "\n1. [stages/chained.md](stages/chained.md)\n"
            + "\n"
            + TRIGGER_BLOCK,
        )
        self.write_run_state(
            "  - id: maker\n    status: skipped\n",
            '\n  - "{run}/phase-1-plan.md"',
            run="  workflow: composed\n",
            extra="imports:\n  - artifact: \"{run}/phase-1-plan.md\"\n"
            "    from: earlier-run\n    at: '2026-08-16T09:00:00Z'\n",
        )
        self.assert_problem("import {run}/phase-1-plan.md matches no step output")

    def test_a_duplicate_import_path_is_reported(self) -> None:
        """§10 keeps one entry per imported artifact, and the schema cannot —
        `uniqueItems` compares whole records, so two entries naming different
        sources for one destination copy both pass. Same reason the duplicate
        step id check lives here."""
        self.write("workflows/stages/chained.md", self.CHAINED_STAGE)
        self.write_run_state(
            "  - id: thing\n    status: skipped\n",
            '\n  - "{run}/a.md"',
            extra="imports:\n  - artifact: \"{run}/a.md\"\n    from: earlier-run\n"
            "    at: '2026-08-16T09:00:00Z'\n"
            "  - artifact: \"{run}/a.md\"\n    from: other-run\n"
            "    at: '2026-08-16T09:01:00Z'\n",
        )
        self.assert_problem("import {run}/a.md has 2 records in `imports`")

    def test_repeated_gate_entries_are_not_duplicates(self) -> None:
        """`gates` carries one entry per decision, so a gate decided twice
        appears twice by design and must not be reported."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\nsteps:\n  - id: demo-approval\n    status: done\n"
            "gates:\n  - gate: demo-approval\n    at: '2026-08-11T09:00:00Z'\n"
            "    outcome: revise\n  - gate: demo-approval\n"
            "    at: '2026-08-11T10:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_done_gate_whose_latest_outcome_is_revise_is_reported(self) -> None:
        """The regression the presence check missed: a `revise` leaves its entry
        in `gates` while the gate returns to `pending`, so an entry alone does
        not say a decision stands. If the later acceptance is never written but
        the status reaches `done`, the stale revision would vouch for it."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\nsteps:\n  - id: demo-approval\n    status: done\n"
            "gates:\n  - gate: demo-approval\n    at: '2026-08-11T09:00:00Z'\n"
            "    outcome: revise\nartifacts: []\n",
        )
        self.assert_problem("its latest outcome is `revise`")

    def test_a_phased_gate_needs_a_decision_at_the_current_phase(self) -> None:
        """A gate a phase repeats decides once per phase, so an earlier phase's
        acceptance must not vouch for a `done` at this one — the entries would
        otherwise be indistinguishable."""
        self.write("workflows/stages/phasedgate.md", self.PHASED_GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 2\nsteps:\n  - id: demo-approval\n"
            "    status: done\ngates:\n  - gate: demo-approval\n    phase: 1\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        self.assert_problem(
            "is done at phase 2 and its latest decision records phase 1"
        )

    def test_a_phased_gate_with_this_phase_decision_stands(self) -> None:
        self.write("workflows/stages/phasedgate.md", self.PHASED_GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 2\nsteps:\n  - id: demo-approval\n"
            "    status: done\ngates:\n  - gate: demo-approval\n    phase: 1\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\n"
            "  - gate: demo-approval\n    phase: 2\n"
            "    at: '2026-08-11T10:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_an_unphased_record_satisfies_no_phase(self) -> None:
        """Whether a gate needs a `phase` comes from its stage, never from the
        records — inferring it from what a record carries would let an omitted
        field decide the field was never required. Reading it from the stage
        closes that without demanding the field back: an entry with no phase
        simply stands for no phase's approval."""
        self.write("workflows/stages/phasedgate.md", self.PHASED_GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 2\nsteps:\n  - id: demo-approval\n"
            "    status: done\ngates:\n  - gate: demo-approval\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        self.assert_problem(
            "is done at phase 2 and its latest decision records no phase"
        )

    def test_a_stale_decision_does_not_hide_a_newer_one(self) -> None:
        """The latest entry is what has to stand, not the best one on file.
        Discarding the entries that do not match the phase before choosing let a
        `phase: 2` acceptance vouch for a gate whose newest decision, recorded
        after it, was a revise."""
        self.write("workflows/stages/phasedgate.md", self.PHASED_GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 2\nsteps:\n  - id: demo-approval\n"
            "    status: done\ngates:\n  - gate: demo-approval\n    phase: 2\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\n"
            "  - gate: demo-approval\n    phase: 2\n"
            "    at: '2026-08-11T11:00:00Z'\n    outcome: revise\nartifacts: []\n",
        )
        self.assert_problem("its latest outcome is `revise`")

    def test_a_decision_from_before_the_run_had_phases_is_left_alone(self) -> None:
        """A re-cut may turn a single-phase run into a multi-phase one (§10),
        and the decisions taken before it had phases were correctly recorded
        without one. Demanding a phase of them would make conformance reject a
        state a supported transition produces, and backfilling would rewrite an
        audit record to say something that was not true when it was written."""
        self.write("workflows/stages/phasedgate.md", self.PHASED_GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 1\nsteps:\n  - id: demo-approval\n"
            "    status: blocked\ngates:\n  - gate: demo-approval\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_an_unphased_gate_in_a_phased_run_is_judged_on_its_latest(self) -> None:
        """A gate that decides once per run records no phase, so scoping its
        decision to `run.phase` would make intake unapprovable in a multi-phase
        run."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\n  phase: 2\nsteps:\n  - id: demo-approval\n"
            "    status: done\ngates:\n  - gate: demo-approval\n"
            "    at: '2026-08-11T09:00:00Z'\n    outcome: accept\nartifacts: []\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_a_done_gate_takes_the_last_entry_naming_it(self) -> None:
        """`gates` is appended in decision order, so a revision followed by an
        acceptance stands — and the reverse does not."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        head = ("run:\n  id: demo\nsteps:\n  - id: demo-approval\n    status: done\n"
                "gates:\n")
        entry = ("  - gate: demo-approval\n    at: '2026-08-11T0{n}:00:00Z'\n"
                 "    outcome: {o}\n")
        for first, second, ok in (("revise", "accept", True), ("accept", "revise", False)):
            self.write(
                "protocol/schemas/examples/run-state.valid.yaml",
                head + entry.format(n=9, o=first) + entry.format(n=10 % 10, o=second)
                + "artifacts: []\n",
            )
            with self.subTest(order=f"{first} then {second}"):
                code, output = self.run_main()
                self.assertEqual(code, 0 if ok else 1, output)

    def test_a_waiting_or_skipped_gate_owes_no_record(self) -> None:
        """`blocked` is a gate still waiting and `skipped` one that never
        decided; neither has an outcome to have lost."""
        self.write("workflows/stages/gated.md", self.GATED_STAGE)
        for status in ("blocked", "skipped", "pending"):
            self.write(
                "protocol/schemas/examples/run-state.valid.yaml",
                f"run:\n  id: demo\nsteps:\n  - id: demo-approval\n    status: {status}\n"
                "gates: []\nartifacts: []\n",
            )
            with self.subTest(status=status):
                code, output = self.run_main()
                self.assertEqual(code, 0, output)

    # A stage a phase repeats — its step writes a per-phase output — declaring a
    # gate. Whether that gate needs a `phase` is read from this, never from the
    # records being checked.
    PHASED_GATED_STAGE = """---
name: phasedgate
description: A stage a phase repeats, declaring a gate.
---

# Stage: phasedgate

### phasedgate (planner)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: planner
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-thing.md"
```

## Gates

- **demo-approval** — collects the human decision.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: phasedgate
        - gate: demo-approval
```
"""

    GATED_STAGE = """---
name: gated
description: A stage that declares a gate.
---

# Stage: gated

## Gates

- **demo-approval** — collects the human decision.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - gate: demo-approval
```
"""

    def test_a_prior_phase_output_is_not_required(self) -> None:
        """A phase the run has left owes this tool nothing it can check.
        Records are one per step and reset on entering a phase, so a `skipped`
        record may have run in an earlier phase and a running one may have been
        skipped there — reading either as evidence about the phase before is
        inference, and this check has been wrong in both directions doing it.
        §8.2 still binds the executor; the document cannot confirm it until run
        state records per-phase participation the way `gates` records the phase
        a decision belongs to.
        """
        self.write("workflows/stages/phased.md", self.PHASED_STAGE)
        self.write_run_state(
            "  - id: phased\n    status: done\n",
            '\n  - "{run}/phase-2-plan.md"',  # phase 1's is absent and stays legal
            run="  phase: 2\n",
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_the_phase_placeholder_defaults_to_phase_one(self) -> None:
        self.write("workflows/stages/phased.md", self.PHASED_STAGE)
        self.write_run_state(
            "  - id: phased\n    status: done\n", '\n  - "{run}/phase-1-plan.md"'
        )
        code, output = self.run_main()
        self.assertEqual(code, 0, output)

    def test_the_spec_run_state_example_is_checked_too(self) -> None:
        """The spec's own example is a run-state document like any other, and
        the tally counts it — a normative example nothing checks is the one
        most likely to drift."""
        _, output = self.run_main()
        match = re.search(r"(\d+) run-state documents", output)
        assert match is not None, output
        self.assertGreaterEqual(int(match.group(1)), 2)

    # ---- malformed declarations stay reportable ----
    #
    # Every check accumulates problems and `main` prints nothing until all of
    # them have run, so a check that raises takes the whole report down with
    # it. These run over documents the schema pass faults rather than instead
    # of it, which is exactly when malformed shapes reach them.

    def test_scalar_output_on_a_standalone_skill_is_reported_not_raised(self) -> None:
        self.write(
            "skills/awf-loner/SKILL.md",
            self.SKILL.replace("awf-thing", "awf-loner").replace(
                '      output:\n        artifact: "{run}/b.md"\n'
                "        template: references/t.template.md",
                "      output: invalid",
            )
            % "true",
        )
        self.assert_problem("is not of type 'object'")

    def test_scalar_output_on_a_step_bound_skill_is_reported_not_raised(self) -> None:
        """The parity check reads the same field, so the guard has to cover it
        too — and there a malformed value is still a value to compare, which is
        why it reads as drift against the stage's well-formed one."""
        self.write_pair()
        self.write(
            "skills/awf-thing/SKILL.md",
            self.SKILL.replace(
                '      output:\n        artifact: "{run}/b.md"\n'
                "        template: references/t.template.md",
                "      output: invalid",
            )
            % "true",
        )
        output = self.assert_problem("is not of type 'object'")
        self.assertIn("step output artifact differs from the one", output)

    def test_a_non_string_step_id_is_reported_not_raised(self) -> None:
        self.write_pair()
        self.write_run_state("  - id: [thing]\n    status: done\n", " []")
        self.assert_problem("is not of type 'string'")

    HOSTILE = (5, "str", [], {}, None, [1, 2], {"a": "b"}, True, 3.5)

    RUN_STATE_SHAPES = (
        "run: %s\ngates: []\n",
        "run:\n  id: demo\n  phase: %s\nsteps:\n  - id: thing\n    status: done\ngates: []\n",
        "run:\n  id: demo\nsteps: %s\ngates: []\n",
        "run:\n  id: demo\nsteps:\n  - %s\ngates: []\n",
        "run:\n  id: demo\nsteps:\n  - id: %s\n    status: done\ngates: []\n",
        "run:\n  id: demo\nsteps:\n  - id: thing\n    status: %s\ngates: []\n",
        "run:\n  id: demo\nsteps:\n  - id: thing\n    status: done\ngates: []\nartifacts: %s\n",
        "run:\n  id: demo\nsteps:\n  - id: thing\n    status: done\ngates: []\nartifacts:\n  - %s\n",
    )

    def test_no_malformed_shape_stops_the_report(self) -> None:
        """Whatever shape a document arrives in, `main` has to reach its print —
        reporting or passing, but never raising. Which of the two it is belongs
        to the schema; that it gets there at all is what this asserts.

        These checks read declarations by shape, and they run over documents
        the schema pass has *faulted* rather than instead of them — that pass
        records a problem and carries on, and nothing prints until every check
        has run. So each field they touch must tolerate a value the schema
        would reject, and the guard belongs on all of them at once: the first
        version covered the manifest and left `steps`, its neighbour, raising.
        """
        self.write_pair()
        pristine = (self.root / "protocol/schemas/examples/run-state.valid.yaml").read_text()
        skill = (self.root / "skills/awf-thing/SKILL.md").read_text()
        output_block = (
            '      output:\n        artifact: "{run}/b.md"\n'
            "        template: references/t.template.md"
        )
        for value in self.HOSTILE:
            encoded = json.dumps(value)
            for shape in self.RUN_STATE_SHAPES:
                self.write(
                    "protocol/schemas/examples/run-state.valid.yaml", shape % encoded
                )
                with self.subTest(field="run-state", value=encoded, shape=shape[:24]):
                    self.assertIn(self.run_main()[0], (0, 1))
            self.write("protocol/schemas/examples/run-state.valid.yaml", pristine)
            for field in ("output", "role", "inputs", "on"):
                mutated = (
                    skill.replace(output_block, f"      output: {encoded}")
                    if field == "output"
                    else re.sub(
                        # The key line may carry a scalar (`role: analyst`) or
                        # open a block; matching only the block form left `role`
                        # and `on` substituting nothing, which reads in the
                        # results as a field that tolerated every hostile value.
                        rf"^      {field}:[^\n]*(?:\n        [^\n]*)*",
                        f"      {field}: {encoded}",
                        skill,
                        count=1,
                        flags=re.MULTILINE,
                    )
                )
                self.assertNotEqual(
                    mutated,
                    skill,
                    f"the {field} mutation changed nothing — the subtest below "
                    "would assert tolerance of a value never written",
                )
                self.write("skills/awf-thing/SKILL.md", mutated)
                with self.subTest(field=field, value=encoded):
                    self.assertIn(self.run_main()[0], (0, 1))
            self.write("skills/awf-thing/SKILL.md", skill)

    def test_a_non_iterable_step_list_is_reported_not_raised(self) -> None:
        """`steps` and `artifacts` are the two arrays a run-state document
        offers, so both go through one guard — the first version of it covered
        the manifest and left this one raising."""
        self.write_pair()
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            'run:\n  id: demo\nsteps: 5\ngates: []\nartifacts:\n  - "{run}/b.md"\n',
        )
        self.assert_problem("is not of type 'array'")

    def test_a_non_iterable_manifest_is_reported_not_raised(self) -> None:
        """A scalar manifest is the shape that bites: a string iterates into
        characters and merely computes nonsense, where a number cannot be
        iterated at all."""
        self.write_pair()
        self.write(
            "protocol/schemas/examples/run-state.valid.yaml",
            "run:\n  id: demo\nsteps:\n  - id: thing\n    status: done\n"
            "gates: []\nartifacts: 5\n",
        )
        self.assert_problem("is not of type 'array'")

    def run_main_expecting_exit_with_root(self, root: Path) -> str:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                validate_conformance.main(["--root", str(root)])
        return str(caught.exception.code)


if __name__ == "__main__":
    unittest.main()
