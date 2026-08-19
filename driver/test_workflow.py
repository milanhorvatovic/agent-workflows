"""Unit tests for workflow.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driver.workflow import Workflow, WorkflowError, load_workflow

REPO = Path(__file__).resolve().parent.parent

STAGE = """---
name: demo
description: A stage.
---

# Stage: demo

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: make
        - gate: check
          conditional: true
```

## Steps

### make (analyst)

Prose.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/in.md"
          required: false
      output:
        artifact: "{run}/out.md"
        template: references/out.template.md
      on:
        PASS: check
        FAIL: make
```

## Gates

- **check** — a gate.
"""

WORKFLOW = """---
name: demo
description: A workflow.
---

# Workflow: demo

1. [stages/demo.md](stages/demo.md)

Prose that mentions [the stage](stages/demo.md) again.
"""


class SyntheticTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.framework = Path(tmp.name)
        self.write("workflows/demo.md", WORKFLOW)
        self.write("workflows/stages/demo.md", STAGE)

    def write(self, relative: str, content: str) -> None:
        path = self.framework / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_loads_the_composed_declarations(self) -> None:
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(workflow.name, "demo")
        (stage,) = workflow.stages
        self.assertEqual(stage.member_ids(), ("make", "check"))
        self.assertEqual([m.kind for m in stage.members], ["step", "gate"])
        self.assertEqual([m.conditional for m in stage.members], [False, True])
        step = workflow.step("make")
        self.assertEqual(step.role, "analyst")
        self.assertEqual(step.output_artifact, "{run}/out.md")
        self.assertEqual(step.output_template, "references/out.template.md")
        self.assertEqual(step.edges, {"PASS": "check", "FAIL": "make"})
        (declared_input,) = step.inputs
        self.assertEqual(declared_input.artifact, "{run}/in.md")
        self.assertFalse(declared_input.required)

    def test_repeated_stage_references_compose_once(self) -> None:
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(len(workflow.stages), 1)

    def test_missing_workflow_is_an_error(self) -> None:
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "absent")
        self.assertIn("cannot read workflow", str(caught.exception))

    def test_an_undecodable_file_is_an_error_not_a_traceback(self) -> None:
        """A file that is not UTF-8 is malformed input, and malformed input
        leaves this module as a WorkflowError like every other kind."""
        for relative in ("workflows/demo.md", "workflows/stages/demo.md"):
            with self.subTest(file=relative):
                (self.framework / relative).write_bytes(b"# stage \xff\xfe\n")
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("cannot read", str(caught.exception))
                self.write(relative, WORKFLOW if relative.count("/") == 1 else STAGE)

    def test_a_traversal_shaped_name_is_refused(self) -> None:
        with self.assertRaises(WorkflowError):
            load_workflow(self.framework, "../demo")

    def test_a_workflow_composing_no_stages_is_an_error(self) -> None:
        self.write("workflows/empty.md", "---\nname: empty\n---\n\n# No refs\n")
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "empty")
        self.assertIn("composes no stages", str(caught.exception))

    def test_a_role_mismatch_between_heading_and_contract_is_an_error(self) -> None:
        """A heading naming one role over a contract declaring another would
        run the step as a role its own stage does not name."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("### make (analyst)", "### make (planner)"),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("under a heading that says 'planner'", str(caught.exception))

    def test_a_truncated_heading_declares_no_step(self) -> None:
        """`### make (` is malformed, not a prefix-match: the contract under
        it must not associate, so the sequence step has no block."""
        self.write(
            "workflows/stages/demo.md", STAGE.replace("### make (analyst)", "### make (")
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("step block above the first step heading", str(caught.exception))

    def test_a_sequence_step_without_a_block_is_an_error(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("- step: make", "- step: make\n        - step: phantom"),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("'phantom' has no step block", str(caught.exception))

    def test_a_step_block_outside_the_sequence_is_an_error(self) -> None:
        extra = STAGE.replace(
            "## Gates",
            "### extra (analyst)\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: analyst\n      output:\n'
            '        artifact: "{run}/x.md"\n```\n\n## Gates',
        )
        self.write("workflows/stages/demo.md", extra)
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("'extra' is not in the sequence", str(caught.exception))

    def test_a_stage_without_a_sequence_is_an_error(self) -> None:
        headless = STAGE.replace("    stage:\n      sequence:\n        - step: make\n        - gate: check\n          conditional: true\n", "    trigger:\n      kind: manual\n")
        self.write("workflows/stages/demo.md", headless)
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("stage sequence blocks", str(caught.exception))

    def test_a_duplicate_member_is_an_error(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("- step: make", "- step: make\n        - step: make"),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("names 'make' twice", str(caught.exception))

    def compose_two_stages(self, second: str) -> None:
        """A workflow over the demo stage and a second one, which is what
        makes the cross-stage rules checkable at all."""
        self.write("workflows/stages/other.md", second)
        self.write(
            "workflows/pair.md",
            "---\nname: pair\ndescription: Two stages.\n---\n\n"
            "1. [stages/demo.md](stages/demo.md)\n2. [stages/other.md](stages/other.md)\n",
        )

    def test_two_stages_sharing_a_member_id_is_an_error(self) -> None:
        """The workflow concatenates its stages' sequences into one record
        list, so a shared id is a duplicate record the moment both compose."""
        self.compose_two_stages(STAGE.replace("name: demo", "name: other"))
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "pair")
        self.assertIn("declared by stages 'demo' and 'other'", str(caught.exception))

    def test_a_member_wearing_a_stage_id_is_an_error(self) -> None:
        """§9.1's targets are untyped strings: a member named for a stage
        makes every edge naming it ambiguous."""
        self.compose_two_stages(
            STAGE.replace("name: demo", "name: other")
            .replace("- step: make", "- step: demo")
            .replace("### make (analyst)", "### demo (analyst)")
            .replace("FAIL: make", "FAIL: demo")
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "pair")
        self.assertIn("which is a stage id", str(caught.exception))

    def test_a_declaration_states_the_protocol_version_it_carries(self) -> None:
        """§11: a client must not silently interpret structures from a
        version it does not implement, and during 0.x any minor may break."""
        for name, replacement in {
            "missing": "    stage:",
            "newer minor": '    protocol: "0.9"\n    stage:',
            "other major": '    protocol: "1.0"\n    stage:',
            "not a version": '    protocol: "0.2.0"\n    stage:',
        }.items():
            with self.subTest(case=name):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE.replace('    protocol: "0.2"\n    stage:', replacement, 1),
                )
                with self.assertRaises(WorkflowError):
                    load_workflow(self.framework, "demo")

    def test_an_older_minor_still_loads(self) -> None:
        """Refusing what the driver does not implement is the rule; an
        earlier minor is not that, and where its shapes differ the load
        fails on the declaration it is missing rather than on its version."""
        self.write(
            "workflows/stages/demo.md", STAGE.replace('protocol: "0.2"', 'protocol: "0.1"')
        )
        self.assertEqual(load_workflow(self.framework, "demo").stages[0].name, "demo")

    def test_a_conditional_that_is_not_true_is_an_error(self) -> None:
        """`conditional` is `const: true` in the schema: read as merely
        falsey, `conditional: false` would populate the member `pending` and
        let a resume reach it before its route fired."""
        for value in ("false", "null", '"true"'):
            with self.subTest(value=value):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE.replace("conditional: true", f"conditional: {value}"),
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("`true` or absent", str(caught.exception))

    def test_an_edge_set_without_fail_is_an_error(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("        FAIL: make\n", ""),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("must route PASS and FAIL", str(caught.exception))

    def test_an_input_defaults_to_required_when_unstated(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace('          required: false\n', ""),
        )
        workflow = load_workflow(self.framework, "demo")
        self.assertTrue(workflow.step("make").inputs[0].required)


class RepositoryTreeTest(unittest.TestCase):
    """The three shipped workflows are the canonical declarations this module
    must read; the counts pin them to the spec's own composition (§6.1) and
    the §10 example's 22 records."""

    def test_feature_composes_six_stages_and_twenty_two_members(self) -> None:
        workflow = load_workflow(REPO, "feature")
        self.assertEqual(
            [stage.name for stage in workflow.stages],
            ["intake", "ideation", "planning", "implementation", "review", "delivery"],
        )
        self.assertEqual(len(workflow.members()), 22)

    def test_bugfix_skips_ideation(self) -> None:
        workflow = load_workflow(REPO, "bugfix")
        self.assertEqual(
            [stage.name for stage in workflow.stages],
            ["intake", "planning", "implementation", "review", "delivery"],
        )

    def test_plan_ends_at_planning(self) -> None:
        workflow = load_workflow(REPO, "plan")
        self.assertEqual(
            [stage.name for stage in workflow.stages],
            ["intake", "ideation", "planning"],
        )

    def test_the_planning_record_order_is_declared_inverted(self) -> None:
        workflow = load_workflow(REPO, "plan")
        planning = workflow.stages[-1]
        self.assertEqual(
            planning.member_ids(),
            ("plan-create", "plan-revise", "plan-validate", "plan-approval"),
        )

    def test_every_sequence_step_has_a_declaration(self) -> None:
        workflow = load_workflow(REPO, "feature")
        for stage, member in workflow.members():
            if member.kind == "step":
                with self.subTest(step=member.id):
                    self.assertIsNotNone(workflow.step(member.id))


if __name__ == "__main__":
    unittest.main()
