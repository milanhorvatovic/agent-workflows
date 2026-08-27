"""Unit tests for assembler.py.

Run from the repo root: python3 -m unittest discover -s driver -t .
"""

from __future__ import annotations

import os
import re
import signal
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from driver import assembler, state
from driver.state import RunState, StepRecord
from driver.test_workflow import REPO, STAGE, WORKFLOW
from driver.workflow import WorkflowError, load_workflow

# The skill bound to STAGE's `make` step: the same contract, which is what
# makes it the binding rather than the name that finds it.
SKILL = """---
name: awf-make
description: A step-bound skill.
license: MIT
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
---

# Skill: awf-make

Work through `references/checklist.md` before writing, and scaffold from
`references/out.template.md`.
"""

ROLE = """---
name: analyst
description: A role.
---

# Role: Analyst

Read before concluding.
"""

TEMPLATE = "# Out: [title]\n\n> **Run:** [run id]\n\n## Findings\n\n[what was found]\n"

# The shipped shape: the skill declares the template and the stage does not.
# A template resolves against the file declaring it, so both declaring one
# names two files and is refused — the tests that exercise the stage's
# carrier write `STAGE` back in themselves.
STAGE_ONLY = STAGE.replace("        template: references/out.template.md\n", "")


def _alarm(*_) -> None:
    raise AssertionError("still blocked in open() — the non-regular-file guard regressed")


