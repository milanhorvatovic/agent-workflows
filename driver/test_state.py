"""Unit tests for state.py."""

from __future__ import annotations

import os
import signal
import stat
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
        (self.base / "workflows" / "stages" / "intake.md").write_text(
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

    def test_a_save_that_fails_after_publishing_leaves_the_id_usable(self) -> None:
        """The retry guarantee has to cover every way the write can fail,
        and syncing the directory is one that happens after the state file
        is already there — cleanup that only removes an empty directory
        leaves that one behind, and the id it names is taken for good by a
        call that reported failure."""
        import errno
        import unittest.mock

        real = os.fsync

        def fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            return real(descriptor)

        with unittest.mock.patch.object(os, "fsync", fsync):
            with self.assertRaises(OSError):
                state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertFalse((self.runs / "2026-08-19-x").exists())
        run_dir, created = state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertTrue((run_dir / state.STATE_FILE).is_file())

    def test_a_sync_that_fails_after_the_bootstrap_leaves_the_id_usable(self) -> None:
        """The syncs that persist the entries naming the run run after the
        state file is written and outside the bootstrap that cleans up
        after itself. A failure there is a creation that failed, so the
        directory it made has to go with it — or the id is taken for good
        by a call that reported failure."""
        import errno
        import unittest.mock

        real_descriptor, real_directory = state._sync_descriptor, state._sync_directory
        runs_id = None

        def sync_descriptor(descriptor):
            # The run's own directory is synced by the save inside the
            # bootstrap; this fails only the one that names the run.
            if runs_id is not None:
                info = os.fstat(descriptor)
                if (info.st_ino, info.st_dev) == runs_id:
                    raise OSError(errno.EIO, os.strerror(errno.EIO))
            return real_descriptor(descriptor)

        def sync_directory(path):
            if Path(path) != self.runs / "2026-08-19-x":
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            return real_directory(path)

        self.runs.mkdir(parents=True)
        info = os.stat(self.runs)
        runs_id = (info.st_ino, info.st_dev)
        with unittest.mock.patch.multiple(
            state, _sync_descriptor=sync_descriptor, _sync_directory=sync_directory
        ):
            with self.assertRaises(OSError):
                state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertFalse((self.runs / "2026-08-19-x").exists())
        run_dir, _ = state.create_run(self.runs, "2026-08-19-x", self.workflow, "0.2")
        self.assertTrue((run_dir / state.STATE_FILE).is_file())

    def test_a_rollback_never_reaches_outside_the_runs_root(self) -> None:
        """The rollback runs while the failure that caused it is still
        unwinding, and a name it walks through can be swapped in that
        window. Naming the state file through the run directory left the
        containment to the path: bound to the directory itself, a link put
        in its place is refused at the open rather than followed to
        whatever it points at."""
        outside = self.base / "elsewhere"
        outside.mkdir()
        victim = outside / state.STATE_FILE
        victim.write_text("someone else's state\n", encoding="utf-8")
        self.runs.mkdir(parents=True)
        try:
            (self.runs / "2026-08-19-x").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {error}")
        with state._runs_directory(self.runs) as runs:
            state._remove_run(self.runs / "2026-08-19-x", runs)
        self.assertTrue(victim.is_file())

    def test_a_value_the_subset_cannot_write_is_reported_as_state(self) -> None:
        """Every defect this module meets leaves it as a StateError, which
        is what carries one to an exit code rather than a traceback. A
        value the YAML subset does not carry reached the writer and left it
        as whatever the writer raised."""
        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        created.instrumentation = {"duration": 1.5}
        created.has_instrumentation = True
        with self.assertRaises(state.StateError) as caught:
            state.save(created, run_dir)
        self.assertIn("subset", str(caught.exception))

    def test_creating_refuses_a_protocol_it_cannot_load_back(self) -> None:
        """The version is written into the document and `load` holds every
        document to it, so an unchecked one leaves a run that exists and
        cannot be resumed."""
        for protocol in ("0.9", "1.0", "0.2.0", "", "zero"):
            with self.subTest(protocol=protocol):
                with self.assertRaises(state.StateError) as caught:
                    state.create_run(self.runs, f"run-{abs(hash(protocol))}", self.workflow, protocol)
                self.assertIn("this driver implements", str(caught.exception))

    def test_a_trailing_newline_does_not_pass_a_pattern(self) -> None:
        """`$` matches before a final newline, so every check written with
        it accepted one — a version, a timestamp, an id carrying a line
        break that the schema refuses and the next save would write out."""
        self.assertFalse(state._is_timestamp("2026-08-03T13:40:00Z\n"))
        with self.assertRaises(state.StateError) as caught:
            state.create_run(self.runs, "trailing", self.workflow, "0.2\n")
        self.assertIn("this driver implements", str(caught.exception))

    def test_a_run_id_carrying_a_surrogate_is_refused(self) -> None:
        """The schema's pattern describes documents, and a lone surrogate is
        a `str` Python holds that UTF-8 cannot encode — it clears the
        pattern and raises inside `mkdir` or the write, which is the
        traceback these guards exist to prevent."""
        with self.assertRaises(state.StateError) as caught:
            state.create_run(self.runs, "\ud800", self.workflow, "0.2")
        self.assertIn("not a run id", str(caught.exception))
        with self.assertRaises(state.StateError):
            state.open_run(self.runs, "run\udfffid")

    def test_a_state_file_that_is_not_a_regular_file_is_refused(self) -> None:
        """`O_NOFOLLOW` says the name is not a link and nothing about what
        kind of file it is: a FIFO there blocks the open until something
        writes to the other end, so a resume hangs instead of reporting."""
        run_dir = self.runs / "demo-run"
        run_dir.mkdir(parents=True)
        try:
            os.mkfifo(run_dir / state.STATE_FILE)
        except (AttributeError, OSError) as error:  # pragma: no cover
            self.skipTest(f"FIFOs unavailable: {error}")
        # The handler is process-wide, so it is put back: left installed,
        # every later test inherits an alarm that fails them.
        previous = signal.signal(signal.SIGALRM, self._alarm)
        signal.alarm(5)
        try:
            with self.assertRaises(state.StateError) as caught:
                state.load(run_dir)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertIn("not a regular file", str(caught.exception))

    @staticmethod
    def _alarm(*_: object) -> None:  # pragma: no cover
        raise AssertionError("load blocked on the FIFO instead of refusing it")

    def test_opening_refuses_an_id_that_is_not_a_plain_directory_name(self) -> None:
        """Containment cannot rest on the command surface being the only
        caller: the id joins under the runs directory either way."""
        for run_id in ("../other", "a/b", "..", "C:run"):
            with self.subTest(run_id=run_id):
                with self.assertRaises(state.StateError) as caught:
                    state.open_run(self.runs, run_id)
                self.assertIn("not a run id", str(caught.exception))

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
        (self.base / "workflows" / "stages" / "intake.md").write_text(
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
        (self.base / "workflows" / "stages" / "intake.md").write_text(phased, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        self.state.phase = 2
        state.start_step(self.state, self.workflow, "make")
        state.complete_step(self.state, workflow, "make")
        self.assertEqual(self.state.artifacts, ["{run}/phase-2-out.md"])

    def test_a_shell_style_token_is_text_and_not_the_phase(self) -> None:
        """`${N}` is shell text, which is why the declaration reader accepts
        it and reports no unknown placeholder. A raw substitution resolves
        the `{N}` inside it all the same, so the manifest would name
        `phase-$1.md` for a step that wrote `phase-${N}.md` — and the same
        raw rule in the manifest check would agree with itself about it."""
        literal = STAGE.replace(
            'artifact: "{run}/out.md"', 'artifact: "{run}/phase-${N}-out.md"'
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(literal, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        self.state.phase = 2
        state.start_step(self.state, self.workflow, "make")
        state.complete_step(self.state, workflow, "make")
        self.assertEqual(self.state.artifacts, ["{run}/phase-${N}-out.md"])
        state.check_manifest(self.state, workflow)

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

    def complete(self, state_obj, workflow, step_id: str) -> None:
        """A verdict routes from a `done` step (§9.1), so the source goes
        through the transitions that make it one."""
        state.start_step(state_obj, workflow, step_id)
        state.complete_step(state_obj, workflow, step_id)

    def test_a_verdict_does_not_route_while_a_step_is_running(self) -> None:
        """The counterpart to the single-active guard on starting one. A
        route rewrites records for the resume to find, and §8.5 returns to
        the active record ahead of any of them — so a verdict applied while
        another step runs mutates the list and changes nothing the resume
        reads, which is a transition that half happened."""
        self.complete(self.state, self.workflow, "make")
        self.state.steps.append(state.StepRecord(id="later", status="active"))
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, self.workflow, "make", "PASS")
        self.assertIn("later", str(caught.exception))
        self.assertEqual(self.state.record("check").status, "skipped")

    def test_a_route_to_overlay_skipped_work_resolves_past_it(self) -> None:
        """`workflows/overlays.md` resolves an edge targeting skipped
        content to the next non-skipped point, and §10 has a route re-enter
        a member a condition skipped. Both are `skipped`, and what tells
        them apart is the declaration: a conditional member is one the
        sequence says so about, an imported derivation is one the manifest
        names, and a member that is neither was left out by the class —
        work a route may not resurrect."""
        three = STAGE.replace(
            "        - step: make\n",
            "        - step: make\n        - step: spare\n        - step: last\n",
        ).replace("        PASS: check\n", "        PASS: spare\n").replace(
            "## Gates",
            "### spare (planner)\n\nProse.\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: planner\n      output:\n'
            '        artifact: "{run}/spare.md"\n```\n\n'
            "### last (reviewer)\n\nProse.\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: reviewer\n      output:\n'
            '        artifact: "{run}/last.md"\n```\n\n## Gates',
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(three, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        _, created = state.create_run(self.runs, "overlay", workflow, "0.2")
        created.record("spare").status = "skipped"  # the class left it out
        self.complete(created, workflow, "make")
        self.assertEqual(
            state.route_verdict(created, workflow, "make", "PASS"), "last"
        )
        self.assertEqual(created.record("spare").status, "skipped")
        self.assertEqual(created.record("last").status, "pending")

    def test_route_follows_the_declared_edge(self) -> None:
        self.complete(self.state, self.workflow, "make")
        target = state.route_verdict(self.state, self.workflow, "make", "PASS")
        self.assertEqual(target, "check")
        # The skipped conditional gate was routed to, so it re-enters pending.
        self.assertEqual(self.state.record("check").status, "pending")

    def build_dependents(self) -> object:
        """A stage where one later step reads `make`'s output and another
        does not — which is the difference §7 turns on."""
        stage = STAGE.replace(
            "        - step: make\n",
            "        - step: make\n        - step: reads\n        - step: apart\n",
        ).replace(
            "## Gates",
            "### reads (validator)\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: validator\n'
            '      inputs:\n        - artifact: "{run}/out.md"\n'
            '      output:\n        artifact: "{run}/verdict.md"\n'
            "      on:\n        PASS: check\n        FAIL: make\n```\n\n"

            "### apart (planner)\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: planner\n'
            '      output:\n        artifact: "{run}/apart.md"\n```\n\n## Gates',
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(
            stage, encoding="utf-8"
        )
        return load_workflow(self.base, "demo")

    def test_a_re_entry_invalidates_what_its_output_fed(self) -> None:
        """§7: a step run again "invalidates what its output fed: the
        validator that must re-check it, the gate that must decide again",
        and what that is "MUST be read from the stage rather than assumed" —
        "resetting a fixed shape would both miss a dependent and run a step
        the overlay excludes"."""
        workflow = self.build_dependents()
        _, created = state.create_run(self.runs, "dependents", workflow, "0.2")
        for step_id in ("make", "reads", "apart"):
            state.start_step(created, workflow, step_id)
            state.complete_step(created, workflow, step_id)
        created.record("check").status = "done"
        state.route_verdict(created, workflow, "reads", "FAIL")
        self.assertEqual(
            {record.id: record.status for record in created.steps},
            {
                "make": "pending",   # the destination, re-entered
                "reads": "pending",  # declares make's output among its inputs
                "apart": "done",     # ran after it and read none of it
                "check": "pending",  # the gate that must decide again
            },
        )

    def test_a_re_entry_never_invalidates_what_precedes_it(self) -> None:
        """§10 bounds what §7 derives: "its destination MUST precede every
        record it invalidates". The shipped planning stage is where the two
        rules meet — `plan-revise` both reads and rewrites the plan, so a
        dependency walk with no bound reaches `plan-create`, which produced
        it first and sits ahead of it in the record order, and a resume
        would pick that over the destination the edge named."""
        workflow = load_workflow(REPO, "feature")
        records = [
            state.StepRecord(id=member.id, status="done")
            for stage in workflow.stages
            for member in stage.members
        ]
        run = state.RunState(
            run_id="planning-run", workflow="feature", protocol="0.2",
            steps=records, gates=[], artifacts=[],
        )
        invalidated = state._invalidated_by(run, workflow, "plan-revise")
        order = [record.id for record in records]
        self.assertNotIn("plan-create", invalidated)
        for step_id in invalidated:
            self.assertGreater(order.index(step_id), order.index("plan-revise"))
        # What the revision does feed is still invalidated.
        self.assertIn("plan-validate", invalidated)
        self.assertIn("plan-approval", invalidated)

    def test_a_re_entry_leaves_a_skipped_record_skipped(self) -> None:
        """What a class excluded, or a condition has not fired, is not work
        the revision invalidated."""
        self.complete(self.state, self.workflow, "make")
        self.assertEqual(self.state.record("check").status, "skipped")
        state.route_verdict(self.state, self.workflow, "make", "FAIL")
        self.assertEqual(self.state.record("make").status, "pending")
        self.assertEqual(self.state.record("check").status, "skipped")

    def test_a_verdict_routes_only_where_the_manifest_says_it_produced(self) -> None:
        """`done` is a status; §8.2 makes the manifest the record of what was
        produced, and the conformance suite holds every shipped document to
        exactly that. `complete_step` writes both together, so only state
        loaded from elsewhere can disagree — and routing from it would
        re-enter the destination on an output no document says exists."""
        self.complete(self.state, self.workflow, "make")
        self.state.artifacts.clear()
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, self.workflow, "make", "PASS")
        self.assertIn("not in the manifest", str(caught.exception))
        self.assertEqual(self.state.record("check").status, "skipped")

    def test_a_verdict_routes_only_from_a_step_that_produced_its_output(self) -> None:
        """§9.1: the verdict comes from the validation of the step's output,
        so a record whose output the run does not hold has nothing to route
        — and routing anyway re-enters the destination on work that never
        happened, past the checks starting and completing both make. This
        run imports nothing, so its `skipped` is a member the class or a
        condition left out, which produced nothing at all."""
        for status in ("pending", "active", "skipped", "blocked"):
            with self.subTest(status=status):
                self.state.record("make").status = status
                with self.assertRaises(state.StateError) as caught:
                    state.route_verdict(self.state, self.workflow, "make", "PASS")
                self.assertIn("the run holds", str(caught.exception))
                self.assertEqual(self.state.record("check").status, "skipped")

    def test_route_without_an_edge_escalates(self) -> None:
        self.complete(self.state, self.workflow, "make")
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(self.state, self.workflow, "make", "PASS_WITH_CONDITIONS")
        self.assertIn("escalate", str(caught.exception))

    def test_route_to_a_stage_id_resolves_to_its_first_runnable_step(self) -> None:
        stage_edge = STAGE.replace("        PASS: check\n", "        PASS: intake\n")
        (self.base / "workflows" / "stages" / "intake.md").write_text(
            stage_edge, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        self.complete(self.state, workflow, "make")
        target = state.route_verdict(self.state, workflow, "make", "PASS")
        self.assertEqual(target, "make")

    def test_a_stage_target_passes_over_a_gate_to_reach_the_step(self) -> None:
        """§9.1 makes a stage id stand for the stage's first step; a gate
        ahead of it in the sequence is a member, not that step."""
        gate_first = STAGE.replace(
            "        - step: make\n        - gate: check\n          conditional: true\n",
            "        - gate: check\n        - step: make\n",
        ).replace("        PASS: check\n", "        PASS: intake\n")
        (self.base / "workflows" / "stages" / "intake.md").write_text(
            gate_first, encoding="utf-8"
        )
        workflow = load_workflow(self.base, "demo")
        _, created = state.create_run(self.runs, "gate-first", workflow, "0.2")
        self.assertEqual([s.id for s in created.steps], ["check", "make"])
        # The gate is ahead of the step in the sequence, so the run reaches
        # it first and its decision stands before the step runs at all —
        # which is the state a route out of that step is resolved from.
        created.record("check").status = "done"
        self.complete(created, workflow, "make")
        target = state.route_verdict(created, workflow, "make", "PASS")
        self.assertEqual(target, "make")

    def test_a_stage_target_with_no_runnable_step_escalates(self) -> None:
        stage_edge = STAGE.replace("        PASS: check\n", "        PASS: other\n")
        (self.base / "workflows" / "stages" / "intake.md").write_text(
            stage_edge, encoding="utf-8"
        )
        second = (
            STAGE.replace("name: intake", "name: other")
            .replace("- step: make", "- step: build")
            .replace("- gate: check", "- gate: sign")
            .replace("### make (analyst)", "### build (analyst)")
            .replace("PASS: check", "PASS: sign")
            .replace("FAIL: make", "FAIL: build")
            .replace("**check**", "**sign**")
        )
        (self.base / "workflows" / "stages" / "other.md").write_text(
            second, encoding="utf-8"
        )
        (self.base / "workflows" / "pair.md").write_text(
            "---\nname: pair\ndescription: Two stages.\n---\n\n"
            "1. [stages/intake.md](stages/intake.md)\n2. [stages/other.md](stages/other.md)\n",
            encoding="utf-8",
        )
        workflow = load_workflow(self.base, "pair")
        _, created = state.create_run(self.runs, "pair-run", workflow, "0.2")
        # Creation bootstraps the entry stage alone (§10), so the targeted
        # stage's step has no record to resolve to yet.
        self.complete(created, workflow, "make")
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(created, workflow, "make", "PASS")
        self.assertIn("no runnable step", str(caught.exception))


class DurabilityTest(StateTestCase):
    def test_the_data_reaches_the_device_before_the_rename_publishes_it(self) -> None:
        """A rename is atomic and says nothing about durability: after a
        power loss it can be on the device while the data it published is
        not, which is the half-written state temp-and-replace exists to make
        impossible. The order is the guarantee — data, rename, then the
        directory entry naming it."""
        import unittest.mock

        order: list[str] = []
        real_fsync, real_replace, real_rename = os.fsync, os.replace, os.rename
        seen: set[int] = set()

        def fsync(descriptor):
            order.append("fsync-directory" if descriptor in seen else "fsync-file")
            return real_fsync(descriptor)

        def replace(source, target, **kwargs):
            order.append("publish")
            return real_replace(source, target, **kwargs)

        def rename(source, target, **kwargs):
            order.append("publish")
            seen.add(kwargs.get("dst_dir_fd"))
            return real_rename(source, target, **kwargs)

        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        order.clear()
        with unittest.mock.patch.multiple(
            os, fsync=fsync, replace=replace, rename=rename
        ):
            state.save(created, run_dir)
        self.assertEqual(order[:2], ["fsync-file", "publish"])
        self.assertIn("fsync", order[-1])
        self.assertEqual(state.load(run_dir), created)

    def test_a_directory_sync_that_fails_is_not_a_save_that_succeeded(self) -> None:
        """An `EIO` from `fsync` says the write did not reach the device,
        which is the whole of what this ordering promises — swallowed, the
        save returns as though it had. A refusal that means the operation
        does not apply to a directory here is the other thing entirely, and
        is what the platforms without it report."""
        import errno
        import unittest.mock

        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        real = os.fsync

        def failing(code):
            def fsync(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise OSError(code, os.strerror(code))
                return real(descriptor)

            return fsync

        with unittest.mock.patch.object(os, "fsync", failing(errno.EIO)):
            with self.assertRaises(OSError) as caught:
                state.save(created, run_dir)
        self.assertEqual(caught.exception.errno, errno.EIO)
        # Unsupported is not failed: a filesystem that has no sync for a
        # directory has not lost anything.
        with unittest.mock.patch.object(os, "fsync", failing(errno.EINVAL)):
            state.save(created, run_dir)
        self.assertEqual(state.load(run_dir), created)

    def test_a_directory_that_cannot_be_opened_is_not_a_sync_declined(self) -> None:
        """Where a platform syncs directories, failing to open one means no
        sync was attempted at all — an `EIO` or an exhausted descriptor
        table is the write not being made durable, reported as made. The
        platforms that have no such operation are decided by the platform,
        not read out of an error code."""
        import errno
        import unittest.mock

        if not state._SYNCS_DIRECTORIES:  # pragma: no cover
            self.skipTest("this platform does not sync directories")
        run_dir, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        real = os.open

        def failing(path, flags, *args, **kwargs):
            # The directory open `_sync_directory` makes, and no other:
            # every write here opens files, and the bound path opens the
            # run directory to hold it.
            if flags & os.O_DIRECTORY and str(path) == str(run_dir):
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            return real(path, flags, *args, **kwargs)

        # Unbound, so the sync is the one that opens the directory by path.
        with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", False):
            with unittest.mock.patch.object(os, "open", failing):
                with self.assertRaises(OSError) as caught:
                    state.save(created, run_dir)
        self.assertEqual(caught.exception.errno, errno.EIO)

    def test_creation_persists_the_entry_that_names_the_run(self) -> None:
        """The state file's own durability says nothing about the directory
        holding it: a parent that never recorded the new entry loses the
        whole run, which `create_run` has already reported as made."""
        import unittest.mock

        real = os.fsync
        synced: set[tuple[int, int]] = set()

        def fsync(descriptor):
            # Identified while it is open: what a descriptor names is not
            # readable once the call that owned it has returned.
            try:
                info = os.fstat(descriptor)
                synced.add((info.st_ino, info.st_dev))
            except OSError:
                pass
            return real(descriptor)

        with unittest.mock.patch.object(os, "fsync", fsync):
            run_dir, _ = state.create_run(
                self.runs, "2026-08-17-x", self.workflow, "0.2"
            )
        runs = os.stat(self.runs)
        self.assertIn((runs.st_ino, runs.st_dev), synced)
        # And every ancestor the creation made: syncing `runs` persists the
        # run inside it, while the entry naming `runs` lives in its own
        # parent — unsynced, the first run of a fresh artifact root goes
        # with it.
        for ancestor in (self.runs.parent, self.runs.parent.parent):
            info = os.stat(ancestor)
            self.assertIn(
                (info.st_ino, info.st_dev), synced, f"{ancestor} was never synced"
            )
        self.assertTrue((run_dir / state.STATE_FILE).is_file())


class StartPositionTest(StateTestCase):
    def two_steps(self) -> object:
        """A stage whose sequence runs one step and then another, so the
        second is `pending` while the first still is."""
        two = STAGE.replace(
            "        - step: make\n", "        - step: make\n        - step: also\n"
        ).replace(
            "## Gates",
            "### also (planner)\n\nProse.\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: planner\n      output:\n'
            '        artifact: "{run}/also.md"\n```\n\n## Gates',
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(two, encoding="utf-8")
        return load_workflow(self.base, "demo")

    def test_a_step_starts_only_where_the_run_stands(self) -> None:
        """§8.5 resolves one position, and starting anything else walks past
        the work between: the record goes `active`, and the active-first
        rule then preserves that skip on every resume after it. The two
        checks that ran before this one report their own cases — a second
        active record, and a status a start would erase."""
        workflow = self.two_steps()
        _, created = state.create_run(self.runs, "2026-08-17-x", workflow, "0.2")
        with self.assertRaises(state.StateError) as caught:
            state.start_step(created, workflow, "also")
        self.assertIn("make", str(caught.exception))
        self.assertEqual(created.record("also").status, "pending")
        # The position itself starts, and once it is done the next one is
        # the position in its turn.
        state.start_step(created, workflow, "make")
        state.complete_step(created, workflow, "make")
        self.assertEqual(state.start_step(created, workflow, "also").status, "active")


class ImportInvalidationTest(StateTestCase):
    def build(self) -> object:
        """A stage where two later steps read what the first produced: one
        whose output the run imported, one the class skipped."""
        def reader(step_id: str, role: str, output: str) -> str:
            return (
                f"### {step_id} ({role})\n\nProse.\n\n```yaml\nmetadata:\n"
                '  workflow:\n    protocol: "0.2"\n    step:\n'
                f"      role: {role}\n      inputs:\n"
                '        - artifact: "{run}/out.md"\n          required: true\n'
                f'      output:\n        artifact: "{output}"\n```\n\n'
            )

        two = STAGE.replace(
            "        - step: make\n",
            "        - step: make\n        - step: derive\n        - step: other\n",
        ).replace(
            "## Gates",
            reader("derive", "planner", "{run}/derived.md")
            + reader("other", "reviewer", "{run}/other.md")
            + "## Gates",
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(two, encoding="utf-8")
        return load_workflow(self.base, "demo")

    def test_a_derivation_that_was_imported_re_enters_with_its_input(self) -> None:
        """§8.6: the skip holds only while the derivation stays imported. A
        step skipped because its output was imported has produced nothing
        this run can re-run — but once the artifact it was derived from is
        re-entered, what it holds was computed from the old input, and a
        resume that walked past it would carry that forward.

        The other `skipped` is a step the class left out: it produced
        nothing and derives from nothing, so the walk passes it by. Which
        of the two a record is comes from the manifest of imports rather
        than from the status they share.
        """
        workflow = self.build()
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            risk="R1",
            risk_rationale="small",
            steps=[
                state.StepRecord(id=step, status="skipped")
                for step in ("make", "derive", "other", "check")
            ],
            gates=[],
            artifacts=["{run}/out.md", "{run}/derived.md"],
            imports=[
                state.ImportRecord(
                    artifact=artifact,
                    from_run="2026-08-01-source",
                    at="2026-08-16T09:00:00Z",
                )
                for artifact in ("{run}/out.md", "{run}/derived.md")
            ],
        )
        invalidated = state._invalidated_by(state_obj, workflow, "make")
        self.assertIn("derive", invalidated)
        self.assertNotIn("other", invalidated)

    def test_a_verdict_routes_from_the_producer_an_import_stood_in_for(self) -> None:
        """§8.6 populates a producer `skipped` where its output was
        imported, and §9.1 puts the edges on that same producer while the
        verdict comes from the validation of its output. Import the plan
        and not the validation and the validator runs on the copy — so the
        verdict is real, the artifact is in the manifest, and the only
        thing missing is the run of a step that had nothing to produce.
        Refused, an imported plan stops at its first verdict."""
        workflow = self.build()
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            risk="R1",
            risk_rationale="small",
            steps=[
                state.StepRecord(id="make", status="skipped"),
                state.StepRecord(id="derive", status="done"),
                state.StepRecord(id="other", status="skipped"),
                state.StepRecord(id="check", status="skipped"),
            ],
            gates=[],
            artifacts=["{run}/out.md", "{run}/derived.md"],
            imports=[
                state.ImportRecord(
                    artifact="{run}/out.md",
                    from_run="2026-08-01-source",
                    at="2026-08-16T09:00:00Z",
                )
            ],
        )
        self.assertEqual(
            state.route_verdict(state_obj, workflow, "make", "PASS"), "check"
        )
        # The class-skipped reader produced nothing and routes nothing.
        with self.assertRaises(state.StateError) as caught:
            state.route_verdict(state_obj, workflow, "other", "PASS")
        self.assertIn("other", str(caught.exception))

    def test_the_write_returns_that_derivation_to_pending(self) -> None:
        """Identifying it is half the transition: left `skipped`, §8.5
        walks past it exactly as it would have without the walk."""
        workflow = self.build()
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            risk="R1",
            risk_rationale="small",
            steps=[
                state.StepRecord(id="make", status="done"),
                state.StepRecord(id="derive", status="skipped"),
                state.StepRecord(id="other", status="skipped"),
                state.StepRecord(id="check", status="skipped"),
            ],
            gates=[],
            artifacts=["{run}/out.md", "{run}/derived.md"],
            imports=[
                state.ImportRecord(
                    artifact="{run}/derived.md",
                    from_run="2026-08-01-source",
                    at="2026-08-16T09:00:00Z",
                )
            ],
        )
        state.route_verdict(state_obj, workflow, "make", "FAIL")
        self.assertEqual(state_obj.record("derive").status, "pending")
        # The class-skipped reader is not a derivation and stays as it is.
        self.assertEqual(state_obj.record("other").status, "skipped")

    def test_a_phased_output_is_matched_against_the_path_imported(self) -> None:
        """An import records the path it copied — `{run}/phase-1-out.md` —
        and a declaration names the family it belongs to. Compared as text
        the two never meet, so every phased derivation read as never
        imported and no re-entry reached one."""
        phased = STAGE.replace(
            'artifact: "{run}/out.md"', 'artifact: "{run}/phase-{N}-out.md"'
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(phased, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            steps=[
                state.StepRecord(id="make", status="skipped"),
                state.StepRecord(id="check", status="skipped"),
            ],
            gates=[],
            artifacts=["{run}/phase-1-out.md"],
            imports=[
                state.ImportRecord(
                    artifact="{run}/phase-1-out.md",
                    from_run="2026-08-01-source",
                    at="2026-08-16T09:00:00Z",
                )
            ],
        )
        self.assertEqual(state._import_skipped(state_obj, workflow), {"make"})

    def test_an_import_from_an_earlier_phase_is_not_this_phase_s(self) -> None:
        """A family is not a path: the artifact a phase produces is the one
        `{N}` resolves to in it, and an import of the phase before names a
        file this phase has yet to write. Read as the family, a member
        skipped for any other reason joined the walk and was reset to
        `pending` — the run then executing it ahead of whatever its own
        skip was waiting for."""
        phased = STAGE.replace(
            'artifact: "{run}/out.md"', 'artifact: "{run}/phase-{N}-out.md"'
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(phased, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")

        def at(phase: int, imported: str) -> set[str]:
            return state._import_skipped(
                state.RunState(
                    run_id="2026-08-17-x",
                    workflow="demo",
                    protocol="0.2",
                    phase=phase,
                    steps=[
                        state.StepRecord(id="make", status="skipped"),
                        state.StepRecord(id="check", status="skipped"),
                    ],
                    gates=[],
                    artifacts=[imported],
                    imports=[
                        state.ImportRecord(
                            artifact=imported,
                            from_run="2026-08-01-source",
                            at="2026-08-16T09:00:00Z",
                        )
                    ],
                ),
                workflow,
            )

        self.assertEqual(at(2, "{run}/phase-1-out.md"), set())
        self.assertEqual(at(2, "{run}/phase-2-out.md"), {"make"})


class CrossStageInvalidationTest(StateTestCase):
    def build(self) -> object:
        """Two stages, the second reading what the first produced and its
        own gate standing after the step that reads it."""
        second = (
            STAGE.replace("name: intake", "name: second")
            .replace("- step: make", "- step: build")
            .replace("- gate: check\n          conditional: true", "- gate: approve")
            .replace("### make (analyst)", "### build (implementer)")
            .replace("role: analyst", "role: implementer")
            .replace('artifact: "{run}/in.md"', 'artifact: "{run}/out.md"')
            .replace("required: false", "required: true")
            .replace('artifact: "{run}/out.md"\n        template', 'artifact: "{run}/built.md"\n        template')
            .replace("PASS: check", "PASS: approve")
            .replace("FAIL: make", "FAIL: build")
            .replace("- **check** — a gate.", "- **approve** — a gate.")
        )
        (self.base / "workflows" / "stages" / "second.md").write_text(
            second, encoding="utf-8"
        )
        (self.base / "workflows" / "demo.md").write_text(
            WORKFLOW + "2. [stages/second.md](stages/second.md)\n", encoding="utf-8"
        )
        return load_workflow(self.base, "demo")

    def test_a_re_entry_reaches_the_gates_of_every_stage_it_touches(self) -> None:
        """The dependency walk crosses stages on purpose — a dependent's
        output is as stale as what it was computed from — and the gates it
        leaves behind have to follow it. A step re-run in a later stage
        under a gate that stayed `done` is an approval standing over work
        the approver never saw, and resume walks straight past it."""
        workflow = self.build()
        order, _ = workflow.sequence()
        self.assertEqual(order, ["make", "check", "build", "approve"])
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            risk="R1",
            risk_rationale="small",
            steps=[state.StepRecord(id=member, status="done") for member in order],
            gates=[
                state.GateRecord(
                    gate=gate,
                    transport="blocking",
                    outcome="accept",
                    at="2026-08-16T09:00:00Z",
                )
                for gate in ("check", "approve")
            ],
            artifacts=["{run}/out.md", "{run}/built.md"],
        )
        state.route_verdict(state_obj, workflow, "make", "FAIL")
        self.assertEqual(state_obj.record("build").status, "pending")
        self.assertEqual(state_obj.record("approve").status, "pending")


class RejectedRunTest(StateTestCase):
    def test_a_rejected_run_has_nothing_left_to_walk_into(self) -> None:
        """§7: where what ends is the run, "every record still `pending` or
        `blocked` becomes `skipped` with the outcome, every one but the
        deciding gate's own". Without that write a resume looks for the
        first record neither done nor skipped and finds work the rejection
        ended — so a document carrying one without the other is a run this
        driver would carry on executing after it was stopped."""
        def rejected(rest: str) -> state.RunState:
            return state.RunState(
                run_id="2026-08-17-x",
                workflow="demo",
                protocol="0.2",
                # A run rejected at its intake gate never accepted a class,
                # so there is none to carry.
                steps=[
                    state.StepRecord(id="make", status=rest),
                    state.StepRecord(id="check", status="done"),
                ],
                gates=[
                    state.GateRecord(
                        gate="check",
                        transport="blocking",
                        outcome="reject",
                        at="2026-08-16T09:00:00Z",
                    )
                ],
                artifacts=[],
            )

        # A phase list states which phases must complete before which
        # others, and §7 makes ending only the phase sound "only where
        # nothing the list places after the rejected phase depends on it,
        # and an executor that cannot establish that MUST end the run".
        # This one reads a phase number, not the list — so the run ends.
        phased = rejected("pending")
        phased.phase = 2
        with self.assertRaises(state.StateError) as caught:
            state.check_gates(phased, self.workflow)
        self.assertIn("reject", str(caught.exception))
        # §7 writes the deciding gate `done`, and nothing after a reject
        # re-enters it — the run is over. A decision on file over a record
        # that never closed is a rejection the resume can return to and
        # ask again.
        for status in ("pending", "blocked", "skipped"):
            with self.subTest(gate=status):
                undecided = rejected("skipped")
                undecided.record("check").status = status
                with self.assertRaises(state.StateError) as caught:
                    state.check_gates(undecided, self.workflow)
                self.assertIn("reject", str(caught.exception))
        for rest in ("pending", "blocked", "active"):
            with self.subTest(status=rest):
                with self.assertRaises(state.StateError) as caught:
                    state.check_gates(rejected(rest), self.workflow)
                self.assertIn("reject", str(caught.exception))
        state.check_gates(rejected("skipped"), self.workflow)


class AcceptedClassTest(StateTestCase):
    def test_a_skipped_gate_never_accepted_the_class_it_carries(self) -> None:
        """Accepting writes the gate `done`, and a re-entry can only make
        it `pending` or `blocked` — the run coming back to decide again.
        `skipped` is neither, so a class beside one is a class no decision
        of this run produced, and every check keyed on `run.risk` reads the
        post-intake shape as established."""
        def carrying(status: str) -> state.RunState:
            return state.RunState(
                run_id="2026-08-17-x",
                workflow="demo",
                protocol="0.2",
                risk="R1",
                risk_rationale="small",
                steps=[
                    state.StepRecord(id="make", status="pending"),
                    state.StepRecord(id="check", status=status),
                ],
                gates=[
                    state.GateRecord(
                        gate="check",
                        transport="blocking",
                        outcome="accept",
                        at="2026-08-16T09:00:00Z",
                    )
                ],
                artifacts=[],
            )

        with self.assertRaises(state.StateError) as caught:
            state.check_gates(carrying("skipped"), self.workflow)
        self.assertIn("check", str(caught.exception))
        # What a re-entry leaves is still read: the gate decides again, and
        # the class it accepted stands until it does. A gate that is still
        # `done` is a different shape — the work before it in its stage is
        # behind it too — so that case is built where it belongs.
        for status in ("pending", "blocked"):
            with self.subTest(status=status):
                state.check_gates(carrying(status), self.workflow)
        decided = carrying("done")
        decided.record("make").status = "done"
        state.check_gates(decided, self.workflow)

    def test_a_gate_decides_after_the_work_before_it(self) -> None:
        """A gate is a member of its stage's sequence and decides where it
        stands: `done` with earlier work still to run is a decision taken
        about something that had not happened. No transition writes it —
        the gate is reached after that work, and a route back into the work
        returns the gate to `pending` with it — so a document carrying it
        would have `resume` run the earlier step under a class the same
        document says was accepted afterward."""
        for status in ("pending", "active", "blocked"):
            with self.subTest(status=status):
                state_obj = state.RunState(
                    run_id="2026-08-17-x",
                    workflow="demo",
                    protocol="0.2",
                    risk="R1",
                    risk_rationale="small",
                    steps=[
                        state.StepRecord(id="make", status=status),
                        state.StepRecord(id="check", status="done"),
                    ],
                    gates=[
                        state.GateRecord(
                            gate="check",
                            transport="blocking",
                            outcome="accept",
                            at="2026-08-16T09:00:00Z",
                        )
                    ],
                    artifacts=[],
                )
                with self.assertRaises(state.StateError) as caught:
                    state.check_gates(state_obj, self.workflow)
                self.assertIn("make", str(caught.exception))


class TerminalAcceptTest(StateTestCase):
    def build(self) -> object:
        """Two stages, and a step after the entry gate: the unfinished
        record has to sit where no decided gate stands before it in its own
        stage, or the rule about that answers first and this one is never
        reached."""
        entry = STAGE.replace(
            "        - gate: check\n          conditional: true\n",
            "        - gate: check\n          conditional: true\n        - step: tail\n",
        ).replace(
            "## Gates",
            "### tail (reviewer)\n\nProse.\n\n```yaml\nmetadata:\n  workflow:\n"
            '    protocol: "0.2"\n    step:\n      role: reviewer\n      output:\n'
            '        artifact: "{run}/tail.md"\n```\n\n## Gates',
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(
            entry, encoding="utf-8"
        )
        second = (
            STAGE.replace("name: intake", "name: second")
            .replace("- step: make", "- step: build")
            .replace("- gate: check\n          conditional: true", "- gate: approve")
            .replace("### make (analyst)", "### build (implementer)")
            .replace("role: analyst", "role: implementer")
            .replace('artifact: "{run}/out.md"', 'artifact: "{run}/built.md"')
            .replace("PASS: check", "PASS: approve")
            .replace("FAIL: make", "FAIL: build")
            .replace("- **check** — a gate.", "- **approve** — a gate.")
        )
        (self.base / "workflows" / "stages" / "second.md").write_text(
            second, encoding="utf-8"
        )
        (self.base / "workflows" / "demo.md").write_text(
            WORKFLOW + "2. [stages/second.md](stages/second.md)\n", encoding="utf-8"
        )
        return load_workflow(self.base, "demo")

    def test_an_accept_at_the_last_gate_ends_the_run_too(self) -> None:
        """§7 names two ways a run ends — "a `reject` in a workflow with no
        phases, an `accept` at the last gate" — and gives both the same
        write: every record still `pending` or `blocked` becomes `skipped`.
        The reject half was checked and this one was not, so a state with
        the final approval on file and work still waiting in an earlier
        stage resumed into work that approval had already shipped past."""
        workflow = self.build()

        def approved(rest: str) -> state.RunState:
            return state.RunState(
                run_id="2026-08-17-x",
                workflow="demo",
                protocol="0.2",
                risk="R1",
                risk_rationale="small",
                steps=[
                    state.StepRecord(id="make", status="done"),
                    state.StepRecord(id="check", status="done"),
                    state.StepRecord(id="tail", status=rest),
                    state.StepRecord(id="build", status="done"),
                    state.StepRecord(id="approve", status="done"),
                ],
                gates=[
                    state.GateRecord(
                        gate=gate,
                        transport="blocking",
                        outcome="accept",
                        at="2026-08-16T09:00:00Z",
                    )
                    for gate in ("check", "approve")
                ],
                artifacts=["{run}/out.md", "{run}/built.md"],
            )

        for rest in ("pending", "blocked"):
            with self.subTest(status=rest):
                with self.assertRaises(state.StateError) as caught:
                    state.check_gates(approved(rest), workflow)
                self.assertIn("tail", str(caught.exception))
        for rest in ("done", "skipped"):
            with self.subTest(status=rest):
                state.check_gates(approved(rest), workflow)


class ManifestTest(StateTestCase):
    def test_the_manifest_holds_only_what_the_composition_produces(self) -> None:
        """§8.2 makes the manifest the record of what the run produced or
        imported, and a path no composed step declares is neither — content
        nothing wrote, which a later input or phase-set resolution would
        then read as an artifact the run holds."""
        _, created = state.create_run(self.runs, "2026-08-17-x", self.workflow, "0.2")
        created.artifacts.append("{run}/forged.md")
        with self.assertRaises(state.StateError) as caught:
            state.check_manifest(created, self.workflow)
        self.assertIn("forged.md", str(caught.exception))

    def test_every_phase_of_a_family_belongs_to_it(self) -> None:
        """A run that has passed through phases holds each phase's own
        artifact, and every one of them is the output its declaration
        names — the family, not the phase now executing."""
        phased = STAGE.replace(
            'artifact: "{run}/out.md"', 'artifact: "{run}/phase-{N}-out.md"'
        )
        (self.base / "workflows" / "stages" / "intake.md").write_text(phased, encoding="utf-8")
        workflow = load_workflow(self.base, "demo")
        _, created = state.create_run(self.runs, "phased", workflow, "0.2")
        created.phase = 2
        created.artifacts.extend(["{run}/phase-1-out.md", "{run}/phase-2-out.md"])
        state.check_manifest(created, workflow)


class RoutedStateTest(StateTestCase):
    def test_what_routing_writes_passes_the_checks_that_read_it(self) -> None:
        """A re-entry returns a decided gate to `pending` so it decides
        again, and appends nothing to `gates` — which is append-only, so the
        accept it made before is still its latest entry. That pairing is
        what this module writes, and every check that reads state has to
        accept it: one that asked for `done` beside a standing accept
        refused the run its own transition had just produced."""
        state_obj = state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            risk="R1",
            risk_rationale="small",
            steps=[
                state.StepRecord(id="make", status="done"),
                state.StepRecord(id="check", status="done"),
            ],
            gates=[
                state.GateRecord(
                    gate="check",
                    transport="blocking",
                    outcome="accept",
                    at="2026-08-16T09:00:00Z",
                )
            ],
            artifacts=["{run}/out.md"],
        )
        state.check_gates(state_obj, self.workflow)
        state.route_verdict(state_obj, self.workflow, "make", "FAIL")
        self.assertEqual(state_obj.record("check").status, "pending")
        self.assertEqual(state_obj.gates[-1].outcome, "accept")
        state.check_gates(state_obj, self.workflow)
        state.check_records(state_obj, self.workflow)


class GatePhaseTest(StateTestCase):
    """A phased gate's latest decision, in a run that carries a phase.

    Two stages, because the rule needs a phased gate that is not the entry
    gate: intake's own decision sets the class, so the gate whose latest
    entry is still a revise has to be a later one.
    """

    def build(self) -> object:
        phased = (
            STAGE.replace("name: intake", "name: phased")
            .replace("- step: make", "- step: build")
            .replace("- gate: check\n          conditional: true", "- gate: approve")
            .replace("### make (analyst)", "### build (implementer)")
            .replace("role: analyst", "role: implementer")
            .replace('artifact: "{run}/out.md"', 'artifact: "{run}/phase-{N}-out.md"')
            .replace("PASS: check", "PASS: approve")
            .replace("FAIL: make", "FAIL: build")
            .replace("- **check** — a gate.", "- **approve** — a gate.")
        )
        (self.base / "workflows" / "stages" / "phased.md").write_text(
            phased, encoding="utf-8"
        )
        (self.base / "workflows" / "demo.md").write_text(
            WORKFLOW + "2. [stages/phased.md](stages/phased.md)\n", encoding="utf-8"
        )
        return load_workflow(self.base, "demo")

    def accepted(self, workflow, phase: int | None) -> state.RunState:
        return state.RunState(
            run_id="2026-08-17-x",
            workflow="demo",
            protocol="0.2",
            phase=2,
            risk="R1",
            risk_rationale="small",
            steps=[
                state.StepRecord(id="make", status="done"),
                state.StepRecord(id="check", status="done"),
                state.StepRecord(id="build", status="pending"),
                state.StepRecord(id="approve", status="pending"),
            ],
            gates=[
                state.GateRecord(
                    gate="check",
                    transport="blocking",
                    outcome="accept",
                    at="2026-08-16T09:00:00Z",
                ),
                state.GateRecord(
                    gate="approve",
                    transport="blocking",
                    outcome="revise",
                    at="2026-08-16T10:00:00Z",
                    phase=phase,
                ),
            ],
            artifacts=["{run}/out.md"],
        )

    def test_a_standing_revise_names_the_phase_it_was_taken_in(self) -> None:
        """§10 has a decision taken while the run carries a phase name it,
        and a revise is the decision that did not stand — the gate decides
        again, in this phase. The accept that set `run.phase` is appended
        after any revise taken before the run had phases, so a revise that
        is still the latest entry was taken under the phase the run is in."""
        workflow = self.build()
        for phase in (None, 1):
            with self.subTest(phase=phase):
                with self.assertRaises(state.StateError) as caught:
                    state.check_gates(self.accepted(workflow, phase), workflow)
                self.assertIn("approve", str(caught.exception))
        state.check_gates(self.accepted(workflow, 2), workflow)


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
            # §8.6 and §10 bound the list, and the suite holds the shipped
            # documents to both: one record per artifact, one source run.
            "one artifact twice": (
                'artifacts:\n  - "{run}/brief.md"\n'
                'imports:\n  - artifact: "{run}/brief.md"\n'
                '    from: earlier-run\n    at: "2026-08-16T09:00:00Z"\n'
                '  - artifact: "{run}/brief.md"\n'
                '    from: earlier-run\n    at: "2026-08-16T10:00:00Z"\n'
            ),
            "two source runs": (
                'artifacts:\n  - "{run}/brief.md"\n  - "{run}/plan.md"\n'
                'imports:\n  - artifact: "{run}/brief.md"\n'
                '    from: earlier-run\n    at: "2026-08-16T09:00:00Z"\n'
                '  - artifact: "{run}/plan.md"\n'
                '    from: other-run\n    at: "2026-08-16T10:00:00Z"\n'
            ),
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
            # A field the schema admits no null for, read as absence, is
            # dropped by the next save — malformed state laundered into
            # well-formed state by a round trip through the driver.
            "run phase is null": self.BASE.replace(
                "  workflow: demo\n", "  workflow: demo\n  phase: null\n"
            ),
            "risk is null": self.BASE.replace(
                "  workflow: demo\n",
                "  workflow: demo\n  risk: null\n  risk_rationale: null\n",
            ),
            "rationale is null": self.BASE.replace(
                "  workflow: demo\n",
                "  workflow: demo\n  risk: R2\n  risk_rationale: null\n",
            ),
            "iterations is null": self.BASE.replace(
                "    status: pending\n", "    status: pending\n    iterations: null\n"
            ),
            "stall_flags is null": self.BASE.replace(
                "    status: pending\n", "    status: pending\n    stall_flags: null\n"
            ),
            "gate phase is null": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    phase: null\n"
                "    transport: blocking\n    outcome: accept\n"
                '    at: "2026-08-16T09:00:00Z"\n',
            ),
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
            # `$` matches before a final newline, so a version or timestamp
            # carrying one passed every check written with it.
            # An id reaches a terminal: `resume` prints the position it
            # resolves, and the reader decodes escapes before this check.
            "step id splits a line": self.BASE.replace(
                "  - id: make\n", '  - id: "make\\nfake: 1"\n'
            ),
            "gate id carries an escape": self.BASE.replace(
                "gates: []\n",
                'gates:\n  - gate: "sign\\u001b[2K"\n    transport: blocking\n'
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z"\n',
            ),
            "protocol with a trailing newline": self.BASE.replace(
                'protocol: "0.2"', 'protocol: "0.2\\n"'
            ),
            "gate timestamp with a trailing newline": self.BASE.replace(
                "gates: []\n",
                "gates:\n  - gate: intake-approval\n    transport: blocking\n"
                '    outcome: accept\n    at: "2026-08-16T09:00:00Z\\n"\n',
            ),
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

    def test_neither_creating_nor_resuming_follows_a_linked_runs_directory(self) -> None:
        """The runs segment is derived by the driver, not configured, so a
        link in its place redirects every run the artifact root should hold
        — and binding the run alone does not notice, its child being an
        ordinary directory inside the link's target."""
        outside = self.base / "elsewhere"
        (outside / "demo-run").mkdir(parents=True)
        (outside / "demo-run" / state.STATE_FILE).write_text(self.BASE, encoding="utf-8")
        self.runs.parent.mkdir(parents=True, exist_ok=True)
        self.symlink(self.runs, outside)
        with self.assertRaises(state.StateError) as caught:
            state.open_run(self.runs, "demo-run")
        self.assertIn("not the runs directory", str(caught.exception))
        with self.assertRaises(state.StateError) as caught:
            state.create_run(self.runs, "2026-08-24-x", self.workflow, "0.2")
        self.assertIn("not the runs directory", str(caught.exception))
        self.assertFalse((outside / "2026-08-24-x").exists())

    def test_creating_refuses_a_dangling_runs_link_before_it_creates(self) -> None:
        """The refusal comes before the mkdir that would otherwise follow
        the link and put the first run wherever it points."""
        self.runs.parent.mkdir(parents=True, exist_ok=True)
        self.symlink(self.runs, self.base / "nowhere")
        with self.assertRaises(state.StateError) as caught:
            state.create_run(self.runs, "2026-08-24-x", self.workflow, "0.2")
        self.assertIn("not the runs directory", str(caught.exception))
        self.assertFalse((self.base / "nowhere").exists())

    def test_a_linked_run_directory_is_refused_without_dir_fd_too(self) -> None:
        """Where the platform cannot bind an operation to a descriptor, the
        link check is the whole of the containment — and `save` reaches the
        directory without any caller having looked."""
        import unittest.mock

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
        with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", False):
            for name, call in {
                "load": lambda: state.load(self.runs / "demo-run"),
                "save": lambda: state.save(loaded, self.runs / "demo-run"),
            }.items():
                with self.subTest(operation=name):
                    with self.assertRaises(state.StateError) as caught:
                        call()
                    self.assertIn("is a link", str(caught.exception))
        self.assertEqual(
            (outside / state.STATE_FILE).read_text(encoding="utf-8"), self.BASE
        )

    def test_a_save_after_resume_still_binds_the_runs_directory(self) -> None:
        """`open_run` closes its descriptor when it returns, so the next
        save holds a run directory and no parent — and `O_NOFOLLOW` on the
        run cannot see past a `runs` that was swapped in the meantime, the
        child it reaches being an ordinary directory inside the target."""
        import shutil

        run_dir, _ = state.create_run(self.runs, "demo-run", self.workflow, "0.2")
        _, loaded = state.open_run(self.runs, "demo-run")
        outside = self.base / "elsewhere"
        (outside / "demo-run").mkdir(parents=True)
        shutil.rmtree(self.runs)
        self.symlink(self.runs, outside)
        with self.assertRaises(state.StateError) as caught:
            state.save(loaded, run_dir)
        self.assertIn("not the runs directory", str(caught.exception))
        self.assertFalse((outside / "demo-run" / state.STATE_FILE).exists())

    def test_the_fallback_path_refuses_a_linked_parent_too(self) -> None:
        """Without binding, the checks are the containment — and checking
        the run alone sees nothing wrong when `runs` is the link, its child
        inside the target being an ordinary directory."""
        import shutil
        import unittest.mock

        run_dir, _ = state.create_run(self.runs, "demo-run", self.workflow, "0.2")
        _, loaded = state.open_run(self.runs, "demo-run")
        outside = self.base / "elsewhere"
        (outside / "demo-run").mkdir(parents=True)
        shutil.rmtree(self.runs)
        self.symlink(self.runs, outside)
        with unittest.mock.patch.object(state, "_BINDS_TO_DIRECTORY", False):
            with self.assertRaises(state.StateError) as caught:
                state.save(loaded, run_dir)
            self.assertIn("not the runs directory", str(caught.exception))
            with self.assertRaises(state.StateError):
                state.load(run_dir)
        self.assertFalse((outside / "demo-run" / state.STATE_FILE).exists())

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
                      "2026-08-03T13:40:00.5+02:00"):
            with self.subTest(accepted=value):
                self.assertTrue(state._is_timestamp(value))
        for value in ("2026-08-03T13:40:00+02:00", "2026-08-03T13:40:00-05:30"):
            with self.subTest(accepted=value):
                self.assertTrue(state._is_timestamp(value))
        # Every `:60` is refused, boundary or not: the format checker behind
        # the schema rejects them, and state the driver writes has to pass it.
        for value in ("2026-08-03T13:40:60Z", "2026-12-31T23:59:60Z",
                      "2026-08-03", "2026-08-03T13:40:00", "2026-08-03T24:00:00Z",
                      "2026-02-30T00:00:00Z", "2026-08-03T13:60:00Z",
                      "2026-08-03T13:40:00+99:99", "2026-08-03T13:40:00+24:00",
                      "2026-08-03T13:40:00+02:60", "", None, 42):
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
