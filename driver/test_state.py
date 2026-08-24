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

    def test_a_failed_first_save_leaves_the_id_usable(self) -> None:
        """§8.1 refuses a pre-existing run directory, so an empty one left
        behind by a failed first write would burn the id: the retry meets
        "already exists" and the run it names has no state to resume."""
        import unittest.mock

        with unittest.mock.patch.object(state, "save", side_effect=OSError("no space")):
            with self.assertRaises(OSError):
                state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertFalse((self.runs / "2026-08-19-x").exists())
        run_dir, created = state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertTrue((run_dir / state.STATE_FILE).is_file())
        self.assertEqual(created.run_id, "2026-08-19-x")

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
        record = state.start_step(self.state, self.workflow, "make")
        self.assertEqual(record.status, "active")

    def test_a_second_active_record_is_refused(self) -> None:
        two_steps = STAGE.replace(
            "        - step: make\n", "        - step: make\n        - step: also\n"
        ).replace(
            "## Gates",
            "### also (planner)\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: planner\n      output:\n'
            '        artifact: "{run}/also.md"\n```\n\n## Gates',
        )
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            two_steps, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        _, created = state.create_run(self.runs, "two-steps", workflow, "0.2")
        state.start_step(created, workflow, "make")
        with self.assertRaises(state.StateError) as caught:
            state.start_step(created, workflow, "also")
        self.assertIn("at most one", str(caught.exception))

    def test_only_a_declared_step_starts_and_only_from_pending(self) -> None:
        """`steps` holds gates too, and a gate has no output to produce:
        marking one active would have to be undone by a completion that
        refuses it, after the state was already written."""
        with self.assertRaises(state.StateError) as caught:
            state.start_step(self.state, self.workflow, "check")
        self.assertIn("not a declared step", str(caught.exception))
        self.assertEqual(self.state.record("check").status, "skipped")
        for status in ("done", "skipped", "blocked"):
            with self.subTest(status=status):
                self.state.record("make").status = status
                with self.assertRaises(state.StateError) as caught:
                    state.start_step(self.state, self.workflow, "make")
                self.assertIn("starts from pending", str(caught.exception))
        # A resume returns to the record that was running and starts it again.
        self.state.record("make").status = "active"
        self.assertEqual(
            state.start_step(self.state, self.workflow, "make").status, "active"
        )

    def test_complete_manifests_the_declared_output(self) -> None:
        state.start_step(self.state, self.workflow, "make")
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
        state.start_step(self.state, self.workflow, "make")
        state.complete_step(self.state, workflow, "make")
        self.assertEqual(self.state.artifacts, ["{run}/phase-2-out.md"])

    def test_completing_a_step_that_is_not_active_is_refused(self) -> None:
        with self.assertRaises(state.StateError):
            state.complete_step(self.state, self.workflow, "make")

    def test_completing_a_record_the_composition_declares_no_step_for(self) -> None:
        """A gate's record is closed by its outcome, not by completion: a
        completion that manifests nothing must refuse rather than retire the
        record from resume with the manifest left short."""
        gate = self.state.record("check")
        gate.status = "active"
        with self.assertRaises(state.StateError) as caught:
            state.complete_step(self.state, self.workflow, "check")
        self.assertIn("not a declared step", str(caught.exception))
        self.assertEqual(gate.status, "active")
        self.assertEqual(self.state.artifacts, [])

    def test_route_follows_the_declared_edge(self) -> None:
        target = state.route_verdict(self.state, self.workflow, "make", "PASS")
        self.assertEqual(target, "check")
        # The skipped conditional gate was routed to, so it re-enters pending.
        self.assertEqual(self.state.record("check").status, "pending")

    def test_route_without_an_edge_escalates(self) -> None:
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, self.workflow, "make", "PASS_WITH_CONDITIONS")
        self.assertIn("escalate", str(caught.exception))

    def test_route_to_a_stage_id_resolves_to_its_first_runnable_step(self) -> None:
        stage_edge = STAGE.replace("        PASS: check\n", "        PASS: demo\n")
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            stage_edge, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        target = state.route_verdict(self.state, workflow, "make", "PASS")
        self.assertEqual(target, "make")

    def test_a_stage_target_passes_over_a_gate_to_reach_the_step(self) -> None:
        """§9.1 makes a stage id stand for the stage's first step; a gate
        ahead of it in the sequence is a member, not that step."""
        gate_first = STAGE.replace(
            "        - step: make\n        - gate: check\n          conditional: true\n",
            "        - gate: check\n        - step: make\n",
        ).replace("        PASS: check\n", "        PASS: demo\n")
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            gate_first, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        _, created = state.create_run(self.runs, "gate-first", workflow, "0.2")
        self.assertEqual([s.id for s in created.steps], ["check", "make"])
        target = state.route_verdict(created, workflow, "make", "PASS")
        self.assertEqual(target, "make")

    def test_a_stage_target_with_no_runnable_step_escalates(self) -> None:
        stage_edge = STAGE.replace("        PASS: check\n", "        PASS: demo\n")
        (self.base / "workflows" / "stages" / "demo.md").write_text(
            stage_edge, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        self.state.record("make").status = "skipped"
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, workflow, "make", "PASS")
        self.assertIn("no runnable step", str(caught.exception))


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

    def test_the_patterns_are_the_schema_patterns(self) -> None:
        """The literals mirror the run-state schema's own — the schema is the
        source of truth, and these pins are what keep the two from drifting
        apart silently."""
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
        self.assertEqual(
            state.IMPORT_PATH.pattern,
            schema["$defs"]["importRecord"]["properties"]["artifact"]["pattern"],
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
            "import timestamp is prose": (
                'artifacts:\n  - "{run}/brief.md"\n'
                'imports:\n  - artifact: "{run}/brief.md"\n'
                '    from: earlier-run\n    at: "yesterday"\n'
            ),
        }
        # Paths the schema's pattern refuses, each manifested so that the
        # path itself is what the load rejects: an unsafe destination
        # presented as validated lineage is what a later materialization
        # would copy to.
        for unsafe in (
            "{run}/../outside.md",
            "{run}//brief.md",
            "{run}/./brief.md",
            "{run}/sub\\brief.md",
            "{run}/brief.md:stream",
            "{run}/NUL",
            "{run}/brief.md ",
            "{run}",
        ):
            cases[f"unsafe path {unsafe}"] = (
                f'artifacts:\n  - "{unsafe}"\n'
                f'imports:\n  - artifact: "{unsafe}"\n'
                '    from: earlier-run\n    at: "2026-08-16T09:00:00Z"\n'
            )
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
            # §10's enrichment is a mapping or null, and this module writes
            # back what it accepts — so a scalar here would make the driver
            # the source of the invalid state, not just its reader.
            # §10 declares every `at` an RFC 3339 date-time, and the suite's
            # format checker holds the fixtures to it — so a bare string
            # accepted here is state the driver writes and the suite rejects.
            "gate timestamp is prose": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    transport: blocking\n"
                '    outcome: accept\n    at: "not-a-timestamp"\n',
            ),
            "gate timestamp has no offset": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00"\n',
            ),
            "gate timestamp is not a date": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-02-30T09:00:00Z"\n',
            ),
            "instrumentation is a scalar": self.BASE + 'instrumentation: "tokens"\n',
            "instrumentation is a list": self.BASE + "instrumentation:\n  - 1\n",
            # §11 again, on the run's own record of what it executes under:
            # resuming state from a version this driver does not implement
            # is guessing at statuses, edges, and record order.
            "newer minor protocol": self.BASE.replace(
                'protocol: "0.2"', 'protocol: "0.9"'
            ),
            "other major protocol": self.BASE.replace(
                'protocol: "0.2"', 'protocol: "1.0"'
            ),
            # A bool is an int in Python and is not one in the schema; left
            # accepted, `phase: true` would resolve a `{N}` path to `True`.
            "boolean run phase": self.BASE.replace(
                "  workflow: demo\n", "  workflow: demo\n  phase: true\n"
            ),
            "boolean iterations": self.BASE.replace(
                "    status: pending\n", "    status: pending\n    iterations: true\n"
            ),
            "boolean gate phase": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    phase: true\n"
                "    transport: blocking\n    outcome: accept\n"
                '    at: "2026-08-16T09:00:00Z"\n',
            ),
        }
        for name, text in cases.items():
            run_dir = self.runs / f"bad-{abs(hash(name))}"
            run_dir.mkdir(parents=True)
            (run_dir / state.STATE_FILE).write_text(text, encoding="utf-8")
            with self.subTest(case=name):
                with self.assertRaises(state.StateError):
                    state.load(run_dir)

    def symlink(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")

    def test_open_run_refuses_a_linked_run_directory(self) -> None:
        """`status` never lists a link as a run for this reason: following
        one reads, and would later write, state outside the artifact root."""
        outside = self.base / "elsewhere"
        outside.mkdir()
        (outside / state.STATE_FILE).write_text(self.BASE, encoding="utf-8")
        self.runs.mkdir(parents=True)
        self.symlink(self.runs / "demo-run", outside)
        with self.assertRaises(state.StateError) as caught:
            state.open_run(self.runs, "demo-run")
        self.assertIn("is a link", str(caught.exception))

    def test_load_refuses_a_linked_state_file(self) -> None:
        outside = self.base / "elsewhere.yaml"
        outside.write_text(self.BASE, encoding="utf-8")
        run_dir = self.runs / "demo-run"
        run_dir.mkdir(parents=True)
        self.symlink(run_dir / state.STATE_FILE, outside)
        with self.assertRaises(state.StateError) as caught:
            state.load(run_dir)
        self.assertIn("is a link", str(caught.exception))

    def test_reads_and_writes_are_bound_to_the_run_directory(self) -> None:
        """Where the platform can bind them, the directory is opened once
        and refuses a link at that open — so a swap between the check and
        the read has nothing left to redirect."""
        if not state._BINDS_TO_DIRECTORY:  # pragma: no cover
            self.skipTest("platform has no dir_fd")
        outside = self.base / "elsewhere"
        outside.mkdir()
        (outside / state.STATE_FILE).write_text(self.BASE, encoding="utf-8")
        self.runs.mkdir(parents=True)
        self.symlink(self.runs / "demo-run", outside)
        loaded = state.RunState(
            run_id="demo-run", workflow="demo", protocol="0.2",
            steps=[state.StepRecord(id="make", status="pending")],
            gates=[], artifacts=[],
        )
        with self.assertRaises(state.StateError) as caught:
            state.load(self.runs / "demo-run")
        self.assertIn("cannot read", str(caught.exception))
        # `save` reports the refusal as what it is, the failure to open the
        # directory it was asked to write into; the command surface turns
        # that into the same exit code a state error takes.
        with self.assertRaises(OSError):
            state.save(loaded, self.runs / "demo-run")
        self.assertEqual(
            (outside / state.STATE_FILE).read_text(encoding="utf-8"), self.BASE
        )

    def test_open_run_refuses_state_that_names_another_run(self) -> None:
        """The id is the run's identity (§8.1): a document naming another
        run would be reported as that run while every path it resolves stays
        under this directory."""
        run_dir = self.runs / "other-run"
        run_dir.mkdir(parents=True)
        (run_dir / state.STATE_FILE).write_text(self.BASE, encoding="utf-8")
        with self.assertRaises(state.StateError) as caught:
            state.open_run(self.runs, "other-run")
        self.assertIn("names run 'demo-run'", str(caught.exception))

    def test_open_run_returns_the_directory_and_its_state(self) -> None:
        self.write_state(self.BASE)
        run_dir, loaded = state.open_run(self.runs, "demo-run")
        self.assertEqual(run_dir, self.runs / "demo-run")
        self.assertEqual(loaded.run_id, "demo-run")

    def test_a_timestamp_is_rfc_3339_or_it_is_not_one(self) -> None:
        """The forms the schema's format assertion accepts, and the ones a
        regex alone would let past: an hour of 24, a February 30th."""
        for value in ("2026-08-03T13:40:00Z", "2026-08-03t13:40:00z",
                      "2026-08-03T13:40:00.5+02:00", "2026-08-03T23:59:60Z"):
            with self.subTest(accepted=value):
                self.assertTrue(state._is_timestamp(value))
        for value in ("2026-08-03", "2026-08-03T13:40:00", "2026-08-03T24:00:00Z",
                      "2026-02-30T00:00:00Z", "2026-08-03T13:60:00Z", "", None, 42):
            with self.subTest(refused=value):
                self.assertFalse(state._is_timestamp(value))

    def test_state_from_an_earlier_minor_still_loads(self) -> None:
        """The refusal is for versions the driver does not implement; an
        earlier minor is readable, and where its shapes differ the load
        fails on the field it is missing rather than on its version."""
        loaded = state.load(
            self.write_state(self.BASE.replace('protocol: "0.2"', 'protocol: "0.1"'))
        )
        self.assertEqual(loaded.protocol, "0.1")

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