class TreeTest(unittest.TestCase):
    """A synthetic framework and run, built once per test so each can bend
    exactly the one declaration it is about."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.framework = self.base / "framework"
        self.run_dir = self.base / "runs" / "demo-run"
        self.run_dir.mkdir(parents=True)
        self.write("workflows/demo.md", WORKFLOW)
        self.write("workflows/stages/intake.md", STAGE_ONLY)
        self.write("skills/awf-make/SKILL.md", SKILL)
        self.write("skills/awf-make/references/checklist.md", "- check this\n")
        self.write("skills/awf-make/references/out.template.md", TEMPLATE)
        self.write("roles/analyst.md", ROLE)

    def write(self, relative: str, content: str) -> None:
        path = self.framework / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def artifact(self, name: str, content: str = "body\n") -> None:
        (self.run_dir / name).write_text(content, encoding="utf-8")

    def workflow(self):
        return load_workflow(self.framework, "demo")

    def state(self, artifacts: list[str] | None = None, phase: int | None = None) -> RunState:
        return RunState(
            run_id="demo-run",
            workflow="demo",
            protocol="0.2",
            steps=[StepRecord(id="make", status="pending")],
            gates=[],
            artifacts=list(artifacts or []),
            phase=phase,
        )

    def declaration(self):
        return self.workflow().step("make")

    def load(self) -> assembler.Skill:
        return assembler.load_skill(self.framework, "make", self.declaration())


class LoadSkillTest(TreeTest):
    def test_reads_the_body_template_and_named_references(self) -> None:
        skill = self.load()
        self.assertEqual(skill.step_id, "make")
        self.assertTrue(skill.body.startswith("\n# Skill: awf-make"))
        self.assertNotIn("license: MIT", skill.body)
        self.assertEqual(skill.template, "references/out.template.md")
        self.assertEqual(skill.references, ("references/checklist.md",))

    def test_the_template_is_not_also_a_reference(self) -> None:
        """The step is given the template as the scaffold its output starts
        from; listing it again as reading material would put one structure in
        the prompt twice under two labels."""
        self.assertNotIn("references/out.template.md", self.load().references)

    def test_references_keep_first_mention_order_without_repeats(self) -> None:
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace(
                "Work through `references/checklist.md` before writing",
                "Load `references/second.md`, then `references/checklist.md`, "
                "then `references/second.md` again",
            ),
        )
        self.write("skills/awf-make/references/second.md", "second\n")
        self.assertEqual(
            self.load().references,
            ("references/second.md", "references/checklist.md"),
        )

    def test_a_reference_the_body_names_must_exist(self) -> None:
        """A named reference nothing backs is a broken package: the step would
        be told to load a file the executor cannot hand it."""
        (self.framework / "skills/awf-make/references/checklist.md").unlink()
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("references/checklist.md", str(caught.exception))
        self.assertIn("not a file", str(caught.exception))

    def test_the_frontmatter_rule_is_the_conformance_suite_s(self) -> None:
        """The two cannot share an implementation — the suite parses through a
        YAML library this package may not import — so what they share is the
        rule, pinned here. A driver reading frontmatter the suite would have
        rejected runs a skill CI never validated."""
        source = (REPO / "scripts" / "validate_conformance.py").read_text(encoding="utf-8")
        declared = re.search(r"^FRONTMATTER = re\.compile\((?P<literal>.+?)\)$", source, re.M)
        self.assertIsNotNone(declared, "the suite no longer declares FRONTMATTER this way")
        self.assertEqual(
            assembler.FRONTMATTER.pattern,
            eval(declared.group("literal").split(", re.")[0]),  # noqa: S307 — a repo literal
        )

    def test_a_skill_authored_with_crlf_reads_the_same_as_the_suite_reads_it(self) -> None:
        """The conformance suite reads these files through `read_text`, which
        translates newlines, and the frontmatter pattern the two share matches
        `\\n` — so without the same translation a CRLF skill passes CI and is
        then refused here for having no frontmatter."""
        (self.framework / "skills/awf-make/SKILL.md").write_bytes(
            SKILL.replace("\n", "\r\n").encode("utf-8")
        )
        skill = self.load()
        self.assertEqual(skill.template, "references/out.template.md")
        self.assertEqual(skill.references, ("references/checklist.md",))
        self.assertNotIn("\r", skill.body)

    def test_a_reference_named_inside_a_fence_is_an_example(self) -> None:
        """The one fence model this repository reads declarations through: a
        path inside an example is that example's, so loading it would put a
        demonstration in the step's context — and refuse the skill outright
        where the example names a file never meant to exist."""
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace(
                "Work through `references/checklist.md` before writing, and scaffold from\n"
                "`references/out.template.md`.",
                "Work through `references/checklist.md`.\n\n"
                "```markdown\nA skill may name `references/illustrative.md` here.\n```",
            ),
        )
        self.assertEqual(self.load().references, ("references/checklist.md",))

    def test_a_nested_reference_is_the_file_not_the_directory(self) -> None:
        """A pattern stopping at the first segment takes `references/guides`
        out of `references/guides/style.md` — not merely missing the file but
        refusing the skill for naming a directory."""
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace("references/checklist.md", "references/guides/style.md"),
        )
        self.write("skills/awf-make/references/guides/style.md", "nested\n")
        self.assertEqual(self.load().references, ("references/guides/style.md",))

    def test_trailing_punctuation_is_not_part_of_the_path(self) -> None:
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace("`references/checklist.md` before writing", "`references/checklist.md`."),
        )
        self.assertEqual(self.load().references, ("references/checklist.md",))

    def test_a_missing_skill_names_the_path_it_looked_for(self) -> None:
        (self.framework / "skills/awf-make/SKILL.md").unlink()
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("skills/awf-make/SKILL.md", str(caught.exception))

    def test_a_skill_without_frontmatter_is_refused(self) -> None:
        self.write("skills/awf-make/SKILL.md", "# Skill: awf-make\n\nProse.\n")
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("no frontmatter", str(caught.exception))

    def test_frontmatter_outside_the_yaml_subset_is_reported(self) -> None:
        self.write("skills/awf-make/SKILL.md", SKILL.replace('name: awf-make', "name: *alias"))
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("frontmatter", str(caught.exception))

    def test_a_skill_without_a_workflow_declaration_is_refused(self) -> None:
        self.write(
            "skills/awf-make/SKILL.md",
            "---\nname: awf-make\ndescription: A skill.\n---\n\n# Skill\n",
        )
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("metadata.workflow", str(caught.exception))

    def test_a_declaration_without_a_protocol_version_is_refused(self) -> None:
        self.write("skills/awf-make/SKILL.md", SKILL.replace('    protocol: "0.2"\n', ""))
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("protocol version", str(caught.exception))

    def test_a_declaration_from_a_version_the_driver_does_not_implement(self) -> None:
        """§11: a newer minor may carry breaking changes while the protocol is
        0.x, so the skill ships prose written against contracts this run does
        not execute."""
        self.write("skills/awf-make/SKILL.md", SKILL.replace('protocol: "0.2"', 'protocol: "9.9"'))
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("this driver implements", str(caught.exception))

    def test_a_step_that_is_not_a_mapping_is_refused(self) -> None:
        self.write(
            "skills/awf-make/SKILL.md",
            "---\nname: awf-make\ndescription: A skill.\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step: null\n---\n\n# Skill\n',
        )
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("not a mapping", str(caught.exception))

    def test_a_malformed_step_is_reported_as_an_assembly_error(self) -> None:
        """Parsed by the composition module's reader, so both carriers accept
        the same things — but its refusal reaches the caller as this module's,
        since the caller is assembling rather than composing."""
        self.write("skills/awf-make/SKILL.md", SKILL.replace("role: analyst", "role: cartographer"))
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("not a protocol role", str(caught.exception))


class ParityTest(TreeTest):
    """Two copies of one contract must agree (§9.1): the stage composes the
    run, the skill is what the step executes from, and a disagreement runs
    prose written against inputs the step was never given."""

    def assert_refused(self, replacement: tuple[str, str], expected: str) -> None:
        self.write("skills/awf-make/SKILL.md", SKILL.replace(*replacement))
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn(expected, str(caught.exception))
        self.assertIn("must agree", str(caught.exception))

    def test_a_differing_role_is_refused(self) -> None:
        self.assert_refused(("role: analyst", "role: planner"), "role")

    def test_a_differing_input_is_refused(self) -> None:
        self.assert_refused(('artifact: "{run}/in.md"', 'artifact: "{run}/other.md"'), "inputs")

    def test_a_differing_input_strength_is_refused(self) -> None:
        self.assert_refused(("required: false", "required: true"), "inputs")

    def test_a_differing_output_artifact_is_refused(self) -> None:
        self.assert_refused(
            ('artifact: "{run}/out.md"', 'artifact: "{run}/elsewhere.md"'), "output artifact"
        )

    def test_a_differing_edge_is_refused(self) -> None:
        self.assert_refused(("PASS: check", "PASS: make"), "edges")

    def test_both_carriers_declaring_a_template_is_refused(self) -> None:
        """The rest of the contract is two copies of one thing and agreement
        is string equality; a template is not, because the same string under
        two bases names two files."""
        self.write("workflows/stages/intake.md", STAGE)
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.load()
        self.assertIn("both declare a template", str(caught.exception))

    def test_the_skill_supplies_the_template_the_stage_omits(self) -> None:
        """Which is every shipped pairing: no stage declares a template, and
        all nineteen that scaffold declare it on the skill."""
        self.write(
            "workflows/stages/intake.md",
            STAGE.replace("        template: references/out.template.md\n", ""),
        )
        self.assertEqual(self.load().template, "references/out.template.md")

    def test_the_stage_supplies_the_template_the_skill_omits(self) -> None:
        self.write("workflows/stages/intake.md", STAGE)
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace("        template: references/out.template.md\n", ""),
        )
        self.write("workflows/stages/references/out.template.md", TEMPLATE)
        self.assertEqual(self.load().template, "references/out.template.md")

    def test_neither_declaring_a_template_scaffolds_nothing(self) -> None:
        """What `risk-route`, `plan-revise`, and `ideate-revise` declare: the
        artifact they write was created by the step before them."""
        for relative, text in (
            ("workflows/stages/intake.md", STAGE_ONLY),
            ("skills/awf-make/SKILL.md", SKILL),
        ):
            self.write(relative, text.replace("        template: references/out.template.md\n", ""))
        skill = self.load()
        self.assertIsNone(skill.template)
        self.assertFalse(assembler.scaffold(skill, self.run_dir, "{run}/out.md"))
        self.assertFalse((self.run_dir / "out.md").exists())


class ResolveTest(TreeTest):
    """§8.1: `{N}` is the phase the step is executing and names one path;
    `{P}` is every *other* phase the manifest records the artifact for."""

    def resolve(self, artifact: str, output: str, phase: int | None, manifest: list[str]):
        declaration = self.declaration()
        declaration = type(declaration)(
            id=declaration.id,
            role=declaration.role,
            inputs=declaration.inputs,
            output_artifact=output,
            output_template=declaration.output_template,
            edges=declaration.edges,
        )
        return assembler.resolve(artifact, declaration, self.state(manifest, phase))

    def test_a_phase_placeholder_takes_the_running_phase(self) -> None:
        self.assertEqual(
            self.resolve("{run}/phase-{N}-plan.md", "{run}/phase-{N}-plan.md", 3, []),
            ("{run}/phase-3-plan.md",),
        )

    def test_a_run_without_phases_resolves_to_phase_one(self) -> None:
        """§8.1: `{N}` is phase 1 where `run.phase` is absent, which is what a
        single-phase run carries and what a run carries before its first
        acceptance."""
        self.assertEqual(
            self.resolve("{run}/phase-{N}-plan.md", "{run}/phase-{N}-plan.md", None, []),
            ("{run}/phase-1-plan.md",),
        )

    def test_a_phase_set_excludes_the_phase_the_step_is_executing(self) -> None:
        manifest = [f"{{run}}/phase-{n}-log.md" for n in (1, 2, 3)]
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/phase-{N}-plan.md", 2, manifest),
            ("{run}/phase-1-log.md", "{run}/phase-3-log.md"),
        )

    def test_a_step_whose_output_carries_no_phase_reads_them_all(self) -> None:
        """§8.1 settles the exclusion from the step's own output, never from
        run state: `run.phase` still names the last phase while the stages
        after it run, so reading it as this step's would drop the final phase
        from exactly the sets those stages exist to read whole."""
        manifest = [f"{{run}}/phase-{n}-log.md" for n in (1, 2, 3)]
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/delivery.md", 3, manifest),
            ("{run}/phase-1-log.md", "{run}/phase-2-log.md", "{run}/phase-3-log.md"),
        )

    def test_a_phase_set_is_ordered_by_number_not_by_spelling(self) -> None:
        manifest = [f"{{run}}/phase-{n}-log.md" for n in (10, 2, 9)]
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/delivery.md", None, manifest),
            ("{run}/phase-2-log.md", "{run}/phase-9-log.md", "{run}/phase-10-log.md"),
        )

    def test_a_phase_set_the_manifest_records_nothing_for_is_empty(self) -> None:
        """Which is phase 1's ordinary state — empty rather than missing."""
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/phase-{N}-plan.md", 1, []), ()
        )

    def test_the_manifest_decides_the_set_not_the_directory(self) -> None:
        """§8.1: a phase the manifest does not record is not one `{P}` names."""
        self.artifact("phase-1-log.md")
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/delivery.md", None, []), ()
        )

    def test_one_path_cannot_name_two_different_phases(self) -> None:
        with self.assertRaises(assembler.AssemblyError) as caught:
            self.resolve("{run}/phase-{N}/phase-{P}.md", "{run}/out.md", 1, [])
        self.assertIn("different phases", str(caught.exception))

    def test_a_phase_number_no_integer_can_hold_is_still_ordered(self) -> None:
        """The manifest is a document the driver reads and did not necessarily
        write, and `int()` caps at 4300 digits — so a phase past that must
        order like every other one rather than leave the driver as a
        traceback."""
        manifest = [
            "{run}/phase-2-log.md",
            "{run}/phase-" + "9" * 5000 + "-log.md",
            "{run}/phase-30-log.md",
        ]
        self.assertEqual(
            self.resolve("{run}/phase-{P}-log.md", "{run}/delivery.md", None, manifest),
            (
                "{run}/phase-2-log.md",
                "{run}/phase-30-log.md",
                "{run}/phase-" + "9" * 5000 + "-log.md",
            ),
        )

    def test_an_escaped_token_is_text_rather_than_a_placeholder(self) -> None:
        self.assertEqual(
            self.resolve("{run}/${N}-plan.md", "{run}/out.md", 2, []), ("{run}/${N}-plan.md",)
        )


