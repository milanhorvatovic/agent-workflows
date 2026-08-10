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
                        "artifact": {"type": "string"},
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
            "properties": {"id": {"type": "string"}},
        },
        "gates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["gate", "at"],
                "properties": {
                    "gate": {"type": "string"},
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
    protocol: "0.1"
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
    protocol: "0.1"
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


def skill_frontmatter(name: str, extra: str = "license: MIT\n") -> str:
    return f"---\nname: {name}\ndescription: A description.\n{extra}---\n\n# {name}\n"


# A step block declared in Agent Skills frontmatter — the skill-tier
# counterpart of STEP_BLOCK, template included (skills own their templates).
SKILL_WORKFLOW = """\
metadata:
  workflow:
    protocol: "0.1"
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
            ("run-state", RUN_STATE_SCHEMA),
        ):
            self.write(f"protocol/schemas/{name}.schema.json", json.dumps(schema))
        self.write(
            "protocol/schemas/examples/step.valid.yaml",
            'protocol: "0.1"\nstep:\n  role: analyst\n  output:\n    artifact: "{run}/a.md"\n',
        )
        self.write(
            "protocol/schemas/examples/step.invalid.yaml",
            'protocol: "0.1"\nstep:\n  role: orchestrator\n',
        )
        self.write(
            "protocol/schemas/examples/loop.valid.yaml",
            'protocol: "0.1"\nloop:\n  exit_criteria: []\n  max_iterations: 3\n',
        )
        self.write(
            "protocol/schemas/examples/loop.invalid.yaml",
            'protocol: "0.1"\nloop:\n  exit_criteria: []\n',
        )
        self.write(
            "protocol/schemas/examples/trigger.valid.yaml",
            'protocol: "0.1"\ntrigger:\n  kind: manual\n',
        )
        self.write(
            "protocol/schemas/examples/trigger.invalid.yaml",
            'protocol: "0.1"\ntrigger:\n  kind: quantum\n',
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
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + STEP_BLOCK)

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
        self.assertIn("8 fixtures", output)
        self.assertIn("2 spec examples", output)
        self.assertIn("2 workflow blocks", output)
        self.assertIn("3 frontmatter files", output)

    def test_schema_violation_in_workflow_block_reported_with_location(self) -> None:
        broken = STEP_BLOCK.replace("role: analyst", "role: analyst\n      rogue: true")
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + broken)
        output = self.assert_problem("workflows/stages/build.md:8")
        self.assertIn("[step]", output)
        self.assertIn("rogue", output)

    def test_block_declaring_no_structure_reported(self) -> None:
        self.write(
            "workflows/demo.md",
            frontmatter("demo") + '\n```yaml\nmetadata:\n  workflow:\n    protocol: "0.1"\n```\n',
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
            'protocol: "0.1"\ntrigger:\n  kind: quantum\n',
        )
        output = self.assert_problem("trigger.valid.yaml")
        self.assertIn("[trigger]", output)

    def test_invalid_fixture_passing_its_schema_reported(self) -> None:
        self.write(
            "protocol/schemas/examples/trigger.invalid.yaml",
            'protocol: "0.1"\ntrigger:\n  kind: manual\n',
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
            'protocol: "0.1"\ntrigger:\n  kind: quantum\n',
        )
        output = self.assert_problem("trigger.valid.manual.yaml")
        self.assertIn("[trigger]", output)

    def test_invalid_variant_fixture_must_still_fail_its_schema(self) -> None:
        # An invalid variant carries one fault so it covers one rule. A variant
        # that validates proves nothing, exactly as the required pair's does.
        self.write(
            "protocol/schemas/examples/trigger.invalid.pairing.yaml",
            'protocol: "0.1"\ntrigger:\n  kind: manual\n',
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
            '    protocol: "0.1"\n'
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
        self.write("workflows/stages/build.md", frontmatter("build") + "\n" + block)
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
        self.assertIn("3 workflow blocks", output)

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
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/a.md"
          required: true
      output:
        artifact: "{run}/b.md"
```
"""

    SKILL = """---
name: awf-thing
description: A description.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/a.md"
          required: %s
      output:
        artifact: "{run}/b.md"
        template: references/t.template.md
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

    def run_main_expecting_exit_with_root(self, root: Path) -> str:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                validate_conformance.main(["--root", str(root)])
        return str(caught.exception.code)


if __name__ == "__main__":
    unittest.main()
