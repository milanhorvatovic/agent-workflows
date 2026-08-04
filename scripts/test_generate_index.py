"""Unit tests for generate_index.py.

Run from the repo root: python3 -m unittest discover -s scripts
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import generate_index

INDEX_TEMPLATE = """\
# fixture index

Intro prose that must survive regeneration.

## Roles

<!-- generated:roles -->
<!-- /generated:roles -->

## Skills

<!-- generated:skills -->
<!-- /generated:skills -->

## Workflows

<!-- generated:workflows -->
<!-- /generated:workflows -->

### Stages

<!-- generated:stages -->
<!-- /generated:stages -->

## Routing

Hand-written routing prose that must survive regeneration.
"""


def frontmatter(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"


class GenerateIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.index = self.root / "AGENTS.md"
        self.index.write_text(INDEX_TEMPLATE, encoding="utf-8")
        # Written out of canonical order to prove sorting is not filesystem order.
        self.write("roles/arbiter.md", frontmatter("arbiter", "Arbiter description."))
        self.write("roles/analyst.md", frontmatter("analyst", "Analyst description."))
        self.write("roles/README.md", "# roles/\n")
        self.write("workflows/overlays.md", frontmatter("overlays", "Overlays description."))
        self.write("workflows/feature.md", frontmatter("feature", "Feature description."))
        self.write("workflows/stages/delivery.md", frontmatter("delivery", "Delivery description."))
        self.write("workflows/stages/intake.md", frontmatter("intake", "Intake description."))

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_main(self, *argv: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = generate_index.main(["--root", str(self.root), *argv])
        return code, stdout.getvalue()

    def run_main_expecting_failure(self, *argv: str) -> str:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                generate_index.main(["--root", str(self.root), *argv])
        return str(caught.exception.code)

    def region(self, key: str) -> str:
        text = self.index.read_text(encoding="utf-8")
        begin = f"<!-- generated:{key} -->\n"
        end = f"<!-- /generated:{key} -->"
        return text.split(begin, 1)[1].split(end, 1)[0]

    def test_populates_sections_in_canonical_order(self) -> None:
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("regenerated", output)
        self.assertEqual(
            self.region("roles"),
            "- `roles/analyst.md` — Analyst description.\n"
            "- `roles/arbiter.md` — Arbiter description.\n",
        )
        self.assertEqual(
            self.region("workflows"),
            "- `workflows/feature.md` — Feature description.\n"
            "- `workflows/overlays.md` — Overlays description.\n",
        )
        self.assertEqual(
            self.region("stages"),
            "- `workflows/stages/intake.md` — Intake description.\n"
            "- `workflows/stages/delivery.md` — Delivery description.\n",
        )

    def test_unknown_slug_sorts_after_canonical_order(self) -> None:
        self.write("roles/aardvark.md", frontmatter("aardvark", "Aardvark description."))
        self.run_main()
        lines = self.region("roles").splitlines()
        self.assertEqual(lines[-1], "- `roles/aardvark.md` — Aardvark description.")

    def test_readme_files_are_excluded(self) -> None:
        self.run_main()
        self.assertNotIn("README", self.region("roles"))

    def test_empty_skills_tier_renders_placeholder(self) -> None:
        self.run_main()
        self.assertEqual(self.region("skills"), "_Not yet populated — one line per skill._\n")

    def test_skill_line_uses_directory_slug(self) -> None:
        self.write("skills/demo/SKILL.md", frontmatter("demo", "Demo skill description."))
        self.run_main()
        self.assertEqual(
            self.region("skills"),
            "- `skills/demo/SKILL.md` — Demo skill description.\n",
        )

    def test_hand_prose_survives_regeneration(self) -> None:
        self.run_main()
        text = self.index.read_text(encoding="utf-8")
        self.assertIn("Intro prose that must survive regeneration.", text)
        self.assertIn("Hand-written routing prose that must survive regeneration.", text)

    def test_regeneration_is_idempotent(self) -> None:
        self.run_main()
        first = self.index.read_text(encoding="utf-8")
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("up to date", output)
        self.assertEqual(self.index.read_text(encoding="utf-8"), first)

    def test_check_passes_when_consistent(self) -> None:
        self.run_main()
        code, output = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("up to date", output)

    def test_check_reports_drift_without_writing(self) -> None:
        self.run_main()
        drifted = self.index.read_text(encoding="utf-8").replace(
            "Analyst description.", "Drifted description."
        )
        self.index.write_text(drifted, encoding="utf-8")
        code, output = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("stale", output)
        self.assertIn("-", output.splitlines()[0])  # unified diff header present
        self.assertIn("+- `roles/analyst.md` — Analyst description.", output)
        self.assertEqual(self.index.read_text(encoding="utf-8"), drifted)

    def test_quoted_description_is_unquoted(self) -> None:
        self.write("roles/analyst.md", frontmatter("analyst", '"Quoted description."'))
        self.run_main()
        self.assertIn("- `roles/analyst.md` — Quoted description.\n", self.region("roles"))

    def test_missing_frontmatter_fails(self) -> None:
        self.write("roles/broken.md", "# no frontmatter\n")
        message = self.run_main_expecting_failure()
        self.assertIn("roles/broken.md: no frontmatter block", message)

    def test_missing_description_fails(self) -> None:
        self.write("roles/broken.md", "---\nname: broken\n---\n")
        message = self.run_main_expecting_failure()
        self.assertIn("roles/broken.md: frontmatter has no description", message)

    def test_quoted_empty_or_blank_description_fails(self) -> None:
        for raw in ('""', '" "', "''"):
            with self.subTest(raw=raw):
                self.write("roles/broken.md", f"---\nname: broken\ndescription: {raw}\n---\n")
                message = self.run_main_expecting_failure()
                self.assertIn("roles/broken.md: description is empty", message)

    def test_block_scalar_description_fails(self) -> None:
        self.write("roles/broken.md", "---\nname: broken\ndescription: >-\n  wrapped\n---\n")
        message = self.run_main_expecting_failure()
        self.assertIn("roles/broken.md: description must be a single-line scalar", message)

    def test_empty_required_section_fails(self) -> None:
        for path in (self.root / "roles").glob("*.md"):
            path.unlink()
        message = self.run_main_expecting_failure()
        self.assertIn("no files match roles/*.md", message)

    def test_duplicate_marker_region_fails(self) -> None:
        text = self.index.read_text(encoding="utf-8")
        self.index.write_text(
            text + "\n<!-- generated:roles -->\n<!-- /generated:roles -->\n",
            encoding="utf-8",
        )
        message = self.run_main_expecting_failure()
        self.assertIn("found 2", message)

    def test_missing_marker_region_fails(self) -> None:
        text = self.index.read_text(encoding="utf-8").replace(
            "<!-- generated:skills -->\n<!-- /generated:skills -->\n", ""
        )
        self.index.write_text(text, encoding="utf-8")
        message = self.run_main_expecting_failure()
        self.assertIn("generated:skills", message)
        self.assertIn("found 0", message)

    def test_missing_index_file_fails(self) -> None:
        self.index.unlink()
        message = self.run_main_expecting_failure()
        self.assertIn("not found", message)


if __name__ == "__main__":
    unittest.main()
