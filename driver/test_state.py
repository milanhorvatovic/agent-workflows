"""Unit tests for state.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driver import state
from driver.test_workflow import STAGE, WORKFLOW
from driver.workflow import load_workflow

REPO = Path(__file__).resolve().parent.parent


class StateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        (self.base / "workflows" / "stages").mkdir(parents=True)
        (self.base / "workflows" / "demo.md").write_text(WORKFLOW, encoding="utf-8")
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            STAGE, encoding="utf-8"
        )
        self.workflow = load_workflow(self.base, "demo")
        self.runs = self.base / "artifacts" / "runs"


class CreateRunTest(StateTestCase):
    def test_bootstraps_the_entry_stage_records_alone(self) -> None:
        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        self.assertEqual(run_dir, self.runs / "2026-08-17-x")
        self.assertTrue((run_dir / state.STATE_FILE).is_file())
        self.assertEqual(
            [(s.id, s.status) for s in created.steps],
            [("make", "pending"), ("check", "skipped")],
        )
        self.assertIsNone(created.risk)
        self.assertEqual(created.artifacts, [])

    def test_round_trips_through_load(self) -> None:
        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        loaded = state.load(run_dir)
        self.assertEqual(loaded, created)

    def test_refuses_an_existing_run_directory(self) -> None:
        state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        with self.assertRaises(state.StateError) as caught:
            state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        self.assertIn("already exists", str(caught.exception))

    def test_refuses_an_id_that_is_not_a_plain_directory_name(self) -> None:
        for run_id in (
            "../x", "a/b", "C:run", "x.", "x ", "a\x85b", "..",
            "a:b", "NUL", "com\u00b9", "demo?", "a|b", "a\u2028b",
        ):
            with self.subTest(run_id=run_id):
                with self.assertRaises(state.StateError):
                    state.create_run(self.runs, run_id, self.workflow, "0.2")


class PositionTest(StateTestCase):
    def test_active_record_takes_precedence_over_position(self) -> None:
        _, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        created.steps.append(state.StepRecord(id="later", status="pending"))
        created.record("later").status = "active"
        self.assertEqual(created.position().id, "later")

    def test_position_is_the_first_record_neither_done_nor_skipped(self) -> None:
        _, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        self.assertEqual(created.position().id, "make")
        created.record("make").status = "done"
        self.assertIsNone(created.position())

    def test_a_blocked_gate_is_the_position(self) -> None:
        """§7: a gate waiting on a human is `blocked`, and a resume returns
        to it rather than past it."""
        _, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        created.record("make").status = "done"
        created.record("check").status = "blocked"
        self.assertEqual(created.position().id, "check")


class TransitionTest(StateTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_dir, self.state = state.create_run(
            self.runs, "2026-08-17-x", self.workflow, "0.2"
        )

    def test_start_marks_the_record_active(self) -> None:
        record = state.start_step(self.state, "make")
        self.assertEqual(record.status, "active")

    def test_a_second_active_record_is_refused(self) -> None:
        state.start_step(self.state, "make")
        self.state.steps.append(state.StepRecord(id="other", status="pending"))
        with self.assertRaises(state.StateError) as caught:
            state.start_step(self.state, "other")
        self.assertIn("at most one", str(caught.exception))

    def test_complete_manifests_the_declared_output(self) -> None:
        state.start_step(self.state, "make")
        state.complete_step(self.state, self.workflow, "make")
        self.assertEqual(self.state.record("make").status, "done")
        self.assertEqual(self.state.artifacts, ["{run}/out.md"])
        state.save(self.state, self.run_dir)
        self.assertEqual(state.load(self.run_dir).artifacts, ["{run}/out.md"])

    def test_complete_resolves_the_phase_placeholder(self) -> None:
        phased = STAGE.replace('artifact: "{run}/out.md"', 'artifact: "{run}/phase-{N}-out.md"')
        (self.base / "workflows" / "stages" / "demo.md").write_text(phased, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        self.state.phase = 2
        state.start_step(self.state, "make")
        state.complete_step(self.state, workflow, "make")
        self.assertEqual(self.state.artifacts, ["{run}/phase-2-out.md"])

    def test_completing_a_step_that_is_not_active_is_refused(self) -> None:
        with self.assertRaises(state.StateError):
            state.complete_step(self.state, self.workflow, "make")

    def test_route_follows_the_declared_edge(self) -> None:
        target = state.route_verdict(self.state, self.workflow, "make", "PASS")
        self.assertEqual(target, "check")
        # The skipped conditional gate was routed to, so it re-enters pending.
        self.assertEqual(self.state.record("check").status, "pending")

    def test_route_without_an_edge_escalates(self) -> None:
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, self.workflow, "make", "PASS_WITH_CONDITIONS")
        self.assertIn("escalate", str(caught.exception))

    def test_route_to_a_stage_id_resolves_to_its_first_runnable_record(self) -> None:
        stage_edge = STAGE.replace("        PASS: check\n", "        PASS: demo\n")
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            stage_edge, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        target = state.route_verdict(self.state, workflow, "make", "PASS")
        self.assertEqual(target, "make")


class LoadValidationTest(StateTestCase):
    def write_state(self, text: str) -> Path:
        run_dir = self.runs / "demo-run"
        run_dir.mkdir(parents=True)
        (run_dir / state.STATE_FILE).write_text(text, encoding="utf-8")
        return run_dir

    BASE = (
        "run:\n  id: demo-run\n  workflow: demo\n  protocol: \"0.2\"\n"
        "steps:\n  - id: make\n    status: pending\n"
        "gates: []\nartifacts: []\n"
    )

    def test_loads_the_minimal_document(self) -> None:
        loaded = state.load(self.write_state(self.BASE))
        self.assertEqual(loaded.run_id, "demo-run")
        self.assertFalse(loaded.has_instrumentation)

    def test_plain_name_is_the_schema_pattern(self) -> None:
        """The literal mirrors the run-state schema's id pattern — the schema
        is the source of truth, and this pin is what keeps the two from
        drifting apart silently."""
        import json

        schema = json.loads(
            (REPO / "protocol" / "schemas" / "run-state.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            state.PLAIN_NAME.pattern,
            schema["properties"]["run"]["properties"]["id"]["pattern"],
        )

    def test_imports_load_validate_and_round_trip(self) -> None:
        run_dir = self.runs / "with-imports"
        run_dir.mkdir(parents=True)
        (run_dir / state.STATE_FILE).write_text(
            self.BASE.replace(
                "artifacts: []\n",
                'artifacts:\n  - "{run}/brief.md"\n'
                "imports:\n"
                '  - artifact: "{run}/brief.md"\n'
                "    from: 2026-08-12-plan-slug\n"
                '    at: "2026-08-16T09:00:00Z"\n',
            ),
            encoding="utf-8",
        )
        loaded = state.load(run_dir)
        (record,) = loaded.imports
        self.assertEqual(record.from_run, "2026-08-12-plan-slug")
        state.save(loaded, run_dir)
        self.assertEqual(state.load(run_dir), loaded)

    def test_import_rejections(self) -> None:
        cases = {
            "unmanifested import": (
                'artifacts: []\n'
                'imports:\n  - artifact: "{run}/brief.md"\n'
                "    from: earlier-run\n    at: \"2026-08-16T09:00:00Z\"\n"
            ),
            "self-import": (
                'artifacts:\n  - "{run}/brief.md"\n'
                'imports:\n  - artifact: "{run}/brief.md"\n'
                "    from: demo-run\n    at: \"2026-08-16T09:00:00Z\"\n"
            ),
            "empty imports": ('artifacts: []\nimports: []\n'),
        }
        for name, tail in cases.items():
            run_dir = self.runs / f"imp-{abs(hash(name))}"
            run_dir.mkdir(parents=True)
            (run_dir / state.STATE_FILE).write_text(
                self.BASE.replace("artifacts: []\n", tail), encoding="utf-8"
            )
            with self.subTest(case=name):
                with self.assertRaises(state.StateError):
                    state.load(run_dir)

    def test_loads_every_shipped_valid_fixture(self) -> None:
        fixtures = sorted(
            (REPO / "protocol" / "schemas" / "examples").glob("run-state.valid*.yaml")
        )
        self.assertTrue(fixtures)
        for path in fixtures:
            run_dir = self.runs / f"fixture-{path.stem}"
            run_dir.mkdir(parents=True)
            (run_dir / state.STATE_FILE).write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            with self.subTest(fixture=path.name):
                loaded = state.load(run_dir)
                self.assertTrue(loaded.steps)
                state.save(loaded, run_dir)
                self.assertEqual(state.load(run_dir), loaded)

    def test_rejections(self) -> None:
        cases = {
            "unknown top-level key": self.BASE + "surprise: true\n",
            "risk without rationale": self.BASE.replace(
                "  workflow: demo\n", "  workflow: demo\n  risk: R2\n"
            ),
            "unknown status": self.BASE.replace("status: pending", "status: running"),
            "duplicate record": self.BASE.replace(
                "steps:\n  - id: make\n    status: pending\n",
                "steps:\n  - id: make\n    status: pending\n  - id: make\n    status: done\n",
            ),
            "two active records": self.BASE.replace(
                "steps:\n  - id: make\n    status: pending\n",
                "steps:\n  - id: make\n    status: active\n  - id: also\n    status: active\n",
            ),
            "drive-relative id": self.BASE.replace("id: demo-run", 'id: "C:demo"'),
        }
        for name, text in cases.items():
            run_dir = self.runs / f"bad-{abs(hash(name))}"
            run_dir.mkdir(parents=True)
            (run_dir / state.STATE_FILE).write_text(text, encoding="utf-8")
            with self.subTest(case=name):
                with self.assertRaises(state.StateError):
                    state.load(run_dir)

    def test_an_undecodable_state_file_is_a_state_error(self) -> None:
        """Not UTF-8 is a defect in the document: it must be reported like
        every other malformation, never escape as a decoding traceback."""
        run_dir = self.runs / "demo-run"
        run_dir.mkdir(parents=True)
        (run_dir / state.STATE_FILE).write_bytes(b"run:\n  id: \xff\xfe\n")
        with self.assertRaises(state.StateError) as caught:
            state.load(run_dir)
        self.assertIn("cannot read", str(caught.exception))

    def test_missing_state_file_is_a_state_error(self) -> None:
        run_dir = self.runs / "empty-run"
        run_dir.mkdir(parents=True)
        with self.assertRaises(state.StateError) as caught:
            state.load(run_dir)
        self.assertIn("cannot read", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