class AssembleTest(TreeTest):
    def test_materials_come_in_one_deterministic_order(self) -> None:
        self.artifact("in.md", "the input\n")
        assembly = assembler.assemble(
            self.framework, self.run_dir, self.state(["{run}/in.md"]), self.workflow(), "make"
        )
        self.assertEqual(
            [(m.kind, m.source) for m in assembly.materials],
            [
                ("role", "roles/analyst.md"),
                ("skill", "skills/awf-make/SKILL.md"),
                ("reference", "skills/awf-make/references/checklist.md"),
                ("input", "{run}/in.md"),
                ("template", "skills/awf-make/references/out.template.md"),
            ],
        )
        self.assertEqual(assembly.role, "analyst")
        self.assertEqual(assembly.output, "{run}/out.md")
        self.assertEqual(assembly.output_path, self.run_dir / "out.md")

    def test_the_same_run_and_step_assemble_to_the_same_bytes(self) -> None:
        self.artifact("in.md")
        first = assembler.assemble(
            self.framework, self.run_dir, self.state(["{run}/in.md"]), self.workflow(), "make"
        )
        second = assembler.assemble(
            self.framework, self.run_dir, self.state(["{run}/in.md"]), self.workflow(), "make"
        )
        self.assertEqual(first.prompt, second.prompt)

    def test_the_prompt_states_where_the_step_stands_and_what_it_owes(self) -> None:
        self.artifact("in.md", "the input\n")
        prompt = assembler.assemble(
            self.framework,
            self.run_dir,
            self.state(["{run}/in.md"], phase=2),
            self.workflow(),
            "make",
        ).prompt
        for line in (
            "# agent-workflows step: make",
            "- Run: demo-run",
            "- Workflow: demo",
            "- Phase: 2",
            "- Role: analyst",
            "- Output: {run}/out.md",
        ):
            self.assertIn(line, prompt)
        self.assertIn("Read before concluding.", prompt)
        self.assertIn("# Skill: awf-make", prompt)
        self.assertIn("- check this", prompt)
        self.assertIn("the input", prompt)
        self.assertIn("[what was found]", prompt)

    def test_an_optional_input_the_manifest_does_not_hold_is_left_out(self) -> None:
        assembly = assembler.assemble(
            self.framework, self.run_dir, self.state([]), self.workflow(), "make"
        )
        self.assertNotIn("input", [m.kind for m in assembly.materials])

    def test_a_required_input_the_run_has_not_produced_blocks_the_step(self) -> None:
        """§9.1, and not a defect: the run has simply not got there yet."""
        self.write(
            "workflows/stages/intake.md",
            STAGE_ONLY.replace("required: false", "required: true"),
        )
        self.write("skills/awf-make/SKILL.md", SKILL.replace("required: false", "required: true"))
        with self.assertRaises(assembler.BlockedError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state([]), self.workflow(), "make"
            )
        self.assertIn("{run}/in.md", str(caught.exception))
        self.assertIsInstance(caught.exception, assembler.AssemblyError)

    def test_an_artifact_on_disk_but_not_in_the_manifest_satisfies_nothing(self) -> None:
        """§8.2: the manifest is what says the run holds an artifact, and a
        file beside it that no step declared is working material."""
        self.artifact("in.md")
        assembly = assembler.assemble(
            self.framework, self.run_dir, self.state([]), self.workflow(), "make"
        )
        self.assertNotIn("input", [m.kind for m in assembly.materials])

    def test_a_manifest_entry_whose_file_is_missing_is_a_defect(self) -> None:
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state(["{run}/in.md"]), self.workflow(), "make"
            )
        self.assertIn("cannot read {run}/in.md", str(caught.exception))

    def test_an_undeclared_step_is_refused(self) -> None:
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state([]), self.workflow(), "check"
            )
        self.assertIn("not a declared step", str(caught.exception))

    def test_a_missing_role_definition_names_the_declared_path(self) -> None:
        """Named the way a reader can look it up. What the process resolved
        still rides along in the operating system's own text, as it does
        everywhere else here; what the message leads with is the declaration."""
        (self.framework / "roles/analyst.md").unlink()
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state([]), self.workflow(), "make"
            )
        self.assertTrue(str(caught.exception).startswith("cannot read roles/analyst.md"))

    def test_a_role_that_links_outside_the_framework_is_refused(self) -> None:
        """A role definition is prompt material like any other, so a framework
        carrying `roles/analyst.md -> /outside/secret` would put that file in
        front of the configured backend."""
        outside = self.base / "secret.md"
        outside.write_text("SECRET\n", encoding="utf-8")
        target = self.framework / "roles/analyst.md"
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state([]), self.workflow(), "make"
            )
        self.assertIn("outside the directory declaring it", str(caught.exception))

    def test_the_role_frontmatter_is_not_spent_on_the_step(self) -> None:
        assembly = assembler.assemble(
            self.framework, self.run_dir, self.state([]), self.workflow(), "make"
        )
        role = next(m for m in assembly.materials if m.kind == "role")
        self.assertNotIn("description: A role.", role.text)
        self.assertIn("# Role: Analyst", role.text)


