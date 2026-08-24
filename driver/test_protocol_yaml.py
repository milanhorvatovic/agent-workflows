"""Unit tests for protocol_yaml.py."""

from __future__ import annotations

import unittest
from pathlib import Path

from driver.protocol_yaml import ProtocolYamlError, dumps, loads

REPO = Path(__file__).resolve().parent.parent


class LoadsTest(unittest.TestCase):
    def test_parses_a_nested_run_state_shape(self) -> None:
        text = (
            "run:\n"
            "  id: 2026-08-03-feature-slug\n"
            "  workflow: feature\n"
            '  protocol: "0.2"\n'
            "steps:\n"
            "  - id: brief-confirm\n"
            "    status: done\n"
            "  - id: plan-validate\n"
            "    status: pending\n"
            "    iterations: 2\n"
            "gates: []\n"
            "artifacts:\n"
            '  - "{run}/brief.md"\n'
        )
        self.assertEqual(
            loads(text),
            {
                "run": {
                    "id": "2026-08-03-feature-slug",
                    "workflow": "feature",
                    "protocol": "0.2",
                },
                "steps": [
                    {"id": "brief-confirm", "status": "done"},
                    {"id": "plan-validate", "status": "pending", "iterations": 2},
                ],
                "gates": [],
                "artifacts": ["{run}/brief.md"],
            },
        )

    def test_reads_the_on_key_as_a_string(self) -> None:
        """The YAML 1.1 failure this module exists to avoid: `on:` is the
        string key spec §9.1 declares, never boolean true."""
        data = loads("on:\n  PASS: next-step\n  FAIL: fix-step\n")
        self.assertEqual(data, {"on": {"PASS": "next-step", "FAIL": "fix-step"}})

    def test_resolves_core_scalars_only(self) -> None:
        data = loads(
            "a: true\nb: false\nc: null\nd: ~\ne:\nf: 42\ng: -7\nh: yes\ni: On\n"
        )
        self.assertEqual(
            data,
            {
                "a": True,
                "b": False,
                "c": None,
                "d": None,
                "e": None,
                "f": 42,
                "g": -7,
                "h": "yes",
                "i": "On",
            },
        )

    def test_strips_comments_outside_quotes_only(self) -> None:
        data = loads('a: 1 # trailing\n# full line\nb: "kept # inside"\n')
        self.assertEqual(data, {"a": 1, "b": "kept # inside"})

    def test_unescapes_double_quoted_scalars(self) -> None:
        data = loads('a: "tab\\tnewline\\nquote\\" backslash\\\\ nul\\x00 u\\u0085"\n')
        self.assertEqual(data, {"a": 'tab\tnewline\nquote" backslash\\ nul\x00 u\x85'})

    def test_empty_document_is_none(self) -> None:
        self.assertIsNone(loads("# only a comment\n\n"))

    def test_sequence_of_scalars_and_empty_flows(self) -> None:
        data = loads("a:\n  - one\n  - 2\n  - []\nb: {}\n")
        self.assertEqual(data, {"a": ["one", 2, []], "b": {}})

    def test_loads_every_valid_run_state_fixture(self) -> None:
        """The shipped starters are the canonical documents this subset must
        read; parity with the conformance suite's full YAML load is asserted
        structurally on fields the fixtures are known to carry."""
        fixtures = sorted(
            (REPO / "protocol" / "schemas" / "examples").glob("run-state.valid*.yaml")
        )
        self.assertTrue(fixtures)
        for path in fixtures:
            with self.subTest(fixture=path.name):
                data = loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                self.assertIn("id", data["run"])
                self.assertTrue(all("id" in step for step in data["steps"]))

    def test_loads_every_stage_sequence_block(self) -> None:
        import re

        block = re.compile(r"```yaml\n(.*?)```", re.DOTALL)
        for path in sorted((REPO / "workflows" / "stages").glob("*.md")):
            for found in block.finditer(path.read_text(encoding="utf-8")):
                with self.subTest(stage=path.name):
                    data = loads(found.group(1))
                    self.assertIn("metadata", data)

    def test_rejects_tabs_in_indentation(self) -> None:
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a:\n\tb: 1\n")
        self.assertIn("tab", str(caught.exception))

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\na: 2\n")
        self.assertIn("duplicate key", str(caught.exception))

    def test_rejects_anchors_aliases_and_flow(self) -> None:
        for text in ("a: &x 1\n", "a: *x\n", "a: [1, 2]\n", "a: |\n  x\n", "a: 'q'\n"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError):
                    loads(text)

    def test_rejects_unterminated_quotes_and_bad_escapes(self) -> None:
        for text in ('a: "open\n', 'a: "\\q"\n', 'a: "\\xZZ"\n', 'a: "end\\"\n'):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError):
                    loads(text)

    def test_rejects_a_plain_scalar_carrying_a_mapping_indicator(self) -> None:
        """`a: value: other` is a nested mapping on one line, which YAML
        refuses; read as text it is the misreading this module avoids."""
        for text in ("a: value: other\n", "a: value:\n", "- item: nested: deep\n"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(text)
                self.assertIn("mapping indicator", str(caught.exception))
        # Quoted, both forms are content and round-trip as themselves.
        self.assertEqual(loads('a: "value: other"\nb: "note:"\n'),
                         {"a": "value: other", "b": "note:"})

    def test_an_apostrophe_is_a_character_not_a_quote(self) -> None:
        """`don't` is a plain scalar; only a scalar that begins with a
        single quote is the form outside the subset."""
        self.assertEqual(loads("a: don't\nb: it's fine\n"), {"a": "don't", "b": "it's fine"})
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 'quoted'\n")
        self.assertIn("outside the subset", str(caught.exception))

    def test_rejects_a_surrogate_escape(self) -> None:
        """Accepted, it would load and validate and then break the next
        save: UTF-8 cannot carry a lone surrogate."""
        for text in ('a: "\\ud800"\n', 'a: "\\udfff"\n'):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(text)
                self.assertIn("surrogate", str(caught.exception))

    def test_error_carries_the_line_number(self) -> None:
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\nb: 2\nc: 'bad'\n")
        self.assertEqual(caught.exception.line_number, 3)


class DumpsTest(unittest.TestCase):
    def test_round_trips_a_run_state_shape(self) -> None:
        data = {
            "run": {"id": "2026-08-03-x", "workflow": "feature", "protocol": "0.2"},
            "steps": [
                {"id": "brief-confirm", "status": "done"},
                {"id": "plan-validate", "status": "pending", "iterations": 2,
                 "stall_flags": []},
            ],
            "gates": [
                {"gate": "intake-approval", "transport": "inbox",
                 "outcome": "accept", "at": "2026-08-03T13:40:00Z"},
            ],
            "artifacts": ["{run}/brief.md", "{run}/phase-1-plan.md"],
        }
        self.assertEqual(loads(dumps(data)), data)

    def test_quotes_what_plain_yaml_would_misread(self) -> None:
        data = {
            "a": "true",
            "b": "42",
            "c": "null",
            "d": "with: colon-space",
            "e": "trailing ",
            "f": "hash # inside",
            "g": "control\x00char",
        }
        text = dumps(data)
        self.assertEqual(loads(text), data)
        self.assertIn('a: "true"', text)
        self.assertIn('b: "42"', text)

    def test_leaves_ids_plain_and_quotes_placeholder_paths(self) -> None:
        """A leading `{` opens flow syntax, so `{run}/…` paths are quoted —
        the form the shipped fixtures use — while plain ids stay plain."""
        text = dumps({"id": "2026-08-03-x", "artifact": "{run}/brief.md"})
        self.assertEqual(text, 'id: 2026-08-03-x\nartifact: "{run}/brief.md"\n')

    def test_round_trips_a_string_that_ends_in_a_colon(self) -> None:
        """Left plain, `- note:` is a mapping to the reader — a manifest
        path or a stall flag would load as something else entirely."""
        for data in (["note:"], {"a": ["note:"]}, {"a": "note:"}):
            with self.subTest(data=data):
                self.assertEqual(loads(dumps(data)), data)

    def test_round_trips_every_character_the_reader_splits_on(self) -> None:
        """`str.splitlines` breaks on more than \\n: an unescaped one would
        leave a document the reader sees as two lines."""
        for name, character in {
            "vertical tab": "\v",
            "form feed": "\f",
            "file separator": "\x1c",
            "group separator": "\x1d",
            "record separator": "\x1e",
            "next line": "\x85",
            "line separator": "\u2028",
            "paragraph separator": "\u2029",
        }.items():
            value = f"before{character}after"
            with self.subTest(character=name):
                text = dumps({"a": value})
                self.assertNotIn(character, text)
                self.assertEqual(loads(text), {"a": value})

    def test_round_trips_every_valid_run_state_fixture(self) -> None:
        fixtures = sorted(
            (REPO / "protocol" / "schemas" / "examples").glob("run-state.valid*.yaml")
        )
        for path in fixtures:
            with self.subTest(fixture=path.name):
                data = loads(path.read_text(encoding="utf-8"))
                self.assertEqual(loads(dumps(data)), data)

    def test_rejects_values_outside_the_subset(self) -> None:
        for value in ({"a": 1.5}, {"a": {1: "int key"}}, {"bad key": 1}, {"a": b"x"}):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    dumps(value)

    def test_empty_collections_dump_as_flow_empties(self) -> None:
        self.assertEqual(dumps({"a": [], "b": {}}), "a: []\nb: {}\n")


if __name__ == "__main__":
    unittest.main()
