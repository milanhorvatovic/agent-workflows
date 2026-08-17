"""Unit tests for cli.py.

Run from the repo root: python3 -m unittest discover -s driver -t .
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from driver import cli
from driver.test_config import VALID


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

    def test_run_fails_loudly_until_the_state_machine_lands(self) -> None:
        code, out, err = self.invoke("run", "--config", str(self.config_path))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("run is not implemented yet", err)

    def test_resume_fails_loudly_until_the_state_machine_lands(self) -> None:
        code, _, err = self.invoke(
            "resume", "2026-08-12-bugfix-one", "--config", str(self.config_path)
        )
        self.assertEqual(code, 1)
        self.assertIn("resume is not implemented yet", err)

    def test_resume_without_a_run_id_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["resume", "--config", str(self.config_path)])
        self.assertEqual(caught.exception.code, 2)

    def test_resume_rejects_run_ids_that_are_not_plain_directory_names(self) -> None:
        for run_id in ("../other-run", "/tmp/run", ".", "..", "a/b", "a\\b", "C:run", "  "):
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
        (self.base / "runs").mkdir()
        entry = unittest.mock.Mock()
        entry.name = "2026-08-13-feature-one"
        entry.is_dir.side_effect = PermissionError("permission denied")
        scandir_result = unittest.mock.MagicMock()
        scandir_result.__enter__.return_value = iter([entry])
        with unittest.mock.patch("driver.cli.os.scandir", return_value=scandir_result):
            code, out, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("cannot read", err)

    def test_config_defect_names_the_file_and_exits_2(self) -> None:
        self.config_path.write_text("{not json", encoding="utf-8")
        code, _, err = self.invoke("status", "--config", str(self.config_path))
        self.assertEqual(code, 2)
        self.assertIn(str(self.config_path), err)
        self.assertIn("invalid JSON", err)

    def test_run_with_a_broken_config_fails_on_the_config(self) -> None:
        self.config_path.write_text("{}", encoding="utf-8")
        code, _, err = self.invoke("run", "--config", str(self.config_path))
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
