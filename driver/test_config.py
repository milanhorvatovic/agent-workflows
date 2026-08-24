"""Unit tests for config.py.

Run from the repo root: python3 -m unittest discover -s driver -t .
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from driver import config as config_module
from driver.config import ConfigError, load_config

VALID = {
    "artifacts_dir": ".",
    "backends": {
        "claude": {"command": ["claude", "-p"]},
        "codex": {"command": ["codex", "exec"]},
    },
    "roles": {
        "analyst": {"backend": "claude", "model": "claude-sonnet-5"},
        "planner": {"backend": "claude", "model": "claude-opus-5"},
        "implementer": {"backend": "claude", "model": "claude-sonnet-5"},
        "reviewer": {"backend": "codex"},
        "validator": {"backend": "claude", "model": "claude-opus-5"},
        "arbiter": {"backend": "claude", "model": "claude-opus-5"},
    },
}


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def write(self, values: dict | str) -> Path:
        path = self.base / "driver.json"
        text = values if isinstance(values, str) else json.dumps(values)
        path.write_text(text, encoding="utf-8")
        return path

    def load(self, values: dict | str) -> config_module.Config:
        return load_config(self.write(values))

    def assert_rejected(self, values: dict | str, fragment: str) -> None:
        with self.assertRaises(ConfigError) as caught:
            self.load(values)
        self.assertIn(fragment, str(caught.exception))

    def variant(self, **overrides: object) -> dict:
        values = json.loads(json.dumps(VALID))
        values.update(overrides)
        return values

    def test_parses_a_valid_config(self) -> None:
        loaded = self.load(VALID)
        self.assertEqual(loaded.backends["claude"].command, ("claude", "-p"))
        self.assertEqual(loaded.roles["planner"].backend, "claude")
        self.assertEqual(loaded.roles["planner"].model, "claude-opus-5")
        self.assertEqual(set(loaded.roles), set(config_module.ROLES))

    def test_model_is_none_when_absent(self) -> None:
        loaded = self.load(VALID)
        self.assertIsNone(loaded.roles["reviewer"].model)

    def test_relative_artifacts_dir_anchors_at_the_config_directory(self) -> None:
        loaded = self.load(self.variant(artifacts_dir="artifacts"))
        self.assertEqual(loaded.artifacts_dir, self.base.resolve() / "artifacts")

    def test_absolute_artifacts_dir_is_kept(self) -> None:
        absolute = str(self.base / "elsewhere")
        loaded = self.load(self.variant(artifacts_dir=absolute))
        self.assertEqual(loaded.artifacts_dir, Path(absolute))

    def test_artifacts_dir_defaults_to_the_config_directory(self) -> None:
        values = self.variant()
        del values["artifacts_dir"]
        loaded = self.load(values)
        self.assertEqual(loaded.artifacts_dir, self.base.resolve())

    def test_tilde_artifacts_dir_expands_to_home(self) -> None:
        loaded = self.load(self.variant(artifacts_dir="~/awf-artifacts"))
        self.assertEqual(loaded.artifacts_dir, Path.home() / "awf-artifacts")

    def test_framework_dir_defaults_to_the_config_directory(self) -> None:
        loaded = self.load(VALID)
        self.assertEqual(loaded.framework_dir, self.base.resolve())

    def test_relative_framework_dir_anchors_at_the_config_directory(self) -> None:
        """The same rules as artifacts_dir, by the same code — one anchoring
        rule for both configured roots."""
        loaded = self.load(self.variant(framework_dir="agent-workflows"))
        self.assertEqual(loaded.framework_dir, self.base.resolve() / "agent-workflows")

    def test_partially_anchored_windows_framework_dir_is_rejected(self) -> None:
        with self.assertRaises(config_module.ConfigError) as caught:
            self.load(self.variant(framework_dir="D:framework"))
        self.assertIn("framework_dir", str(caught.exception))

    def test_runs_dir_derives_the_spec_runs_segment(self) -> None:
        loaded = self.load(self.variant(artifacts_dir="artifacts"))
        self.assertEqual(loaded.runs_dir, self.base.resolve() / "artifacts" / "runs")

    def test_missing_file_is_rejected(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            load_config(self.base / "absent.json")
        self.assertIn("cannot read config", str(caught.exception))

    def test_undecodable_config_is_rejected(self) -> None:
        path = self.base / "driver.json"
        path.write_bytes(b"\xff\xfe{")
        with self.assertRaises(ConfigError) as caught:
            load_config(path)
        self.assertIn("cannot read config", str(caught.exception))

    def test_invalid_json_is_rejected(self) -> None:
        self.assert_rejected("{not json", "invalid JSON")

    def test_non_object_top_level_is_rejected(self) -> None:
        self.assert_rejected(json.dumps(["a list"]), "top level must be an object")

    def test_unknown_top_level_key_is_rejected(self) -> None:
        self.assert_rejected(self.variant(runs_dir="runs"), "unknown keys: runs_dir")

    def test_empty_artifacts_dir_is_rejected(self) -> None:
        self.assert_rejected(
            self.variant(artifacts_dir="  "), "artifacts_dir must be a non-empty string"
        )

    def test_control_characters_in_a_configured_path_are_rejected(self) -> None:
        """NUL because no filesystem call accepts one, and the rest because
        both paths are printed — `run` reports the directory it created, so
        a newline there splits the line reporting it."""
        for key in ("artifacts_dir", "framework_dir"):
            for value in ("a\x00b", "a\nb", "a\x1b[2Kb", "a\x85b", "a\u2028b"):
                with self.subTest(key=key, value=value):
                    self.assert_rejected(
                        self.variant(**{key: value}),
                        f"{key} must not contain control characters",
                    )

    def test_a_surrogate_in_a_configured_path_is_rejected(self) -> None:
        """JSON decodes `\\ud800` into a lone surrogate, which UTF-8 cannot
        encode — so the path reaches `mkdir` or the line that prints it and
        raises there, turning a config defect into a traceback."""
        for key in ("artifacts_dir", "framework_dir"):
            with self.subTest(key=key):
                text = json.dumps(self.variant(**{key: "artifacts"})).replace(
                    '"artifacts"', '"art\\ud800ifacts"'
                )
                self.assert_rejected(text, f"{key} must not contain surrogates")

    def test_partially_anchored_windows_artifacts_dir_is_rejected(self) -> None:
        for value in ("D:artifacts", "\\artifacts"):
            with self.subTest(value=value):
                self.assert_rejected(
                    self.variant(artifacts_dir=value),
                    "artifacts_dir must be fully absolute or fully relative",
                )

    def test_missing_backends_is_rejected(self) -> None:
        values = self.variant()
        del values["backends"]
        self.assert_rejected(values, "backends must be a non-empty object")

    def test_empty_backends_is_rejected(self) -> None:
        self.assert_rejected(self.variant(backends={}), "backends must be a non-empty object")

    def test_empty_backend_name_is_rejected(self) -> None:
        values = self.variant()
        values["backends"][" "] = {"command": ["true"]}
        self.assert_rejected(values, "backend names must be non-empty")

    def test_non_object_backend_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"] = ["claude", "-p"]
        self.assert_rejected(values, "backend 'claude' must be an object")

    def test_unknown_backend_key_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"]["timeout"] = 60
        self.assert_rejected(values, "backend 'claude' has unknown keys: timeout")

    def test_missing_backend_command_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"] = {}
        self.assert_rejected(values, "backend 'claude' command must be a non-empty list")

    def test_empty_backend_command_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"]["command"] = []
        self.assert_rejected(values, "backend 'claude' command must be a non-empty list")

    def test_blank_command_part_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"]["command"] = ["claude", " "]
        self.assert_rejected(values, "backend 'claude' command must be a non-empty list")

    def test_non_string_command_part_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"]["command"] = ["claude", 1]
        self.assert_rejected(values, "backend 'claude' command must be a non-empty list")

    def test_nul_in_command_part_is_rejected(self) -> None:
        values = self.variant()
        values["backends"]["claude"]["command"] = ["claude", "-p\x00"]
        self.assert_rejected(values, "backend 'claude' command must not contain NUL")

    def test_missing_roles_is_rejected(self) -> None:
        values = self.variant()
        del values["roles"]
        self.assert_rejected(values, "roles must be an object")

    def test_unknown_role_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["scribe"] = {"backend": "claude"}
        self.assert_rejected(values, "unknown roles: scribe")

    def test_missing_roles_are_listed(self) -> None:
        values = self.variant()
        del values["roles"]["reviewer"]
        del values["roles"]["validator"]
        self.assert_rejected(values, "roles missing: reviewer, validator")

    def test_non_object_role_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["analyst"] = "claude"
        self.assert_rejected(values, "role 'analyst' must be an object")

    def test_unknown_role_key_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["analyst"]["temperature"] = 0
        self.assert_rejected(values, "role 'analyst' has unknown keys: temperature")

    def test_missing_role_backend_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["analyst"] = {"model": "claude-sonnet-5"}
        self.assert_rejected(values, "role 'analyst' backend must be a non-empty string")

    def test_undefined_backend_reference_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["analyst"]["backend"] = "gemini"
        self.assert_rejected(values, "role 'analyst' references undefined backend 'gemini'")

    def test_blank_role_model_is_rejected(self) -> None:
        values = self.variant()
        values["roles"]["analyst"]["model"] = " "
        self.assert_rejected(values, "role 'analyst' model must be a non-empty string")

    def test_example_config_is_valid(self) -> None:
        example = Path(__file__).resolve().parent / "config.example.json"
        loaded = load_config(example)
        self.assertEqual(set(loaded.roles), set(config_module.ROLES))


if __name__ == "__main__":
    unittest.main()
