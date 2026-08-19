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
        (stages / "demo.md").write_text(STAGE, encoding="utf-8")

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
