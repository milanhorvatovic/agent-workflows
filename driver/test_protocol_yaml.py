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
            '  protocol: "0.3"\n'
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
                    "protocol": "0.3",
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

    def test_resolves_every_core_spelling(self) -> None:
        """Core gives each kind more than one spelling, and a document the
        driver did not write may use any of them."""
        self.assertEqual(
            loads("a: True\nb: TRUE\nc: False\nd: NULL\ne: Null\nf: ~\ng: +1\nh: -0\n"),
            {"a": True, "b": True, "c": False, "d": None, "e": None, "f": None,
             "g": 1, "h": 0},
        )

    def test_rejects_core_kinds_the_subset_does_not_carry(self) -> None:
        """Returned as text, a float or a hex integer is a value this module
        reads as one type and every other reader as another."""
        # A decimal with a leading zero is the form readers disagree about:
        # `010` is ten under YAML 1.2 and eight under 1.1, and `08` is a
        # number to one and a string to the other. Resolving it picks a side.
        for token in ("0x10", "0o17", "0.2", "1e3", ".5", "-.inf", ".nan",
                      "007", "010", "08", "-0777"):
            with self.subTest(token=token):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(f"a: {token}\n")
                self.assertIn("outside the subset", str(caught.exception))

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

    def test_trims_only_what_yaml_separates_with(self) -> None:
        """A non-breaking or ideographic space is content, not separation:
        trimmed as whitespace, a value comes back shorter than it was
        written, in a key, a value, or a sequence item alike."""
        self.assertEqual(loads("a: value\u00a0\n"), {"a": "value\u00a0"})
        self.assertEqual(loads("k\u00a0: 1\n"), {"k\u00a0": 1})
        self.assertEqual(loads("a:\n  - item\u3000\n"), {"a": ["item\u3000"]})
        self.assertEqual(loads(dumps({"a": "value\u00a0"})), {"a": "value\u00a0"})

    def test_strips_comments_outside_quotes_only(self) -> None:
        data = loads('a: 1 # trailing\n# full line\nb: "kept # inside"\n')
        self.assertEqual(data, {"a": 1, "b": "kept # inside"})

    def test_a_quote_delimits_only_where_a_scalar_starts(self) -> None:
        """Quotes delimit a scalar only when the scalar itself starts
        quoted; anywhere else they are ordinary characters, so `5"` is a
        plain scalar with a comment after it rather than the start of a
        quoted scalar that never closes."""
        self.assertEqual(loads('note: 5" # inches\n'), {"note": '5"'})
        self.assertEqual(loads('a: x"y # z\n'), {"a": 'x"y'})
        self.assertEqual(loads('- 6" long # item\n'), ['6" long'])
        # Where one does start quoted, its interior `#` stays content and a
        # comment may follow the closing quote — escapes included.
        self.assertEqual(loads('b: "kept # inside"\n'), {"b": "kept # inside"})
        self.assertEqual(loads('c: "esc \\" still" # after\n'), {"c": 'esc " still'})
        with self.assertRaises(ProtocolYamlError):
            loads('d: "open\n')

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

    def test_rejects_raw_control_characters(self) -> None:
        """Raw, each is either invalid YAML that would survive into a value
        and be written back, or a line break the split consumes silently —
        a document that loses its shape rather than one that is refused."""
        for name, character in {
            "nul": "\x00", "bell": "\x07", "vertical tab": "\v",
            "escape": "\x1b", "delete": "\x7f", "next line": "\x85",
            "line separator": "\u2028", "paragraph separator": "\u2029",
        }.items():
            with self.subTest(character=name):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(f"a: before{character}after\n")
                self.assertIn("raw control character", str(caught.exception))
        # Tab, newline, and carriage return are YAML's own, and every
        # forbidden character is readable as an escape inside quotes.
        self.assertEqual(loads("a: b\tc\r\nd: e\n"), {"a": "b\tc", "d": "e"})
        self.assertEqual(loads('a: "b\\x00c"\n'), {"a": "b\x00c"})

    def test_rejects_a_document_nested_past_the_limit(self) -> None:
        """Nesting is recursion here, and Python's stack is not a subset
        rule: a document nested past it raised `RecursionError` out of the
        parser, past every handler that turns malformed input into a
        reported defect."""
        from driver.protocol_yaml import MAX_DEPTH

        def nest(depth: int) -> str:
            return (
                "".join("  " * level + f"k{level}:\n" for level in range(depth))
                + "  " * depth
                + "v: 1\n"
            )

        self.assertIsInstance(loads(nest(MAX_DEPTH - 2)), dict)
        for depth in (MAX_DEPTH + 5, 5000):
            with self.subTest(depth=depth):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(nest(depth))
                self.assertIn("nested past", str(caught.exception))

    def test_the_depth_guard_counts_through_inline_mappings_too(self) -> None:
        """A sequence entry's inline mapping is parsed by its own call, and
        that call once started the count again — so alternating the two
        shapes recursed past the guard and out through `RecursionError`."""
        from driver.protocol_yaml import MAX_DEPTH

        def nest(depth: int) -> str:
            lines = ["    " * level + "- k:" for level in range(depth)]
            lines.append("    " * depth + "- leaf")
            return "\n".join(lines) + "\n"

        self.assertIsInstance(loads(nest(5)), list)
        with self.assertRaises(ProtocolYamlError) as caught:
            loads(nest(MAX_DEPTH + 10))
        self.assertIn("nested past", str(caught.exception))

    def test_rejects_tabs_in_indentation(self) -> None:
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a:\n\tb: 1\n")
        self.assertIn("tab", str(caught.exception))

    def test_a_key_that_would_resolve_away_is_refused(self) -> None:
        """A key's type decides the mapping's shape, not one value in it:
        `1:` and `01:` are one integer key to a conforming reader and two
        string keys here — the same document read as two different mappings.
        `on:` stays the string key §9.1 declares."""
        for text in ("true: 1\n", "1: x\n", "01: x\n", "null: x\n",
                     "~: x\n", "2026-08-03: x\n", "0x10: x\n"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(text)
                self.assertIn("non-string", str(caught.exception))
        self.assertEqual(loads("on: x\nPASS: y\n"), {"on": "x", "PASS": "y"})

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\na: 2\n")
        self.assertIn("duplicate key", str(caught.exception))

    def test_rejects_anchors_aliases_and_flow(self) -> None:
        for text in ("a: &x 1\n", "a: *x\n", "a: [1, 2]\n", "a: |\n  x\n", "a: 'q'\n"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError):
                    loads(text)

    def test_rejects_every_indicator_a_plain_scalar_cannot_start_with(self) -> None:
        """Accepted as text, these are documents no conforming reader takes
        — and the emitter would rewrite them as quoted strings, laundering
        the malformation into valid YAML."""
        # `#` is in the set and unreachable through this spelling: after a
        # space it opens a comment, which is stripped before a token forms.
        for token in ("@reserved", "%directive", "`reserved", ",flow", "]flow",
                      "}flow", "&anchor", "*alias", "!tag", "- item",
                      "? key", "-", "?"):
            with self.subTest(token=token):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(f"a: {token}\n")
                self.assertIn("outside the subset", str(caught.exception))

    def test_keeps_the_plain_scalars_those_indicators_allow(self) -> None:
        """`-` and `:` open a scalar when what follows is not a space, and
        an indicator inside a token was never an indicator at all."""
        self.assertEqual(
            loads("a: -7\nb: :x\nc: x-y\nd: a#b\ne: 2026-08-03-x\n"),
            {"a": -7, "b": ":x", "c": "x-y", "d": "a#b", "e": "2026-08-03-x"},
        )

    def test_rejects_unterminated_quotes_and_bad_escapes(self) -> None:
        for text in ('a: "open\n', 'a: "\\q"\n', 'a: "\\xZZ"\n', 'a: "end\\"\n'):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError):
                    loads(text)

    def test_a_tab_separates_a_key_from_its_value(self) -> None:
        """YAML separates with a space or a tab, so a document written with
        the second is legal and must not be called malformed — inside a
        sequence entry's inline mapping as much as anywhere else."""
        self.assertEqual(loads("a:\tvalue\nb:\t1 # c\n"), {"a": "value", "b": 1})
        self.assertEqual(loads('c:\t"q # x"\n'), {"c": "q # x"})
        self.assertEqual(loads("- key:\tvalue\n"), [{"key": "value"}])
        # Mixed separation: whichever comes first ends the key, and the rest
        # of the run is skipped before the scalar begins — read as spaces
        # alone, a quoted value after `: \t` is not seen as quoted and its
        # `#` truncates it.
        self.assertEqual(loads('key: \t"kept # text"\n'), {"key": "kept # text"})
        self.assertEqual(loads('- key: \t"kept # text"\n'), [{"key": "kept # text"}])
        self.assertEqual(loads('a:\t "x # y"\n'), {"a": "x # y"})

    def test_an_integer_too_long_to_convert_is_a_subset_error(self) -> None:
        """Python caps `int()` at 4300 digits and YAML puts no ceiling on
        an integer's length, so a value of exactly this shape must be
        reported like any other rather than raising past every handler."""
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("iterations: " + "9" * 5000 + "\n")
        self.assertIn("outside the subset", str(caught.exception))

    def test_a_key_is_plain_on_the_page_or_it_is_not_a_key(self) -> None:
        """What YAML forbids at the start of a plain scalar it forbids at
        the start of a key: `!tag: 1` read as a string key while the
        emitter wrote tag syntax, and `{"- item": 1}` was written as
        `- item: 1` — a mapping out, a sequence back."""
        for key in ("- item", "-", "!tag", "&anchor", "*alias", "%directive"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    dumps({key: 1})
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("!tag: 1\n")
        self.assertIn("not a plain key", str(caught.exception))
        # The keys the protocol's own documents use stay writable.
        self.assertEqual(dumps({"on": 1, "PASS": 2}), "on: 1\nPASS: 2\n")

    def test_a_key_may_carry_a_space_on_both_sides(self) -> None:
        """§10's instrumentation is where a plain key with a space in it
        plausibly appears: refused on write, state that loads here could
        not be saved back."""
        self.assertEqual(loads("token count: 1\n"), {"token count": 1})
        self.assertEqual(dumps({"token count": 1}), "token count: 1\n")
        for key in (" leading", "trailing ", "a\tb"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    dumps({key: 1})
        # A tab is the other way round: no quoted-key form exists, so a key
        # the emitter cannot write is one the reader must not accept.
        with self.assertRaises(ProtocolYamlError):
            loads("token\tcount: 1\n")

    def test_rejects_a_plain_scalar_carrying_a_mapping_indicator(self) -> None:
        """`a: value: other` is a nested mapping on one line, which YAML
        refuses; read as text it is the misreading this module avoids.
        A tab is the other separator YAML gives that indicator."""
        for text in ("a: value: other\n", "a: value:\n", "- item: nested: deep\n",
                     "a: value:\tother\n"):
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

    def test_a_tab_separates_a_sequence_item_from_its_indicator(self) -> None:
        """`-` is the indicator and what follows it is separation, which is
        a space or a tab wherever else this module reads YAML. Knowing only
        the space, a sequence written with tabs was routed to the mapping
        parser and refused as a document no reader refuses."""
        self.assertEqual(loads("-\titem\n"), ["item"])
        self.assertEqual(loads("a:\n  -\tone\n  - two\n"), {"a": ["one", "two"]})
        self.assertEqual(loads(dumps(["item"])), ["item"])

    def test_an_inline_mapping_is_indented_where_its_key_stands(self) -> None:
        """The separation after `-` is whatever YAML allows, and the keys
        under it align with the key it carries — so where that key stands
        is where the mapping is indented from. Fixed at two columns, an
        item written with more separation had its continuation read as
        indentation nothing opened."""
        for text in (
            "- key: value\n  other: 1\n",
            "-   key: value\n    other: 1\n",
            "-\tkey: value\n  other: 1\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(loads(text), [{"key": "value", "other": 1}])

    def test_a_carriage_return_ends_a_line_for_the_line_number_too(self) -> None:
        """The reader takes CR as a line break — `splitlines` does — so the
        diagnostics have to count it as one: a document written with them
        reported every defect against line 1, which is the line-numbered
        error this module promises being no better than none."""
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\rb: 2\rc: \x00\r")
        self.assertEqual(caught.exception.line_number, 3)
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\r\nb: \x00\r\n")
        self.assertEqual(caught.exception.line_number, 2)

    def test_a_leading_byte_order_mark_is_the_stream_s_and_not_a_key_s(self) -> None:
        """A YAML stream may begin with U+FEFF, and every conforming reader
        takes it as the encoding marker it is. Read as content it becomes
        part of the first key, so a state file another tool wrote would
        carry `\\ufeffrun` here and resume on a document nothing recognizes."""
        self.assertEqual(loads("﻿run: 1\n"), {"run": 1})
        # Only the stream's own: one inside the document is content, and
        # content this subset does not carry.
        self.assertEqual(loads('a: "x﻿y"\n'), {"a": "x﻿y"})

    def test_rejects_the_two_code_points_yaml_excludes_outright(self) -> None:
        """YAML 1.2 keeps U+FFFE and U+FFFF out of the character stream, so
        a document carrying either raw is one no conforming reader accepts
        — and one this emitter must not write. Escaped, they are ordinary
        content: what the rule is about is the stream."""
        for character in ("\ufffe", "\uffff"):
            with self.subTest(character=character):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(f"a: before{character}after\n")
                self.assertIn("YAML", str(caught.exception))
                text = dumps({"a": f"x{character}y"})
                self.assertNotIn(character, text)
                self.assertEqual(loads(text), {"a": f"x{character}y"})

    def test_rejects_a_raw_surrogate_as_it_rejects_the_escape(self) -> None:
        """UTF-8 cannot carry a lone surrogate, which is why the escape for
        one is refused and why the emitter refuses the code point. Raw, it
        passed — and what came back was a value this module's own writer
        cannot put in a file, which is the round trip these two halves
        promise each other."""
        for text in ("a: \ud800\n", 'a: "x\udfffy"\n', "\ud800: 1\n"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolYamlError) as caught:
                    loads(text)
                self.assertIn("surrogate", str(caught.exception))
        with self.assertRaises(ProtocolYamlError) as caught:
            loads("a: 1\nb: \ud800\n")
        self.assertEqual(caught.exception.line_number, 2)

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
            "run": {"id": "2026-08-03-x", "workflow": "feature", "protocol": "0.3"},
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

    def test_quotes_every_string_core_would_resolve_away(self) -> None:
        """The one that mattered: `protocol: "0.3"` emitted plain is a float
        to every conforming reader, so the state the driver writes says one
        thing to this module and another — schema-invalid — to everyone
        else. Quoting is what keeps the type the value was given."""
        for value in ("0.2", "True", "TRUE", "NULL", "Null", "~", "+1", "007",
                      "0x10", "0o17", "1e3", ".inf", ".nan", ""):
            with self.subTest(value=value):
                text = dumps({"a": value})
                self.assertEqual(text, f'a: "{value}"\n')
                self.assertEqual(loads(text), {"a": value})

    def test_quotes_a_timestamp_another_reader_would_resolve(self) -> None:
        """Not a core kind, quoted all the same: readers in this ecosystem —
        the conformance suite's among them — resolve a plain timestamp to a
        datetime, while §10 declares `at` a string. A run id that merely
        contains a date is not one, and stays plain."""
        text = dumps({"at": "2026-08-03T13:40:00Z", "on": "2026-08-03",
                      "id": "2026-08-03-x"})
        self.assertEqual(
            text, 'at: "2026-08-03T13:40:00Z"\non: "2026-08-03"\nid: 2026-08-03-x\n'
        )

    def test_a_saved_run_state_keeps_every_scalar_its_type(self) -> None:
        """The whole point of the two rules above, on the documents that
        matter: what the driver writes back must carry the same types the
        fixture did, `protocol` and `at` as the strings §10 declares."""
        for path in sorted(
            (REPO / "protocol" / "schemas" / "examples").glob("run-state.valid*.yaml")
        ):
            with self.subTest(fixture=path.name):
                emitted = dumps(loads(path.read_text(encoding="utf-8")))
                self.assertIn('protocol: "', emitted)
                for line in emitted.splitlines():
                    if line.strip().startswith("at:"):
                        self.assertIn('at: "', line)

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

    def test_refuses_to_write_a_key_that_would_resolve_away(self) -> None:
        """The emitting half: this subset has no quoted keys, so a key
        another reader would retype is one the module cannot write."""
        for key in ("true", "42", "null", "2026-08-03"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    dumps({key: 1})
        self.assertEqual(dumps({"on": 1}), "on: 1\n")

    def test_rejects_values_outside_the_subset(self) -> None:
        for value in ({"a": 1.5}, {"a": {1: "int key"}}, {"bad:key": 1}, {"a": b"x"}):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    dumps(value)

    def test_empty_collections_dump_as_flow_empties(self) -> None:
        self.assertEqual(dumps({"a": [], "b": {}}), "a: []\nb: {}\n")

    def test_refuses_to_write_deeper_than_it_reads(self) -> None:
        """The reader stops at a depth far below where the interpreter's
        own stack gives out, and the writer knew no such bound — so a
        document it emitted could not be read back, which for run state is
        a save that persists what the next resume refuses."""
        deep: object = "leaf"
        for _ in range(70):
            deep = {"a": deep}
        with self.assertRaises(ValueError) as caught:
            dumps(deep)
        self.assertIn("nested too deeply", str(caught.exception))
        shallow: object = "leaf"
        for _ in range(30):
            shallow = {"a": shallow}
        self.assertEqual(loads(dumps(shallow)), shallow)

    def test_refuses_to_write_what_it_could_not_read_back(self) -> None:
        """A key is written plain and a lone surrogate cannot be encoded at
        all: accepted here, each reaches the save that writes the file — a
        newline splitting one field into two lines, a surrogate raising
        inside `stream.write` after the state was assembled."""
        for key in ("a\nb", "a\rb", "a\x00b", "a\x85b", "a\u2028b"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError) as caught:
                    dumps({key: 1})
                self.assertIn("cannot write plain", str(caught.exception))
        # Both sides of the mapping: a key is as unencodable as a value,
        # and only the value was ever checked — the text came back and the
        # save that writes it raised instead.
        for data in ({"a": "x\ud800y"}, {"a\ud800b": 1}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError) as caught:
                    dumps(data)
                self.assertIn("surrogate", str(caught.exception))

    def test_a_document_is_a_mapping_or_a_sequence(self) -> None:
        """Both shapes this module exists for are one of the two, and the
        reader parses nothing else — so a bare scalar written here is a
        document `loads` could not read back."""
        for data in (None, "text", 42, True, [], {}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    dumps(data)
        for data in ({"a": 1}, [1, 2]):
            with self.subTest(data=data):
                self.assertEqual(loads(dumps(data)), data)


if __name__ == "__main__":
    unittest.main()
