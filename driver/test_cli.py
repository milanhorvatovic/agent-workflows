"""Unit tests for cli.py.

Run from the repo root: python3 -m unittest discover -s driver -t .
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from driver import cli
from driver.test_config import VALID
from driver.test_workflow import STAGE, WORKFLOW


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.config_path = self.base / "driver.json"
        self.config_path.write_text(json.dumps(VALID), encoding="utf-8")

    def invoke(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_status_lists_run_directories_sorted(self) -> None:
        runs = self.base / "runs"
        (runs / "2026-08-13-feature-two").mkdir(parents=True)
        (runs / "2026-08-12-bugfix-one").mkdir()
        (runs / "stray-file.txt").write_text("not a run\n", encoding="utf-8")
        code, out, _ = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-08-12-bugfix-one\n2026-08-13-feature-two\n")

    def test_status_with_no_runs_directory_prints_nothing(self) -> None:
        code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_status_rejects_a_runs_path_that_is_not_a_directory(self) -> None:
        (self.base / "runs").write_text("not a directory\n", encoding="utf-8")
        code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("is not a directory", err)

    def write_framework(self) -> None:
        stages = self.base / "workflows" / "stages"
        stages.mkdir(parents=True)
        (self.base / "workflows" / "demo.md").write_text(WORKFLOW, encoding="utf-8")
        (stages / "intake.md").write_text(STAGE, encoding="utf-8")

    def test_run_creates_the_run_and_stops_at_execution(self) -> None:
        self.write_framework()
        code, out, err = self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 1)
        self.assertIn("created", out)
        self.assertIn("next is make (pending)", out)
        self.assertIn("have not landed", err)
        self.assertTrue(
            (self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml").is_file()
        )

    def test_run_without_a_workflow_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["run", "2026-08-17-x", "--config", str(self.config_path)])
        self.assertEqual(caught.exception.code, 2)

    def test_run_on_a_missing_workflow_is_a_config_defect(self) -> None:
        code, _, err = self.invoke(
            "run", "--workflow", "absent", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read workflow", err)

    def test_run_refuses_an_existing_run_id(self) -> None:
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        code, _, err = self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_resume_resolves_the_position_of_a_created_run(self) -> None:
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 1)
        self.assertIn("next is make (pending)", out)
        self.assertIn("have not landed", err)

    def test_resume_on_a_missing_run_is_a_defect(self) -> None:
        """Reported at whichever level is actually absent: the runs root
        the artifact root should hold, or the state inside a run."""
        code, _, err = self.invoke(
            "resume", "2026-08-12-bugfix-one", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot open", err)
        (self.base / "runs").mkdir()
        code, _, err = self.invoke(
            "resume", "2026-08-12-bugfix-one", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_resume_reports_a_finished_run_as_success(self) -> None:
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        # A finished run is one whose done step also manifested what it
        # declared (§8.2) — marking the status alone builds the invalid
        # document `resume` now refuses rather than reports finished.
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        state_path.write_text(
            state_path.read_text(encoding="utf-8")
            .replace("status: pending", "status: done")
            .replace("artifacts: []", 'artifacts:\n  - "{run}/out.md"'),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 0)
        self.assertIn("nothing left to run", out)
        self.assertEqual(err, "")

    def test_resume_never_follows_a_linked_run_directory(self) -> None:
        """`status` excludes links for this reason; resume has to refuse the
        same escape, or a link under runs/ reads state outside the root."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        outside = self.base / "elsewhere"
        outside.mkdir()
        try:
            (self.base / "runs" / "linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        code, _, err = self.invoke("resume", "linked", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertIn("is a link", err)

    def test_resume_refuses_state_that_names_another_run(self) -> None:
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        copied = self.base / "runs" / "2026-08-18-copy"
        copied.mkdir()
        (copied / "workflow-state.yaml").write_text(
            (self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-18-copy", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("names run '2026-08-17-x'", err)
        self.assertEqual(out, "")

    def test_resume_refuses_a_run_whose_manifest_is_short(self) -> None:
        """§8.2 ties a done step to its manifested output, and reporting a
        run finished trusts the same document routing refuses to act on: a
        truncated manifest would otherwise answer "nothing left to run" for
        a run the conformance suite rejects."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        state_path.write_text(
            state_path.read_text(encoding="utf-8").replace(
                "status: pending", "status: done"
            ),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("not in the manifest", err)
        self.assertEqual(out, "")

    def test_resume_refuses_records_the_composition_does_not_declare(self) -> None:
        """§10 makes declared membership and order what §8.5's resume reads,
        and the schema cannot constrain either — so a swapped pair changes
        where a resume lands with nothing to say it did."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        original = state_path.read_text(encoding="utf-8")
        for name, document in {
            "swapped order": original.replace(
                "  - id: make\n    status: pending\n  - id: check\n    status: skipped\n",
                "  - id: check\n    status: skipped\n  - id: make\n    status: pending\n",
            ),
            "undeclared id": original.replace("id: make", "id: phantom"),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(document, encoding="utf-8")
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(
                    "declare" in err or "recorded after" in err, err
                )

    def test_resume_refuses_a_pre_acceptance_list_short_of_the_entry_stage(self) -> None:
        """§10's pre-acceptance list is the entry stage's records alone, and
        alone is a bound on both sides: the acceptance creates what comes
        after, and nothing creates the entry stage's own records after
        creation does. An empty list would otherwise resolve to no position
        at all — `resume` reporting nothing left to run for a run that never
        reached its first step."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        original = state_path.read_text(encoding="utf-8")
        for name, document in {
            "no records at all": original.replace(
                "steps:\n  - id: make\n    status: pending\n"
                "  - id: check\n    status: skipped\n",
                "steps: []\n",
            ),
            "a member missing": original.replace("  - id: check\n    status: skipped\n", ""),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(document, encoding="utf-8")
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("check", err)

    def test_a_gate_position_names_the_module_that_clears_it(self) -> None:
        """A gate waits on a human (§7): no context assembler or backend can
        clear it, and which kind a record is comes from the composition
        rather than from its status."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        state_path.write_text(
            state_path.read_text(encoding="utf-8")
            .replace("  - id: make\n    status: pending", "  - id: make\n    status: done")
            .replace("status: skipped", "status: blocked")
            .replace("artifacts: []", 'artifacts:\n  - "{run}/out.md"'),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 1)
        self.assertIn("next is check (blocked)", out)
        self.assertIn("gate handler", err)
        self.assertNotIn("invocation backend", err)

    def test_resume_refuses_a_gate_whose_decision_does_not_stand(self) -> None:
        """§7 and §10: a gate's `steps` entry is `done` only once its
        decision stands, and `gates` is appended in decision order, so the
        latest entry is the one that has to — never the best on file."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        finished = (
            state_path.read_text(encoding="utf-8")
            .replace("  - id: make\n    status: pending", "  - id: make\n    status: done")
            .replace("status: skipped", "status: done")
            .replace("artifacts: []", 'artifacts:\n  - "{run}/out.md"')
        )
        for name, gates in {
            "no decision at all": "gates: []\n",
            "latest outcome is a revise": (
                "gates:\n  - gate: check\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z"\n'
                "  - gate: check\n    transport: blocking\n"
                '    outcome: revise\n    at: "2026-08-16T10:00:00Z"\n'
            ),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(
                    finished.replace("gates: []\n", gates), encoding="utf-8"
                )
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("gate 'check'", err)

    def test_resume_refuses_a_phase_on_a_gate_that_decides_once_per_run(self) -> None:
        """§10: a gate a phase repeats names the phase its decision was taken
        in, and a gate that decides once per run records none. Which kind a
        gate is comes from its stage's contracts — `demo` writes no `{N}`
        output, so `check` decides once — and a phase recorded against it
        stands for a phase of a stage that has none."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        original = state_path.read_text(encoding="utf-8").replace(
            "  - id: make\n    status: pending", "  - id: make\n    status: done"
        ).replace("artifacts: []", 'artifacts:\n  - "{run}/out.md"')
        for name, (status, gates) in {
            "the standing decision": (
                "done",
                "gates:\n  - gate: check\n    phase: 1\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z"\n',
            ),
            # Every entry is a decision the gate recorded, so a superseded one
            # carries the field it was never entitled to just as plainly.
            "a decision that did not stand": (
                "pending",
                "gates:\n  - gate: check\n    phase: 1\n    transport: blocking\n"
                '    outcome: revise\n    at: "2026-08-16T09:00:00Z"\n',
            ),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(
                    original.replace("status: skipped", f"status: {status}").replace(
                        "gates: []\n", gates
                    ),
                    encoding="utf-8",
                )
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("gate 'check'", err)
                self.assertIn("once per run", err)

    def test_resume_refuses_a_class_no_gate_decision_accepted(self) -> None:
        """§7 and §10: the class in `run.risk` is what the intake gate
        accepted, and that acceptance is one write — the class, the gate's
        `done`, and the populated list together. State is loaded, not
        trusted, so a document that carries the class while the stage's
        closing gate never decided has the authority of the acceptance
        without the acceptance, and every check keyed on `run.risk` reads
        the post-intake shape as established."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        original = state_path.read_text(encoding="utf-8").replace(
            '  protocol: "0.2"\n',
            '  protocol: "0.2"\n  risk: R1\n  risk_rationale: "small"\n',
        )
        for name, document in {
            # The gate the class came from was never reached.
            "the gate is skipped": original,
            "the gate is waiting": original.replace(
                "  - id: check\n    status: skipped", "  - id: check\n    status: blocked"
            ),
            # Decided, and the decision that stands is not an acceptance.
            "the decision is a revise": original.replace(
                "  - id: check\n    status: skipped", "  - id: check\n    status: pending"
            ).replace(
                "gates: []\n",
                "gates:\n  - gate: check\n    transport: blocking\n"
                '    outcome: revise\n    at: "2026-08-16T09:00:00Z"\n',
            ),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(document, encoding="utf-8")
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("check", err)

    def test_resume_reads_a_class_its_gate_did_accept(self) -> None:
        """The other side of the same rule: an acceptance on file is what
        makes the class readable, and a run past its intake gate resumes.

        Past it in both senses — the gate decides where it stands in its
        stage, so the step ahead of it is behind it too. A document with
        the gate `done` over work still to run is one no transition writes,
        and this one built it until the check for that landed.
        """
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        state_path.write_text(
            state_path.read_text(encoding="utf-8")
            .replace(
                '  protocol: "0.2"\n',
                '  protocol: "0.2"\n  risk: R1\n  risk_rationale: "small"\n',
            )
            .replace("  - id: make\n    status: pending", "  - id: make\n    status: done")
            .replace("  - id: check\n    status: skipped", "  - id: check\n    status: done")
            .replace("artifacts: []", 'artifacts:\n  - "{run}/out.md"')
            .replace(
                "gates: []\n",
                "gates:\n  - gate: check\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z"\n',
            ),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 0)
        self.assertIn("nothing left to run", out)
        self.assertEqual(err, "")

    def test_resume_refuses_a_decision_by_a_gate_nothing_declares(self) -> None:
        """§7 makes `gates` the record of the run's own decisions, so an
        entry naming a gate no composed stage declares is instrumentation
        nothing wrote — and read as a gate of unknown scope it escapes the
        phase rule every declared one is held to."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        state_path.write_text(
            state_path.read_text(encoding="utf-8").replace(
                "gates: []\n",
                "gates:\n  - gate: phantom\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z"\n',
            ),
            encoding="utf-8",
        )
        code, out, err = self.invoke(
            "resume", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("phantom", err)

    def test_resume_refuses_a_status_the_member_kind_does_not_own(self) -> None:
        """§10 gives the two working statuses to different kinds: `active`
        is the step currently running, `blocked` a gate waiting on its
        outcome. Either on the wrong kind is a position neither path can
        advance, so a resume would land there and stop."""
        self.write_framework()
        self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        state_path = self.base / "runs" / "2026-08-17-x" / "workflow-state.yaml"
        original = state_path.read_text(encoding="utf-8")
        for name, document in {
            "a step marked blocked": original.replace(
                "  - id: make\n    status: pending", "  - id: make\n    status: blocked"
            ),
            "a gate marked active": original.replace(
                "  - id: check\n    status: skipped", "  - id: check\n    status: active"
            ),
        }.items():
            with self.subTest(case=name):
                state_path.write_text(document, encoding="utf-8")
                code, out, err = self.invoke(
                    "resume", "2026-08-17-x", "--config", str(self.config_path)
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue("is blocked" in err or "is active" in err, err)

    def test_resume_without_a_run_id_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["resume", "--config", str(self.config_path)])
        self.assertEqual(caught.exception.code, 2)

    def test_resume_rejects_run_ids_that_are_not_plain_directory_names(self) -> None:
        for run_id in (
            "../other-run",
            "/tmp/run",
            ".",
            "..",
            "a/b",
            "a\\b",
            "C:run",
            "a\x00b",
            "a\nb",
            "a\rb",
            "a\x85b",
            "a\u2028b",
            "demo.",
            "demo ",
            "demo?",
            "a*b",
            'a"b',
            "a<b",
            "a|b",
            "NUL",
            "nul.md",
            "COM1",
            "com\u00b9",
            "LPT\u00b3.log",
            "aux:stream",
            "  ",
        ):
            with self.subTest(run_id=run_id):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        cli.main(["resume", run_id, "--config", str(self.config_path)])
                self.assertEqual(caught.exception.code, 2)

    def test_resume_refuses_any_colon_in_a_run_id(self) -> None:
        # Every colon is refused — an NTFS `name:stream` is a stream rather
        # than a child directory — which retires the ISO-timestamp allowance
        # the first cut of this guard made: an id only POSIX can create is a
        # state file only POSIX can share.
        for run_id in ("2026-08-17T09:58:06-fix", "demo:stream"):
            with self.subTest(run_id=run_id):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        cli.main(["resume", run_id, "--config", str(self.config_path)])
                self.assertEqual(caught.exception.code, 2)

    def test_status_reports_an_unreadable_runs_directory(self) -> None:
        (self.base / "runs").mkdir()
        with unittest.mock.patch(
            "driver.cli.os.scandir", side_effect=PermissionError("permission denied")
        ):
            code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("cannot read", err)

    def test_status_reports_a_child_it_cannot_classify(self) -> None:
        # A vanished child raises FileNotFoundError, which must read as a
        # defect here — only absence of the runs directory itself is the
        # zero-runs case.
        for failure in (PermissionError("permission denied"), FileNotFoundError("vanished")):
            with self.subTest(failure=type(failure).__name__):
                (self.base / "runs").mkdir(exist_ok=True)
                entry = unittest.mock.Mock()
                entry.name = "2026-08-13-feature-one"
                entry.is_dir.side_effect = failure
                # The real scandir object is its own iterator and context
                # manager; the mock must honor both halves of that contract.
                scandir_result = unittest.mock.MagicMock()
                scandir_result.__enter__.return_value = scandir_result
                scandir_result.__iter__.return_value = iter([entry])
                with unittest.mock.patch(
                    "driver.cli.os.scandir", return_value=scandir_result
                ):
                    code, out, err = self.invoke("status", "--config", str(self.config_path))
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("cannot read", err)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_status_never_lists_a_symlink_as_a_run(self) -> None:
        runs = self.base / "runs"
        (runs / "2026-08-17-real-run").mkdir(parents=True)
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (runs / "2026-08-17-linked").symlink_to(elsewhere, target_is_directory=True)
        code, out, _ = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-08-17-real-run\n")

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_status_reports_a_dangling_runs_symlink(self) -> None:
        (self.base / "runs").symlink_to(self.base / "absent", target_is_directory=True)
        code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("dangling link", err)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_status_reports_a_dangling_artifact_root_link(self) -> None:
        config = dict(VALID, artifacts_dir="linked")
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        (self.base / "linked").symlink_to(self.base / "absent", target_is_directory=True)
        code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("dangling link", err)

    def test_status_never_lists_a_junction_as_a_run(self) -> None:
        # A junction cannot be created on the POSIX CI runner, so the entry
        # is staged: a directory by classification, not a symlink, carrying
        # the reparse attribute that marks junctions on Windows.
        (self.base / "runs").mkdir()
        entry = unittest.mock.Mock()
        entry.name = "2026-08-17-junction"
        entry.is_dir.return_value = True
        entry.is_symlink.return_value = False
        entry.stat.return_value = unittest.mock.Mock(
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        scandir_result = unittest.mock.MagicMock()
        scandir_result.__enter__.return_value = scandir_result
        scandir_result.__iter__.return_value = iter([entry])
        with unittest.mock.patch("driver.cli.os.scandir", return_value=scandir_result):
            code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    @unittest.skipIf(os.name == "nt", "POSIX directory-name semantics")
    def test_status_reports_a_run_name_a_line_cannot_carry(self) -> None:
        (self.base / "runs" / "bad\nname").mkdir(parents=True)
        code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("control characters", err)

    def test_config_defect_names_the_file_and_exits_2(self) -> None:
        self.config_path.write_text("{not json", encoding="utf-8")
        code, _, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertIn(str(self.config_path), err)
        self.assertIn("invalid JSON", err)

    def test_run_with_a_broken_config_fails_on_the_config(self) -> None:
        self.config_path.write_text("{}", encoding="utf-8")
        code, _, err = self.invoke(
            "run", "--workflow", "demo", "2026-08-17-x", "--config", str(self.config_path)
        )
        self.assertEqual(code, 2)
        self.assertIn("backends must be a non-empty object", err)

    def test_missing_command_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main([])
        self.assertEqual(caught.exception.code, 2)

    def test_missing_config_option_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["status"])
        self.assertEqual(caught.exception.code, 2)

    def test_module_entry_point_dispatches(self) -> None:
        (self.base / "runs" / "2026-08-13-feature-one").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, "-m", "driver", "status", "--config", str(self.config_path)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "2026-08-13-feature-one\n")


if __name__ == "__main__":
    unittest.main()
