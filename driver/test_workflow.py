"""Unit tests for workflow.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driver.workflow import MEMBER_ID, Workflow, WorkflowError, load_workflow

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

    def test_only_the_numbered_list_composes(self) -> None:
        """A link in a sentence or an example is prose about a stage, not a
        claim to run it — a workflow discussing one it does not compose
        would otherwise execute it."""
        self.write("workflows/stages/other.md", STAGE.replace("name: demo", "name: other"))
        for name, mention in {
            "sentence": "A later run may execute [it](stages/other.md) instead.\n",
            "bullet": "- [stages/other.md](stages/other.md) — discussed, not composed\n",
            "example": "```md\n1. [stages/other.md](stages/other.md)\n```\n",
            "tilde example": "~~~\n1. [stages/other.md](stages/other.md)\n~~~\n",
            "indented fence": "  ```\n1. [stages/other.md](stages/other.md)\n  ```\n",
            "longer closer": "```\n1. [stages/other.md](stages/other.md)\n`````\n",
            "unclosed fence": "```\n1. [stages/other.md](stages/other.md)\n",
            "indented": "   1. [stages/other.md](stages/other.md)\n",
        }.items():
            with self.subTest(mention=name):
                self.write("workflows/demo.md", WORKFLOW + "\n" + mention)
                workflow = load_workflow(self.framework, "demo")
                self.assertEqual([stage.name for stage in workflow.stages], ["demo"])

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
        """`### make (` is malformed, not a prefix-match: it owns the space
        beneath it without naming anything, so the contract there attributes
        to no step rather than to whichever heading last parsed."""
        self.write(
            "workflows/stages/demo.md", STAGE.replace("### make (analyst)", "### make (")
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("does not match", str(caught.exception))

    def test_a_step_block_with_no_heading_at_all_is_an_error(self) -> None:
        self.write(
            "workflows/stages/demo.md", STAGE.replace("### make (analyst)\n\n", "")
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("above the first step heading", str(caught.exception))

    def test_every_atx_heading_form_closes_a_step_section(self) -> None:
        """CommonMark ends the marker with a space, a tab, or the line, so
        `###`, `###\\tname`, and their H2 forms are headings too — a scan
        that knew only the space would let the contract below one bind to a
        step further up the file."""
        for heading, fragment in {
            "##\tGates": "closed the step section",
            "##": "closed the step section",
            "###\tnot a step": "does not match",
            "###": "does not match",
        }.items():
            with self.subTest(heading=heading):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE + f"\n{heading}\n\n```yaml\nmetadata:\n  workflow:\n"
                    '    protocol: "0.2"\n    step:\n      role: analyst\n'
                    '      output:\n        artifact: "{run}/moved.md"\n```\n',
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn(fragment, str(caught.exception))

    def test_a_step_block_below_a_closing_h2_is_an_error(self) -> None:
        """`## Gates` ends the step section above it, so a contract below it
        belongs to no step however many valid headings precede it."""
        self.write(
            "workflows/stages/demo.md",
            STAGE + "\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: analyst\n      output:\n'
            '        artifact: "{run}/moved.md"\n```\n',
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("closed the step section", str(caught.exception))

    def test_gates_and_the_sequence_must_name_the_same_members(self) -> None:
        """§9.4 asks parity of both kinds: a sequenced gate the stage does
        not declare blocks the run at a decision nothing describes, and a
        declared one the sequence omits is a decision no record can carry."""
        for name, stage in {
            "sequenced but undeclared": STAGE.replace("- **check** — a gate.", "- **other** — a gate."),
            "declared but unsequenced": STAGE.replace(
                "- **check** — a gate.", "- **check** — a gate.\n- **extra** — a gate."
            ),
        }.items():
            with self.subTest(case=name):
                self.write("workflows/stages/demo.md", stage)
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("gate", str(caught.exception))

    def test_a_gate_bullet_whose_id_is_malformed_is_an_error(self) -> None:
        """Anything bullet-and-bold in the section is a gate declaration, and
        one whose id fails the form is a typo to report. Read as nothing, it
        is a gate the stage describes that parity never asks the sequence
        for — a human decision the run would execute straight past."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace(
                "- **check** — a gate.", "- **check** — a gate.\n- **Extra_Gate** — a typo."
            ),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("Extra_Gate", str(caught.exception))

    def test_authored_text_reaches_the_terminal_escaped(self) -> None:
        """Every value in these errors comes from a file the driver reads,
        and `resume` prints them: a control sequence carried through raw
        would rewrite the line rather than be reported in it. The module
        quotes what it quotes elsewhere for this reason; these two paths
        report captured text and owe the same."""
        for name, stage in {
            "a gate bullet": STAGE.replace(
                "- **check** — a gate.", "- **check** — a gate.\n- **Bad\x1b[31mid** — a typo."
            ),
            "a placeholder": STAGE.replace(
                'artifact: "{run}/out.md"', 'artifact: "{run}/{Q\\u001b[31m}/out.md"'
            ),
        }.items():
            with self.subTest(field=name):
                self.write("workflows/stages/demo.md", stage)
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertNotIn("\x1b", str(caught.exception))

    def test_a_gate_declared_more_than_once_is_an_error(self) -> None:
        """Parity compares declarations, so erasing their multiplicity before
        the comparison lets two `- **check**` bullets answer one sequence
        entry — a member §9.4 declares twice and population records once. A
        second `## Gates` section is the same loss by another route: it sits
        past the boundary the first one's section ends at, so its gates are
        invisible to parity and to gate scoping alike."""
        for name, stage in {
            "declared twice": STAGE.replace(
                "- **check** — a gate.", "- **check** — a gate.\n- **check** — again."
            ),
            "a second section": STAGE + "\n## Gates\n\n- **other** — invisible.\n",
        }.items():
            with self.subTest(case=name):
                self.write("workflows/stages/demo.md", stage)
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("Gates" if "section" in name else "check", str(caught.exception))

    def test_every_atx_heading_form_closes_the_gates_section(self) -> None:
        """The section ends at the next level-2 heading, and CommonMark ends
        that marker with a space, a tab, or the line — a boundary that knew
        only the space would read the bold bullets of the section below as
        gates and fail parity against a sequence that rightly omits them."""
        for heading in ("##\tNotes", "##"):
            with self.subTest(heading=heading):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE + f"\n{heading}\n\n- **stray** — prose, not a gate.\n",
                )
                workflow = load_workflow(self.framework, "demo")
                self.assertEqual(workflow.gate_scopes(), {"check": False})

    def test_a_heading_and_its_contract_associate_one_to_one(self) -> None:
        """A heading with no contract is a step the prose declares and the
        driver has no role or handoff to execute; two headings sharing an id
        are a record population could not tell apart."""
        headless = STAGE.replace(
            "## Gates", "### spare (analyst)\n\nProse with no contract.\n\n## Gates"
        )
        self.write("workflows/stages/demo.md", headless)
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("declares no contract block", str(caught.exception))

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

    def test_an_edge_target_nothing_declares_is_an_error(self) -> None:
        """Unchecked, a mistyped target loads, writes a durable run, and
        fails at the first verdict that tries to route."""
        self.write(
            "workflows/stages/demo.md", STAGE.replace("PASS: check", "PASS: chek")
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("declares nothing for", str(caught.exception))

    def test_an_edge_may_target_another_composed_stage(self) -> None:
        """Which ids exist is a property of the composition: a stage's steps
        routinely route into the stage that follows."""
        self.compose_two_stages(
            STAGE.replace("name: demo", "name: other")
            .replace("- step: make", "- step: build")
            .replace("- gate: check", "- gate: sign")
            .replace("### make (analyst)", "### build (analyst)")
            .replace("PASS: check", "PASS: sign")
            .replace("FAIL: make", "FAIL: build")
            .replace("**check**", "**sign**")
        )
        self.write("workflows/stages/demo.md", STAGE.replace("PASS: check", "PASS: build"))
        workflow = load_workflow(self.framework, "pair")
        self.assertEqual(workflow.step("make").edges["PASS"], "build")

    def test_a_stage_target_with_no_step_declared_is_an_error(self) -> None:
        """A stage of gates alone can never resolve a stage target, and
        that is knowable here rather than one verdict into the run."""
        gates_only = (
            "---\nname: other\ndescription: A stage of gates.\n---\n\n"
            "# Stage: other\n\n"
            "```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    stage:\n      sequence:\n        - gate: sign\n'
            "```\n\n## Gates\n\n- **sign** — a gate.\n"
        )
        self.compose_two_stages(gates_only)
        self.write("workflows/stages/demo.md", STAGE.replace("PASS: check", "PASS: other"))
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "pair")
        self.assertIn("no step to resolve to", str(caught.exception))

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

    def test_the_workflow_file_states_its_own_version_too(self) -> None:
        """The composition is executed from this file, so leaving its own
        declarations unread is what would make a mismatch silent."""
        self.write(
            "workflows/demo.md",
            WORKFLOW
            + "\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "9.0"\n    trigger:\n      kind: manual\n```\n',
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("workflows/demo.md", str(caught.exception))
        self.assertIn("this driver implements", str(caught.exception))

    def test_a_version_is_compared_without_converting_it(self) -> None:
        """The schema puts no ceiling on a component's digits and Python
        caps `int()` at 4300 of them, so a version this shape but absurdly
        long has to be reported like any other rather than raising past
        every handler that carries a defect to an exit code."""
        from driver import implements

        self.assertFalse(implements("0." + "1" * 5000))
        self.assertTrue(implements("0." + "0" * 5000 + "2"))
        self.assertTrue(implements("0.02"))
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace('protocol: "0.2"', 'protocol: "0.%s"' % ("1" * 5000), 1),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("this driver implements", str(caught.exception))

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

    def test_a_declared_metadata_workflow_is_read_by_presence(self) -> None:
        """`metadata.workflow: null` is a declaration that says nothing, not
        a fence carrying something else — read as absence it composes a file
        one of whose declarations is broken."""
        self.write(
            "workflows/stages/demo.md",
            STAGE + "\n```yaml\nmetadata:\n  workflow: null\n```\n",
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("not a mapping", str(caught.exception))

    def test_a_declared_structure_is_read_by_presence_too(self) -> None:
        """A `stage` or `step` that is present and not a mapping is broken,
        and filtering it out would let the file pass on the strength of
        another block that happens to be valid."""
        for structure in ("stage", "step"):
            with self.subTest(structure=structure):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE + "\n```yaml\nmetadata:\n  workflow:\n"
                    f'    protocol: "0.2"\n    {structure}: null\n```\n',
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn(f"{structure} is not a mapping", str(caught.exception))

    def test_a_tilde_fenced_declaration_is_read(self) -> None:
        """§9 places a declaration at a first-column `yaml` fence; which
        marker writes it is CommonMark's business, not the protocol's."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("```yaml", "~~~yaml").replace("```", "~~~"),
        )
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(workflow.step("make").role, "analyst")

    def test_an_example_fence_outside_the_subset_is_not_a_declaration(self) -> None:
        """A first-column `yaml` fence is where declarations live and not
        the only thing that lives there: an example may use YAML this
        subset does not carry, and refusing it would stop composition over
        prose the conformance reader ignores."""
        for example in (
            "example: [one, two]\nother: 'quoted'\n",
            # An example may carry a `metadata` of its own; the block this
            # module reads is the one whose `metadata` holds `workflow`, and
            # nesting decides that rather than the word appearing anywhere —
            # a comment or a quoted value may mention it in passing, and a
            # `workflow` key after the metadata block has ended belongs to
            # whatever opened at the first column instead.
            "metadata:\n  labels: [one, two]\n",
            "metadata: {annotations: 'x'}\n",
            # A comment mentioning the word is a comment, inline as well as
            # on a line of its own.
            "metadata: # {workflow: demo}\n  labels: [one, two]\n",
            # A descendant deeper than the direct child is somebody else's
            # key: `metadata.annotations.workflow` declares nothing.
            "metadata:\n  annotations:\n    workflow: [one, two]\n",
            "metadata: {annotations: {workflow: [one, two]}}\n",
            "metadata:\n  labels: [one, two]\n  # workflow: not a key\n",
            "metadata:\n  labels: ['workflow: x']\n",
            "metadata:\n  labels: [a, b]\nother:\n  workflow: 'x'\n",
            # A quoted scalar is a value however it reads inside, so a flow
            # key is looked for outside the quotes or not at all.
            "metadata: '{workflow: demo}'\n",
            'metadata: "{workflow: demo}"\n',
            # A sibling of `metadata` is not a child of it: the lookup for
            # `workflow` is bounded to `metadata`'s own value, or the next
            # key's mapping answers for it.
            "{metadata: {}, example: {workflow: [one, two]}}\n",
            # Node properties may precede a block scalar, and what they
            # precede is still a block scalar — `metadata` is a string, and
            # the `workflow:` indented under it is that string's text.
            "metadata: !!str |\n  workflow: [one, two]\n",
            "metadata: &saved >\n  workflow: [one, two]\n",
            # An anchor opens a node; the same characters inside a scalar
            # are that scalar's text. `note: x &m metadata` anchors
            # nothing, so the alias below it still names what the real
            # anchor holds.
            "anchor: &m other\nnote: x &m metadata\n*m:\n  workflow: [one, two]\n",
            # A flow mapping the document does not open with is somebody
            # else's value: `example.labels.metadata.workflow` is as deep a
            # descendant written in braces as it is written in lines.
            "example:\n  labels: {metadata: {workflow: x}}\n",
            # `\e` is ESC and `\f` is a form feed, not backslashes to drop:
            # dropped, they spell the very keys this scan looks for, and an
            # example carrying one would be reported as a declaration that
            # no reader resolves.
            '{"m\\etadata": {workflow: [one, two]}}\n',
            'metadata: {"work\\flow": [one, two]}\n',
            # A decoded key is compared as the value it is: `"workflow "`
            # carries a space that no reader trims, so the mapping has no
            # `workflow` key and the block declares nothing — in flow and
            # in block alike.
            'metadata: {"workflow ": [one, two]}\n',
            'metadata:\n  "workflow ": [one, two]\n',
            # A single-quoted scalar escapes its quote by doubling it, so
            # the pair is a character in the value and not the end of it —
            # closing at the first would expose the rest of a scalar as
            # structure and report an example as a broken declaration.
            "metadata: 'it''s {workflow: [one, two]}'\n",
        ):
            with self.subTest(example=example.splitlines()[0]):
                self.write(
                    "workflows/stages/demo.md", STAGE + f"\n```yaml\n{example}```\n"
                )
                workflow = load_workflow(self.framework, "demo")
                self.assertEqual(workflow.stages[0].member_ids(), ("make", "check"))

    def test_a_broken_declaration_is_still_an_error(self) -> None:
        """The refusal is kept for a block that was reaching for a
        declaration and failed — in whichever spelling it reached, since a
        `metadata: {workflow: …}` is outside this subset and is still a
        declaration rather than the prose a narrower test would skip it as."""
        for spelling in (
            "metadata:\n  workflow: [one, two]\n",
            "metadata: {workflow: {protocol: '0.2'}}\n",
            'metadata:\n  "workflow": [one, two]\n',
            # A quoted span followed by `:` is a key, and a key is
            # structure — blanking it with the quoted values would file a
            # declaration as prose.
            'metadata: {"workflow": [one, two]}\n',
            'metadata: { "workflow" : [one, two] }\n',
            # A comment at column zero ends nothing, and an apostrophe
            # inside a plain scalar is an ordinary character.
            "metadata:\n# a comment\n  workflow: [one, two]\n",
            "metadata: {note: don't, workflow: [one, two]}\n",
            # The same character after a space is the same character: a
            # quote opens a scalar at the start of a node and nowhere else,
            # or everything past this apostrophe — the real key included —
            # would blank and file the declaration as prose.
            "metadata: {note: rock 'n roll, workflow: [one, two]}\n",
            # A document may be a flow mapping whole, and `metadata` is its
            # direct key there as much as at the first column — a reader
            # that parses it resolves the same `metadata.workflow`.
            "{metadata: {workflow: [one, two]}}\n",
            "{'metadata': {workflow: [one, two]}}\n",
            # Node properties precede the root node as readily as any other,
            # and what they annotate is the same mapping.
            "!!map {metadata: {workflow: [one, two]}}\n",
            "&saved {metadata: {workflow: [one, two]}}\n",
            # A key is a node too, and one carrying a tag or an anchor
            # resolves to the same key — at either level, in either form.
            "!!str metadata:\n  workflow: [one, two]\n",
            "&saved metadata:\n  workflow: [one, two]\n",
            "metadata:\n  !!str workflow: [one, two]\n",
            "{!!str metadata: {workflow: [one, two]}}\n",
            # An alias names what its anchor holds: the key `*m` is
            # `metadata` where `&m metadata` said so, and a value `*w` is
            # the mapping the anchor carries.
            "anchor: &m metadata\n*m:\n  workflow: [one, two]\n",
            # What an anchor holds ends where a comment begins, and an
            # alias names the definition before it rather than the last one
            # in the file.
            "anchor: &m metadata # a label\n*m:\n  workflow: [one, two]\n",
            "a: &m metadata\n*m:\n  workflow: [one, two]\nb: &m other\n",
            "anchor: &w {workflow: [one, two]}\nmetadata: *w\n",
            # A stream mark stands ahead of the document it opens, and the
            # reader that parses past it resolves the same two keys.
            "\ufeff{metadata: {workflow: [one, two]}}\n",
            "\ufeffmetadata:\n  workflow: [one, two]\n",
            # The document-start marker opens the document it precedes, and
            # what follows it is that document's root.
            "--- {metadata: {workflow: [one, two]}}\n",
            "---\n{metadata: {workflow: [one, two]}}\n",
            "--- !!map {metadata: {workflow: [one, two]}}\n",
            # A quoted key is decoded before it is a key: `"work\\u0066low"`
            # is the same key spelled with an escape, at either level.
            'metadata: {"work\\u0066low": [one, two]}\n',
            '"met\\u0061data":\n  workflow: [one, two]\n',
            '? "met\\u0061data"\n: {workflow: [one, two]}\n',
            # The explicit indicator may stand alone, its key on the line
            # beneath it and the value under the `:` line after that.
            "?\n  metadata\n:\n  workflow: [one, two]\n",
            '{"met\\u0061data": {workflow: [one, two]}}\n',
            'metadata:\n  "work\\u0066low": [one, two]\n',
            "metadata: {!!str workflow: [one, two]}\n",
            # YAML's explicit key form names the same key: `? metadata` with
            # the value on the `:` line beneath it, and its flow spelling.
            "? metadata\n: {workflow: [one, two]}\n",
            "metadata:\n  ? workflow\n  : [one, two]\n",
            "metadata:\n  ? !!str workflow\n  : [one, two]\n",
            "? metadata\n:\n  workflow: [one, two]\n",
            "{? metadata: {workflow: [one, two]}}\n",
            # A comment after a real key does not unmake the key.
            "metadata: {workflow: [one, two]} # {workflow: no}\n",
            # The one that carries both: a quoted value mentioning the word
            # and a real key beside it.
            'metadata: {name: "workflow: x", workflow: [one, two]}\n',
            # Single quotes are outside this subset, which is why the block
            # fails to parse — and a key written in them is still a key.
            "'metadata': {workflow: [one, two]}\n",
            "metadata:\n  'workflow': [one, two]\n",
        ):
            with self.subTest(spelling=spelling.splitlines()[0]):
                self.write(
                    "workflows/stages/demo.md", STAGE + f"\n```yaml\n{spelling}```\n"
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                # Which subset rule catches it depends on the spelling — a
                # flow collection, a single-quoted key — and what matters is
                # that the block is reported against its file rather than
                # skipped as prose.
                self.assertIn("workflows/stages/demo.md", str(caught.exception))

    def test_a_declaration_inside_a_longer_fence_is_an_example(self) -> None:
        """Discovery consumes outermost fences whole, so a block shown
        inside a wrapper is part of the example, never a declaration."""
        self.write(
            "workflows/stages/demo.md",
            STAGE
            + "\n````md\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: planner\n      output:\n'
            '        artifact: "{run}/x.md"\n```\n````\n',
        )
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(sorted(workflow.stages[0].steps), ["make"])

    def test_a_heading_inside_an_example_binds_nothing(self) -> None:
        """Between a real heading and its contract, an example's heading
        would otherwise be the nearest one and take the contract with it."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace(
                "Prose.\n", "Prose.\n\n```md\n### fake (planner)\n```\n"
            ),
        )
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(sorted(workflow.stages[0].steps), ["make"])

    def test_a_role_outside_the_protocol_six_is_an_error(self) -> None:
        """The config routes exactly the six roles, so a seventh is a step
        nothing can execute — and the file that declares it is nameable
        here, where a run directory does not exist yet."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("### make (analyst)", "### make (auditor)").replace(
                "role: analyst", "role: auditor"
            ),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("not a protocol role", str(caught.exception))

    def test_an_output_carrying_the_phase_set_placeholder_is_an_error(self) -> None:
        """`{P}` is one path per phase; a step produces one artifact, so the
        placeholder would enter the manifest as the literal it is."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace('artifact: "{run}/out.md"', 'artifact: "{run}/phase-{P}-out.md"'),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("carries {P}", str(caught.exception))

    def test_a_placeholder_the_spec_does_not_define_is_an_error(self) -> None:
        """The spec defines four, and nothing resolves a fifth: completion
        substitutes `{N}` alone, so an unknown token would enter the manifest
        as the literal it is — the path a later step reads by that name never
        existing. Every string the contract addresses a path with is read,
        the conformance suite's rule and its known set."""
        for name, stage in {
            "output artifact": STAGE.replace(
                'artifact: "{run}/out.md"', 'artifact: "{run}/phase-{Q}-out.md"'
            ),
            "input artifact": STAGE.replace(
                'artifact: "{run}/in.md"', 'artifact: "{run}/{Q}-in.md"'
            ),
            "template": STAGE.replace(
                "template: references/out.template.md",
                "template: references/{Q}.template.md",
            ),
            # Resolved by the executor, never authored — the suite says so
            # in its own message, and it is unknown here for the same reason.
            "the manifest's own name": STAGE.replace(
                'artifact: "{run}/out.md"', 'artifact: "{artifacts}/out.md"'
            ),
        }.items():
            with self.subTest(field=name):
                self.write("workflows/stages/demo.md", stage)
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("placeholder", str(caught.exception))

    def test_a_shell_style_phase_set_token_is_text(self) -> None:
        """`${P}` is shell text by the same rule that makes `${N}` shell
        text, and the reader that recognizes placeholders reads past both.
        The rule against a phase set of outputs is about the placeholder,
        so a path that merely looks like one is a path."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace('artifact: "{run}/out.md"', 'artifact: "{run}/phase-${P}-out.md"'),
        )
        workflow = load_workflow(self.framework, "demo")
        self.assertEqual(workflow.step("make").output_artifact, "{run}/phase-${P}-out.md")

    def test_a_required_that_is_not_a_boolean_is_an_error(self) -> None:
        """Absence is the default; a present value that is not a boolean
        would be coerced to required and change what blocks the step."""
        for value in ('"false"', "0", "null"):
            with self.subTest(value=value):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE.replace("required: false", f"required: {value}"),
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("not a boolean", str(caught.exception))

    def test_a_member_id_carrying_a_line_break_is_refused(self) -> None:
        """`$` matches before a final newline, so the schema's pattern read
        with `match` accepted `"check\\n"` — a record id with a line break
        in it, which would split the position line the CLI prints."""
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("- gate: check", '- gate: "check\\n"'),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("not a member id", str(caught.exception))

    def test_member_id_is_the_schema_pattern(self) -> None:
        """The literal mirrors the stage schema's member-id pattern — the
        schema is the source of truth, and the pin keeps them together."""
        import json

        schema = json.loads(
            (REPO / "protocol" / "schemas" / "stage.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            MEMBER_ID.pattern,
            schema["$defs"]["member"]["properties"]["step"]["pattern"],
        )

    def test_unknown_keys_inside_a_declared_structure_are_errors(self) -> None:
        """§9.5: unknown keys inside a declared structure are authoring
        errors. Each of these typos otherwise reads as a deliberate
        omission — of conditionality, of routing, of a scaffold."""
        for name, (before, after) in {
            "stage": ("      sequence:", "      sequenc: []\n      sequence:"),
            "member": ("          conditional: true", "          conditionl: true"),
            "step": ("      role: analyst", "      rol: analyst\n      role: analyst"),
            "output": (
                "        template: references/out.template.md",
                "        templat: references/out.template.md",
            ),
            "input": ("          required: false", "          requiredd: false"),
        }.items():
            with self.subTest(structure=name):
                self.write("workflows/stages/demo.md", STAGE.replace(before, after))
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("unknown keys", str(caught.exception))

    def test_a_member_names_exactly_one_kind(self) -> None:
        """Presence decides, not truthiness: `gate: null` is a named field
        with a broken value, and an entry naming both kinds is not one
        member however either value parses."""
        for name, replacement in {
            "both kinds": "        - step: make\n          gate: null",
            "null value": "        - step: null",
            "id the schema refuses": "        - step: Make Step",
        }.items():
            with self.subTest(case=name):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE.replace("        - step: make", replacement),
                )
                with self.assertRaises(WorkflowError):
                    load_workflow(self.framework, "demo")

    def test_a_declared_optional_field_is_read_by_presence(self) -> None:
        """`null` is a declared value, not an absent key: read as absence it
        gives a broken declaration the behaviour of a valid one — a step
        that scaffolds nothing, a step that routes by composition order."""
        for name, (before, after) in {
            "template": (
                "        template: references/out.template.md",
                "        template: null",
            ),
            "on": (
                "      on:\n        PASS: check\n        FAIL: make\n",
                "      on: null\n",
            ),
        }.items():
            with self.subTest(field=name):
                self.write("workflows/stages/demo.md", STAGE.replace(before, after))
                with self.assertRaises(WorkflowError):
                    load_workflow(self.framework, "demo")

    def test_an_empty_template_is_an_error(self) -> None:
        self.write(
            "workflows/stages/demo.md",
            STAGE.replace("template: references/out.template.md", 'template: ""'),
        )
        with self.assertRaises(WorkflowError) as caught:
            load_workflow(self.framework, "demo")
        self.assertIn("template is not a path", str(caught.exception))

    def test_an_inputs_value_that_is_not_a_list_is_an_error(self) -> None:
        """Read as absence, a malformed `inputs` drops the step's whole
        handoff contract instead of reporting the line that broke."""
        for value in ("false", "null", "{}"):
            with self.subTest(value=value):
                self.write(
                    "workflows/stages/demo.md",
                    STAGE.replace(
                        '      inputs:\n        - artifact: "{run}/in.md"\n'
                        "          required: false\n",
                        f"      inputs: {value}\n",
                    ),
                )
                with self.assertRaises(WorkflowError) as caught:
                    load_workflow(self.framework, "demo")
                self.assertIn("`inputs` is not a list", str(caught.exception))


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