class ContainmentTest(TreeTest):
    """An artifact path cannot escape by spelling — the schema forbids
    absolute forms and dot segments — but a link inside the run redirects
    without changing the path, and what is read goes into a prompt."""

    def symlink(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")

    def test_a_linked_artifact_is_not_read(self) -> None:
        outside = self.base / "elsewhere.md"
        outside.write_text("a secret\n", encoding="utf-8")
        self.symlink(self.run_dir / "in.md", outside)
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.assemble(
                self.framework, self.run_dir, self.state(["{run}/in.md"]), self.workflow(), "make"
            )
        self.assertIn("in.md", str(caught.exception))

    def test_a_linked_artifact_is_refused_without_dir_fd_too(self) -> None:
        """Where the platform cannot bind an operation to an open directory,
        the component checks are the whole of the containment."""
        outside = self.base / "elsewhere.md"
        outside.write_text("a secret\n", encoding="utf-8")
        self.symlink(self.run_dir / "in.md", outside)
        with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", False):
            with self.assertRaises(assembler.AssemblyError) as caught:
                assembler.assemble(
                    self.framework,
                    self.run_dir,
                    self.state(["{run}/in.md"]),
                    self.workflow(),
                    "make",
                )
        self.assertIn("is a link", str(caught.exception))

    def test_an_artifact_that_is_not_a_regular_file_is_refused(self) -> None:
        """`O_NOFOLLOW` says the name is not a link and nothing about what kind
        of file it is. A FIFO in an artifact's place blocks the open until
        something writes the other end — a command that hangs rather than
        reporting, which is worse than any refusal."""
        if not hasattr(os, "mkfifo"):  # pragma: no cover
            self.skipTest("platform has no FIFOs")
        os.mkfifo(self.run_dir / "in.md")
        # An alarm rather than trust: if the guard regresses this test hangs
        # forever, and a suite that never finishes reports nothing at all. The
        # handler is process-wide, so it is put back: left installed, every
        # later test inherits an alarm that fails them.
        previous = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(5)
        try:
            with self.assertRaises(assembler.AssemblyError) as caught:
                assembler._read_artifact(self.run_dir, "{run}/in.md")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertIn("not a regular file", str(caught.exception))

    def test_a_linked_directory_on_the_way_to_an_artifact_is_not_followed(self) -> None:
        outside = self.base / "elsewhere"
        outside.mkdir()
        (outside / "in.md").write_text("a secret\n", encoding="utf-8")
        self.symlink(self.run_dir / "nested", outside)
        for binds in (True, False):
            if binds and not state._BINDS_TO_DIRECTORY:  # pragma: no cover
                continue
            with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", binds):
                with self.assertRaises(assembler.AssemblyError):
                    assembler._read_artifact(self.run_dir, "{run}/nested/in.md")


class ScaffoldTest(TreeTest):
    def test_the_artifact_is_the_template_byte_for_byte(self) -> None:
        """§8.3: a scaffolded artifact MUST carry every placeholder its
        template defines until the step fills it, so nothing is substituted
        here — filling one by script is filling it for the step."""
        output = self.run_dir / "out.md"
        self.assertTrue(assembler.scaffold(self.load(), self.run_dir, "{run}/out.md"))
        self.assertEqual(output.read_text(encoding="utf-8"), TEMPLATE)
        self.assertIn("[run id]", output.read_text(encoding="utf-8"))

    def test_a_template_keeps_the_line_endings_it_was_authored_with(self) -> None:
        """Byte for byte is the claim, and text mode does not keep it: reading
        a CRLF template through it translates the endings, so the artifact
        would reach the run as something other than the file the contract
        named."""
        crlf = b"# Out: [title]\r\n\r\n[what was found]\r\n"
        (self.framework / "skills/awf-make/references/out.template.md").write_bytes(crlf)
        self.assertTrue(assembler.scaffold(self.load(), self.run_dir, "{run}/out.md"))
        self.assertEqual((self.run_dir / "out.md").read_bytes(), crlf)

    def test_scaffolding_never_overwrites_what_a_step_was_given(self) -> None:
        """A revision, a re-entry, or a gate's recorded direction is exactly
        the content a second scaffold would discard (§7, §8.3)."""
        output = self.run_dir / "out.md"
        output.write_text("# Out: real\n\n## Gate direction\n\nchange the title\n", encoding="utf-8")
        self.assertFalse(assembler.scaffold(self.load(), self.run_dir, "{run}/out.md"))
        self.assertIn("change the title", output.read_text(encoding="utf-8"))

    def test_a_nested_output_gets_the_directories_above_it(self) -> None:
        self.assertTrue(
            assembler.scaffold(self.load(), self.run_dir, "{run}/reports/out.md")
        )
        self.assertEqual(
            (self.run_dir / "reports" / "out.md").read_text(encoding="utf-8"), TEMPLATE
        )

    def test_a_template_that_cannot_be_read_is_reported(self) -> None:
        (self.framework / "skills/awf-make/references/out.template.md").unlink()
        skill = assembler.Skill(
            step_id="make",
            directory=self.framework / "skills/awf-make",
            body="",
            template="references/out.template.md",
            template_dir=self.framework / "skills/awf-make",
            references=(),
        )
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.scaffold(skill, self.run_dir, "{run}/out.md")
        self.assertIn("skills/awf-make/references/out.template.md", str(caught.exception))

    def test_a_template_cannot_reach_outside_its_own_package(self) -> None:
        """The schema constrains a template to a non-empty string and nothing
        more, so the shape is the reader's to hold: a `..` segment reads a file
        the package does not contain and writes it in as the step's artifact —
        traversal by declaration rather than by link."""
        outside = self.base / "secret.md"
        outside.write_text("SECRET\n", encoding="utf-8")
        for escape in (
            "../../secret.md",
            "/etc/passwd",
            "references/../../secret.md",
            # Drive-relative and root-relative Windows forms are not absolute,
            # and joining either on a Windows host discards the skill
            # directory — the rule the config paths already carry.
            "D:secret.md",
            "\\\\host\\share\\secret.md",
            "\\secret.md",
            # Escaping the package is one way to name something other than a
            # file in it; a device basename and a stream marker are the others,
            # and both survive the join that `..` was barred from.
            "references/CON",
            "references/NUL.md",
            "references/out.md::$DATA",
            '"references/out.md "',
        ):
            self.write("skills/awf-make/SKILL.md", SKILL.replace(
                "template: references/out.template.md", f"template: {escape}"
            ))
            with self.assertRaises(assembler.AssemblyError) as caught:
                self.load()
            self.assertIn("template", str(caught.exception))
        self.assertFalse((self.run_dir / "out.md").exists())

    def test_a_stage_declaring_an_escaping_template_never_composes(self) -> None:
        """The guard sits in the reader both carriers share, so the stage's
        copy is refused where it is read — before a run directory exists."""
        self.write(
            "workflows/stages/intake.md",
            STAGE.replace("template: references/out.template.md", "template: ../../secret.md"),
        )
        with self.assertRaises(WorkflowError) as caught:
            self.workflow()
        self.assertIn("not a package path", str(caught.exception))

    def test_a_link_at_the_output_name_reads_the_same_on_both_platforms(self) -> None:
        """`O_EXCL` answers EEXIST for a link as readily as for a file, and the
        two mean opposite things — an artifact the step works from, against a
        name redirecting the run's own artifact out of the run."""
        outside = self.base / "elsewhere.md"
        outside.write_text("SECRET\n", encoding="utf-8")
        try:
            (self.run_dir / "out.md").symlink_to(outside)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        for binds in (True, False):
            if binds and not state._BINDS_TO_DIRECTORY:  # pragma: no cover
                continue
            with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", binds):
                with self.assertRaises(assembler.AssemblyError) as caught:
                    assembler.scaffold(self.load(), self.run_dir, "{run}/out.md")
                self.assertIn("link", str(caught.exception))
        self.assertEqual(outside.read_text(encoding="utf-8"), "SECRET\n")

    def test_a_failed_write_leaves_no_scaffold_behind(self) -> None:
        """An empty or partial file is what the next `O_EXCL` reports as
        EEXIST, and this function reads that as an artifact the step already
        has — so a failed copy would be handed to the step as content to work
        from."""
        if not Path("/dev/fd").is_dir():  # pragma: no cover
            self.skipTest("no /dev/fd to count descriptors with")
        output = self.run_dir / "out.md"
        skill = self.load()
        descriptors = len(os.listdir("/dev/fd"))
        # Only the write fails: `fdopen` is on the framework read path too,
        # and a template that cannot be read is a different failure than a
        # scaffold that cannot be written.
        real = os.fdopen

        def failing(descriptor, mode="r", *rest, **named):
            if mode.startswith("w"):
                raise OSError("no space left on device")
            return real(descriptor, mode, *rest, **named)

        with unittest.mock.patch.object(os, "fdopen", failing):
            with self.assertRaises(assembler.AssemblyError) as caught:
                assembler.scaffold(skill, self.run_dir, "{run}/out.md")
        self.assertIn("cannot scaffold", str(caught.exception))
        self.assertFalse(output.exists())
        # `fdopen` takes ownership only once it returns a stream, so the
        # simulated failure above leaves the descriptor this module opened —
        # and repeated failures would accumulate one apiece.
        self.assertEqual(len(os.listdir("/dev/fd")), descriptors)
        # And the retry that follows writes the whole template rather than
        # reporting the wreckage of the first attempt as already scaffolded.
        self.assertTrue(assembler.scaffold(skill, self.run_dir, "{run}/out.md"))
        self.assertEqual(output.read_text(encoding="utf-8"), TEMPLATE)

    def test_a_stage_declared_template_resolves_beside_the_stage(self) -> None:
        """A template is relative to the file declaring it — the conformance
        suite states that and tests a stage's template living beside the
        stage — so resolving both carriers against the package would read a
        different file than the one CI checked."""
        self.write("workflows/stages/intake.md", STAGE)
        self.write(
            "skills/awf-make/SKILL.md",
            SKILL.replace("        template: references/out.template.md\n", ""),
        )
        self.write("workflows/stages/references/out.template.md", "# From the stage\n")
        skill = self.load()
        self.assertEqual(skill.template_dir, self.framework / "workflows" / "stages")
        self.assertTrue(assembler.scaffold(skill, self.run_dir, "{run}/out.md"))
        self.assertEqual(
            (self.run_dir / "out.md").read_text(encoding="utf-8"), "# From the stage\n"
        )

    def test_a_package_entry_that_links_outside_is_refused(self) -> None:
        """A checked spelling is half of it: `references/x.md` may itself be a
        link, and what this module does with the file is put it in a prompt or
        copy it into a run."""
        outside = self.base / "secret.md"
        outside.write_text("SECRET\n", encoding="utf-8")
        target = self.framework / "skills/awf-make/references/out.template.md"
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(assembler.AssemblyError) as caught:
            assembler.scaffold(self.load(), self.run_dir, "{run}/out.md")
        self.assertIn("outside the directory declaring it", str(caught.exception))
        self.assertFalse((self.run_dir / "out.md").exists())

    def test_an_existing_output_that_is_not_a_regular_file_is_refused(self) -> None:
        """EEXIST says the name is taken, not that what holds it is the
        artifact the step works from."""
        (self.run_dir / "out.md").mkdir()
        for binds in (True, False):
            if binds and not state._BINDS_TO_DIRECTORY:  # pragma: no cover
                continue
            with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", binds):
                with self.assertRaises(assembler.AssemblyError) as caught:
                    assembler.scaffold(self.load(), self.run_dir, "{run}/out.md")
                self.assertIn("not a regular file", str(caught.exception))

    def test_a_scaffold_never_lands_outside_the_run(self) -> None:
        """The one thing here that creates a file, held to the containment
        every read is: a link on the way down would put a run's artifact where
        nothing in the run can see it."""
        outside = self.base / "elsewhere"
        outside.mkdir()
        try:
            (self.run_dir / "reports").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        for binds in (True, False):
            if binds and not state._BINDS_TO_DIRECTORY:  # pragma: no cover
                continue
            with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", binds):
                with self.assertRaises(assembler.AssemblyError):
                    assembler.scaffold(self.load(), self.run_dir, "{run}/reports/out.md")
        self.assertFalse((outside / "out.md").exists())


class RepositoryTest(unittest.TestCase):
    """This repository is the fixture: every step of every shipped workflow
    binds to a skill whose contract agrees with the stage composing it, and
    the assembly is built from the real roles, skills, and references."""

    def test_every_composed_step_loads_the_skill_bound_to_it(self) -> None:
        seen = set()
        for name in ("feature", "bugfix", "plan"):
            workflow = load_workflow(REPO, name)
            for stage in workflow.stages:
                for step_id, declaration in stage.steps.items():
                    skill = assembler.load_skill(REPO, step_id, declaration)
                    self.assertTrue(skill.body.strip())
                    seen.add(step_id)
        # The eighteen step-bound skills skills/README.md counts, reached
        # through the compositions rather than by listing the directory.
        self.assertEqual(len(seen), 18)

    def test_the_shipped_steps_that_scaffold_are_the_ones_with_templates(self) -> None:
        workflow = load_workflow(REPO, "feature")
        without = {
            step_id
            for stage in workflow.stages
            for step_id, declaration in stage.steps.items()
            if assembler.load_skill(REPO, step_id, declaration).template is None
        }
        # Each writes an artifact an earlier step already scaffolded: the
        # brief's routing section, the plan under revision, the ideation
        # under revision.
        self.assertEqual(without, {"risk-route", "plan-revise", "ideate-revise"})

    def test_a_real_step_assembles_from_the_real_framework(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "runs" / "2026-08-26-x"
        run_dir.mkdir(parents=True)
        (run_dir / "brief.md").write_text("# Brief\n\nBuild the thing.\n", encoding="utf-8")
        (run_dir / "phase-1-impl-validation.md").write_text("# Phase 1\n", encoding="utf-8")
        workflow = load_workflow(REPO, "feature")
        loaded = RunState(
            run_id="2026-08-26-x",
            workflow="feature",
            protocol="0.2",
            steps=[StepRecord(id="plan-create", status="pending")],
            gates=[],
            artifacts=["{run}/brief.md", "{run}/phase-1-impl-validation.md"],
            phase=2,
            risk="R2",
            risk_rationale="one module",
        )
        assembly = assembler.assemble(REPO, run_dir, loaded, workflow, "plan-create")
        self.assertEqual(assembly.role, "planner")
        self.assertEqual(assembly.output, "{run}/phase-2-plan.md")
        sources = [m.source for m in assembly.materials]
        self.assertEqual(sources[0], "roles/planner.md")
        self.assertEqual(sources[1], "skills/awf-plan-create/SKILL.md")
        # Phase 2 is executing, so the `{P}` set is phase 1 alone — the
        # binding the earlier phase set, reaching the plan that must respect it.
        self.assertIn("{run}/phase-1-impl-validation.md", sources)
        self.assertIn("skills/awf-plan-create/references/plan.template.md", sources)
        self.assertIn("Build the thing.", assembly.prompt)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
