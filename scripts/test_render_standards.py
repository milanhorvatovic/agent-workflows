"""Unit tests for render_standards.py.

Run from the repo root: python3 -m unittest discover -s scripts
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import render_standards

CONFIG = {
    "PROJECT_NAME": "Sample",
    "TECH_STACK": "Python",
    "ARCHITECTURE_TYPE": "modular monolith",
}


class RenderStandardsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "standards").mkdir()
        self.out = self.root / "rendered"
        self.write(
            "standards/coding.md",
            "# Coding Standards - {{PROJECT_NAME}}\n\n"
            "> Tech Stack: {{TECH_STACK}}\n\n"
            "Follow the idiomatic style for {{TECH_STACK}}.\n"
            "Single braces pass through: `/users/{id}` and `{ \"data\": 1 }`.\n",
        )
        self.write(
            "standards/architecture.md",
            "# Architecture Standards - {{PROJECT_NAME}}\n\n"
            "Pattern: {{ARCHITECTURE_TYPE}}.\n",
        )
        self.write("standards/README.md", "# standards/\n\nNot a source.\n{{NOT_CHECKED}}\n")

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.write_text(text, encoding="utf-8")
        return path

    def config_file(self, values: dict) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return path

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = render_standards.main([*argv, "--root", str(self.root)])
            except SystemExit as error:
                code = error.code if isinstance(error.code, int) else 1
                if isinstance(error.code, str):
                    stderr.write(error.code)
        return code, stdout.getvalue(), stderr.getvalue()

    # --- rendering ---

    def test_render_substitutes_every_placeholder(self) -> None:
        code, out, _ = self.run_main(
            "--config", str(self.config_file(CONFIG)), "--out", str(self.out)
        )
        self.assertEqual(code, 0)
        coding = (self.out / "coding.md").read_text(encoding="utf-8")
        self.assertIn("# Coding Standards - Sample", coding)
        self.assertIn("Follow the idiomatic style for Python.", coding)
        self.assertNotIn("{{", coding)
        architecture = (self.out / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("Pattern: modular monolith.", architecture)
        self.assertIn("2 file(s) rendered", out)

    def test_single_braces_pass_through(self) -> None:
        self.run_main("--config", str(self.config_file(CONFIG)), "--out", str(self.out))
        coding = (self.out / "coding.md").read_text(encoding="utf-8")
        self.assertIn("`/users/{id}`", coding)
        self.assertIn('{ "data": 1 }', coding)

    def test_readme_is_not_a_source(self) -> None:
        code, _, _ = self.run_main(
            "--config", str(self.config_file(CONFIG)), "--out", str(self.out)
        )
        self.assertEqual(code, 0)
        self.assertFalse((self.out / "README.md").exists())

    def test_render_is_idempotent(self) -> None:
        args = ("--config", str(self.config_file(CONFIG)), "--out", str(self.out))
        self.run_main(*args)
        first = (self.out / "coding.md").read_text(encoding="utf-8")
        code, _, _ = self.run_main(*args)
        self.assertEqual(code, 0)
        self.assertEqual(first, (self.out / "coding.md").read_text(encoding="utf-8"))

    def test_only_selects_subset(self) -> None:
        code, _, _ = self.run_main(
            "--config", str(self.config_file(CONFIG)),
            "--out", str(self.out),
            "--only", "architecture",
        )
        self.assertEqual(code, 0)
        self.assertTrue((self.out / "architecture.md").exists())
        self.assertFalse((self.out / "coding.md").exists())

    def test_only_rejects_unknown_name(self) -> None:
        code, _, err = self.run_main(
            "--config", str(self.config_file(CONFIG)),
            "--out", str(self.out),
            "--only", "nonexistent",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("unknown standard(s): nonexistent", err)
        self.assertIn("available:", err)

    # --- config validation ---

    def test_missing_config_value_is_named(self) -> None:
        code, _, err = self.run_main(
            "--config", str(self.config_file({"PROJECT_NAME": "Sample"})),
            "--out", str(self.out),
        )
        self.assertNotEqual(code, 0)
        self.assertIn("missing value(s) for: ARCHITECTURE_TYPE, TECH_STACK", err)

    def test_unknown_config_key_fails(self) -> None:
        code, _, err = self.run_main(
            "--config", str(self.config_file({**CONFIG, "TYPO_KEY": "x"})),
            "--out", str(self.out),
        )
        self.assertNotEqual(code, 0)
        self.assertIn('unknown placeholder "TYPO_KEY"', err)

    def test_empty_config_value_fails(self) -> None:
        code, _, err = self.run_main(
            "--config", str(self.config_file({**CONFIG, "TECH_STACK": "  "})),
            "--out", str(self.out),
        )
        self.assertNotEqual(code, 0)
        self.assertIn('"TECH_STACK" must be a non-empty string', err)

    def test_invalid_json_fails(self) -> None:
        path = self.write("config.json", "{not json")
        code, _, err = self.run_main("--config", str(path), "--out", str(self.out))
        self.assertNotEqual(code, 0)
        self.assertIn("invalid JSON", err)

    def test_non_object_config_fails(self) -> None:
        path = self.write("config.json", '["a"]')
        code, _, err = self.run_main("--config", str(path), "--out", str(self.out))
        self.assertNotEqual(code, 0)
        self.assertIn("must be a JSON object", err)

    # --- integrity checking ---

    def test_check_passes_on_clean_tree(self) -> None:
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("2 source(s) clean", out)

    def test_check_flags_unknown_placeholder(self) -> None:
        self.write("standards/coding.md", "Uses {{UNREGISTERED_TOKEN}}.\n")
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn('unknown placeholder "{{UNREGISTERED_TOKEN}}"', err)
        self.assertIn("registered:", err)

    def test_check_flags_malformed_syntax(self) -> None:
        self.write(
            "standards/coding.md",
            "Line one is fine.\nUnclosed {{TECH_STACK} here.\nLower {{tech}} here.\n",
        )
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("coding.md:2: malformed", err)
        self.assertIn("coding.md:3: malformed", err)

    def test_check_reports_every_file(self) -> None:
        self.write("standards/coding.md", "{{BAD_ONE}}\n")
        self.write("standards/architecture.md", "{{BAD_TWO}}\n")
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("BAD_ONE", err)
        self.assertIn("BAD_TWO", err)
        self.assertIn("2 placeholder problem(s)", err)

    def test_render_refuses_broken_sources(self) -> None:
        self.write("standards/coding.md", "{{UNREGISTERED_TOKEN}}\n")
        code, _, err = self.run_main(
            "--config", str(self.config_file(CONFIG)), "--out", str(self.out)
        )
        self.assertNotEqual(code, 0)
        self.assertIn("not rendering", err)
        self.assertFalse(self.out.exists())

    # --- argument handling and edge cases ---

    def test_check_rejects_render_flags(self) -> None:
        code, _, err = self.run_main("--check", "--out", str(self.out))
        self.assertNotEqual(code, 0)
        self.assertIn("--check takes no", err)

    def test_render_requires_config_and_out(self) -> None:
        code, _, err = self.run_main("--out", str(self.out))
        self.assertNotEqual(code, 0)
        self.assertIn("rendering needs --config and --out", err)

    def test_empty_standards_dir_fails(self) -> None:
        for path in (self.root / "standards").glob("*.md"):
            path.unlink()
        code, _, err = self.run_main("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("no sources match", err)

    def test_missing_standards_dir_fails(self) -> None:
        root = self.root / "elsewhere"
        root.mkdir()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                render_standards.main(["--check", "--root", str(root)])
        self.assertIn("not a directory", str(caught.exception.code))


if __name__ == "__main__":
    unittest.main()
