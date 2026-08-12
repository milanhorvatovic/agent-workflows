"""Unit tests for init.py.

Run from the repo root: python3 -m unittest discover -s setup
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import init

CONFIG = {
    "placeholders": {
        "PROJECT_NAME": "Sample",
        "TECH_STACK": "Python",
        "ARCHITECTURE_TYPE": "modular monolith",
    },
    "commit_format": "conventional",
    "pr_format": "github",
}

INSTALLED_STANDARDS = ("coding.md", "review-checklist.md", "commit-conventional.md", "pr-github.md")


class SetupInitTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.source = base / "framework"
        self.target = base / "project"
        self.config_dir = base
        self.write(
            "skills/awf-alpha/SKILL.md",
            "---\nname: awf-alpha\n---\n\n# awf-alpha\n",
        )
        self.write("skills/awf-alpha/references/notes.md", "# Notes\n")
        self.write("skills/awf-beta/SKILL.md", "---\nname: awf-beta\n---\n\n# awf-beta\n")
        self.write("skills/README.md", "# skills/\n\nNot a skill package.\n")
        self.write(
            "standards/coding.md",
            "# Coding — {{PROJECT_NAME}}\n\nStack: {{TECH_STACK}}.\n"
            "Pattern: {{ARCHITECTURE_TYPE}}.\n",
        )
        self.write("standards/review-checklist.md", "# Review checklist — {{PROJECT_NAME}}\n")
        self.write("standards/commit-conventional.md", "# Conventional commits — {{PROJECT_NAME}}\n")
        self.write("standards/commit-angular.md", "# Angular commits — {{PROJECT_NAME}}\n")
        self.write("standards/pr-github.md", "# GitHub PRs — {{PROJECT_NAME}}\n")
        self.write("standards/ticket-jira.md", "# Jira tickets — {{PROJECT_NAME}}\n")
        self.write("standards/ticket-linear.md", "# Linear tickets — {{PROJECT_NAME}}\n")
        self.write("standards/README.md", "# standards/\n\nNot a source.\n")
        self.write(
            "CHANGELOG.md",
            "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-08-12\n\n"
            "## [0.1.0] - 2026-08-04\n",
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_target(self, relative: str, text: str) -> Path:
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def config_file(self, values: dict) -> Path:
        path = self.config_dir / "setup.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return path

    def run_main(self, *argv: str, answers: list[str] | None = None) -> tuple[int, str, str]:
        ask = None
        if answers is not None:
            answer_iter = iter(answers)

            def ask(prompt: str) -> str:
                return next(answer_iter)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = init.main([*argv, "--root", str(self.source)], ask=ask)
            except SystemExit as error:
                code = error.code if isinstance(error.code, int) else 1
                if isinstance(error.code, str):
                    stderr.write(error.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def install(self, config: dict | None = None, *extra: str) -> tuple[int, str, str]:
        path = self.config_file(config if config is not None else CONFIG)
        return self.run_main("--target", str(self.target), "--config", str(path), *extra)

    def read_manifest(self) -> dict:
        path = self.target / init.MANIFEST_PATH
        return json.loads(path.read_text(encoding="utf-8"))

    def tree_state(self) -> dict[str, bytes]:
        return {
            p.relative_to(self.target).as_posix(): p.read_bytes()
            for p in sorted(self.target.rglob("*"))
            if p.is_file()
        }

    # --- fresh install ---

    def test_installs_every_skill_package(self) -> None:
        code, out, err = self.install()
        self.assertEqual(code, 0, err)
        for relative in (
            ".agents/skills/awf-alpha/SKILL.md",
            ".agents/skills/awf-alpha/references/notes.md",
            ".agents/skills/awf-beta/SKILL.md",
        ):
            self.assertTrue((self.target / relative).is_file(), relative)
        self.assertIn("skill awf-alpha: installed", out)
        self.assertIn("skill awf-beta: installed", out)

    def test_skills_readme_is_not_a_package(self) -> None:
        self.install()
        self.assertFalse((self.target / ".agents/skills/README.md").exists())

    def test_renders_selected_standards_with_substitution(self) -> None:
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        for name in INSTALLED_STANDARDS:
            self.assertTrue((self.target / f".agents/standards/{name}").is_file(), name)
            self.assertIn(f"standard {name}: installed", out)
        coding = (self.target / ".agents/standards/coding.md").read_text(encoding="utf-8")
        self.assertIn("# Coding — Sample", coding)
        self.assertIn("Stack: Python.", coding)
        self.assertNotIn("{{", coding)

    def test_unselected_variants_are_not_installed(self) -> None:
        self.install()
        for name in ("commit-angular.md", "ticket-jira.md", "ticket-linear.md"):
            self.assertFalse((self.target / f".agents/standards/{name}").exists(), name)

    def test_manifest_records_every_install(self) -> None:
        self.install()
        manifest = self.read_manifest()
        self.assertEqual(manifest["manifest_version"], 1)
        entries = manifest["entries"]
        self.assertIn(".agents/skills/awf-alpha", entries)
        self.assertIn(".agents/standards/coding.md", entries)
        for entry in entries.values():
            self.assertEqual(entry["source_tag"], "0.2.0")
            self.assertTrue(entry["digest"].startswith("sha256:"))

    def test_summary_counts_the_first_run(self) -> None:
        _, out, _ = self.install()
        self.assertIn("6 installed, 0 refreshed, 0 up to date, 0 adopted, 0 skipped, 0 stale", out)

    # --- idempotency ---

    def test_second_run_changes_nothing(self) -> None:
        self.install()
        before = self.tree_state()
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(before, self.tree_state())
        self.assertIn("0 installed, 0 refreshed, 6 up to date", out)

    def test_junk_in_source_is_ignored(self) -> None:
        self.write("skills/awf-alpha/__pycache__/junk.pyc", "junk")
        self.write("skills/awf-alpha/.DS_Store", "junk")
        self.install()
        self.assertFalse((self.target / ".agents/skills/awf-alpha/__pycache__").exists())
        self.assertFalse((self.target / ".agents/skills/awf-alpha/.DS_Store").exists())
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: up to date", out)

    # --- collision guard ---

    def test_foreign_skill_directory_is_left_untouched(self) -> None:
        self.write_target(".agents/skills/awf-alpha/SKILL.md", "the consumer's own\n")
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(
            (self.target / ".agents/skills/awf-alpha/SKILL.md").read_text(encoding="utf-8"),
            "the consumer's own\n",
        )
        self.assertIn(
            "skill awf-alpha: skipped — exists but was not installed by setup; left untouched",
            out,
        )
        self.assertNotIn(".agents/skills/awf-alpha", self.read_manifest()["entries"])
        self.assertIn("skill awf-beta: installed", out)

    def test_foreign_standard_file_is_left_untouched(self) -> None:
        self.write_target(".agents/standards/coding.md", "the consumer's own\n")
        _, out, _ = self.install()
        self.assertEqual(
            (self.target / ".agents/standards/coding.md").read_text(encoding="utf-8"),
            "the consumer's own\n",
        )
        self.assertIn("standard coding.md: skipped — exists but was not installed by setup", out)

    def test_identical_foreign_content_is_adopted(self) -> None:
        shutil.copytree(self.source / "skills/awf-alpha", self.target / ".agents/skills/awf-alpha")
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: adopted", out)
        self.assertIn(".agents/skills/awf-alpha", self.read_manifest()["entries"])

    def test_directory_digest_sees_empty_subdirectories(self) -> None:
        skill = self.source / "skills/awf-alpha"
        before = init.content_digest(skill)
        (skill / "scratch").mkdir()
        self.assertNotEqual(before, init.content_digest(skill))

    def test_extra_empty_directory_is_not_adopted_as_identical(self) -> None:
        shutil.copytree(self.source / "skills/awf-alpha", self.target / ".agents/skills/awf-alpha")
        (self.target / ".agents/skills/awf-alpha/scratch").mkdir()
        _, out, _ = self.install()
        self.assertIn(
            "skill awf-alpha: skipped — exists but was not installed by setup", out
        )
        self.assertTrue((self.target / ".agents/skills/awf-alpha/scratch").is_dir())

    def test_tree_digest_is_self_delimiting(self) -> None:
        one = self.source / "one"
        one.mkdir()
        # Under a delimiter-only serialization this content forges the exact
        # byte stream of the two-file tree below.
        (one / "a.md").write_bytes(b"X\x00f\x00b.md\x00Y")
        two = self.source / "two"
        two.mkdir()
        (two / "a.md").write_bytes(b"X")
        (two / "b.md").write_bytes(b"Y")
        self.assertNotEqual(init.content_digest(one), init.content_digest(two))

    def test_file_replaced_by_an_equivalent_symlink_reads_as_modified(self) -> None:
        self.install()
        skill_file = self.target / ".agents/skills/awf-alpha/SKILL.md"
        aside = self.target / "elsewhere.md"
        aside.write_bytes(skill_file.read_bytes())
        skill_file.unlink()
        skill_file.symlink_to(aside)
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: skipped — locally modified since install", out)
        self.assertTrue(skill_file.is_symlink())

    def test_empty_file_and_empty_directory_digests_differ(self) -> None:
        empty_file = self.write("empty.md", "")
        empty_dir = self.source / "emptydir"
        empty_dir.mkdir()
        self.assertNotEqual(init.content_digest(empty_file), init.content_digest(empty_dir))

    def test_empty_directory_at_a_standard_path_is_not_adopted(self) -> None:
        self.write("standards/empty-note.md", "")
        (self.target / ".agents/standards/empty-note.md").mkdir(parents=True)
        _, out, _ = self.install()
        self.assertIn(
            "standard empty-note.md: skipped — exists but was not installed by setup", out
        )
        self.assertTrue((self.target / ".agents/standards/empty-note.md").is_dir())

    def test_dangling_symlink_at_a_planned_path_is_not_replaced(self) -> None:
        standards = self.target / ".agents/standards"
        standards.mkdir(parents=True)
        (standards / "coding.md").symlink_to(self.target / "nowhere.md")
        _, out, _ = self.install()
        self.assertIn(
            "standard coding.md: skipped — a symlink sits at this path", out
        )
        self.assertTrue((standards / "coding.md").is_symlink())

    def test_stale_path_replaced_by_a_dangling_symlink_stays_recorded(self) -> None:
        self.install({**CONFIG, "ticket_format": "jira"})
        stale = self.target / ".agents/standards/ticket-jira.md"
        stale.unlink()
        stale.symlink_to(self.target / "nowhere.md")
        _, out, _ = self.install()
        self.assertIn("standard ticket-jira.md: stale", out)
        self.assertIn(".agents/standards/ticket-jira.md", self.read_manifest()["entries"])

    def test_symlinked_managed_directory_is_refused(self) -> None:
        outside = self.config_dir / "outside"
        outside.mkdir()
        (self.target / ".agents").mkdir(parents=True)
        (self.target / ".agents/skills").symlink_to(outside)
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("managed path is a symlink", err)
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_at_a_managed_path_is_refused_before_installing(self) -> None:
        self.write_target(".agents/standards", "a file where a directory belongs")
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("managed path is not a directory", err)
        self.assertFalse((self.target / ".agents/skills").exists())

    def test_target_inside_the_framework_root_is_refused(self) -> None:
        code, _, err = self.run_main("--target", str(self.source / "skills/awf-alpha"))
        self.assertNotEqual(code, 0)
        self.assertIn("inside the framework repository", err)

    def test_identical_foreign_standard_is_adopted(self) -> None:
        self.write_target(
            ".agents/standards/coding.md",
            "# Coding — Sample\n\nStack: Python.\nPattern: modular monolith.\n",
        )
        _, out, _ = self.install()
        self.assertIn("standard coding.md: adopted", out)
        self.assertIn(".agents/standards/coding.md", self.read_manifest()["entries"])

    def test_locally_modified_install_is_never_overwritten(self) -> None:
        self.install()
        self.write_target(".agents/skills/awf-alpha/SKILL.md", "customized\n")
        self.write("skills/awf-alpha/SKILL.md", "upstream moved on\n")
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(
            (self.target / ".agents/skills/awf-alpha/SKILL.md").read_text(encoding="utf-8"),
            "customized\n",
        )
        self.assertIn("skill awf-alpha: skipped — locally modified since install", out)

    def test_modified_standard_is_never_overwritten(self) -> None:
        self.install()
        self.write_target(".agents/standards/coding.md", "customized\n")
        _, out, _ = self.install()
        self.assertEqual(
            (self.target / ".agents/standards/coding.md").read_text(encoding="utf-8"),
            "customized\n",
        )
        self.assertIn("standard coding.md: skipped — locally modified since install", out)

    # --- upgrades ---

    def test_unmodified_install_is_refreshed_when_source_changes(self) -> None:
        self.install()
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v2\n")
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertIn("skill awf-alpha: refreshed", out)
        self.assertIn(
            "# v2",
            (self.target / ".agents/skills/awf-alpha/SKILL.md").read_text(encoding="utf-8"),
        )

    def test_refresh_drops_files_the_source_no_longer_ships(self) -> None:
        self.install()
        (self.source / "skills/awf-alpha/references/notes.md").unlink()
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v2\n")
        self.install()
        self.assertFalse(
            (self.target / ".agents/skills/awf-alpha/references/notes.md").exists()
        )

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_failed_copy_leaves_no_partial_install(self) -> None:
        unreadable = self.source / "skills/awf-alpha/references/notes.md"
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o644)
        item = init.Item(
            "skill", "awf-alpha", self.source / "skills/awf-alpha", ".agents/skills/awf-alpha"
        )
        destination = self.target / item.target_rel
        with self.assertRaises(shutil.Error):
            init.write_item(item, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list((self.target / ".agents/skills").iterdir()), [])

    def test_failed_promotion_restores_the_old_install(self) -> None:
        self.install()
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v2\n")
        destination = self.target / ".agents/skills/awf-alpha"
        item = init.Item(
            "skill", "awf-alpha", self.source / "skills/awf-alpha", ".agents/skills/awf-alpha"
        )
        original_rename = Path.rename

        def failing_promotion(path: Path, target: Path) -> Path:
            if Path(target) == destination and path.name == "awf-alpha":
                raise OSError("promotion failed")
            return original_rename(path, target)

        with unittest.mock.patch.object(Path, "rename", failing_promotion):
            with self.assertRaises(OSError):
                init.write_item(item, destination)
        self.assertIn(
            "# awf-alpha", (destination / "SKILL.md").read_text(encoding="utf-8")
        )

    def test_deleted_install_is_reinstalled(self) -> None:
        self.install()
        shutil.rmtree(self.target / ".agents/skills/awf-alpha")
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: installed", out)
        self.assertTrue((self.target / ".agents/skills/awf-alpha/SKILL.md").is_file())

    # --- stale reporting ---

    def test_deselected_standard_is_reported_stale(self) -> None:
        self.install({**CONFIG, "ticket_format": "jira"})
        _, out, _ = self.install()
        self.assertIn(
            "standard ticket-jira.md: stale — installed by an earlier run but "
            "not selected by this run; remove manually if unwanted",
            out,
        )
        self.assertTrue((self.target / ".agents/standards/ticket-jira.md").is_file())

    def test_skill_no_longer_shipped_is_reported_stale(self) -> None:
        self.install()
        shutil.rmtree(self.source / "skills/awf-beta")
        _, out, _ = self.install()
        self.assertIn(
            "skill awf-beta: stale — installed by an earlier run but "
            "no longer shipped by this source; remove manually if unwanted",
            out,
        )
        self.assertTrue((self.target / ".agents/skills/awf-beta/SKILL.md").is_file())

    def test_stale_entry_for_a_removed_path_is_dropped(self) -> None:
        self.install({**CONFIG, "ticket_format": "jira"})
        (self.target / ".agents/standards/ticket-jira.md").unlink()
        _, out, _ = self.install()
        self.assertNotIn("ticket-jira.md", out)
        self.assertNotIn(".agents/standards/ticket-jira.md", self.read_manifest()["entries"])

    # --- config validation ---

    def test_unknown_config_key_fails(self) -> None:
        code, _, err = self.install({**CONFIG, "typo_key": "x"})
        self.assertNotEqual(code, 0)
        self.assertIn("unknown key(s): typo_key", err)
        self.assertIn("known:", err)

    def test_unknown_variant_fails_naming_available(self) -> None:
        code, _, err = self.install({**CONFIG, "ticket_format": "asana"})
        self.assertNotEqual(code, 0)
        self.assertIn('unknown ticket format "asana"', err)
        self.assertIn("available: jira, linear", err)

    def test_non_string_variant_fails(self) -> None:
        code, _, err = self.install({**CONFIG, "ticket_format": 7})
        self.assertNotEqual(code, 0)
        self.assertIn('"ticket_format" must be a string', err)

    def test_missing_placeholders_object_fails(self) -> None:
        code, _, err = self.install({"commit_format": "conventional"})
        self.assertNotEqual(code, 0)
        self.assertIn('missing "placeholders" object', err)

    def test_non_object_placeholders_fails(self) -> None:
        code, _, err = self.install({**CONFIG, "placeholders": ["x"]})
        self.assertNotEqual(code, 0)
        self.assertIn("placeholders: config must be a JSON object", err)

    def test_unknown_placeholder_fails(self) -> None:
        config = {**CONFIG, "placeholders": {**CONFIG["placeholders"], "TYPO": "x"}}
        code, _, err = self.install(config)
        self.assertNotEqual(code, 0)
        self.assertIn('unknown placeholder "TYPO"', err)

    def test_missing_placeholder_value_fails(self) -> None:
        config = {**CONFIG, "placeholders": {"PROJECT_NAME": "Sample"}}
        code, _, err = self.install(config)
        self.assertNotEqual(code, 0)
        self.assertIn("missing value(s) for", err)

    def test_invalid_json_config_fails(self) -> None:
        path = self.config_dir / "setup.json"
        path.write_text("{not json", encoding="utf-8")
        code, _, err = self.run_main("--target", str(self.target), "--config", str(path))
        self.assertNotEqual(code, 0)
        self.assertIn("invalid JSON", err)

    def test_non_object_config_fails(self) -> None:
        path = self.config_dir / "setup.json"
        path.write_text('["a"]', encoding="utf-8")
        code, _, err = self.run_main("--target", str(self.target), "--config", str(path))
        self.assertNotEqual(code, 0)
        self.assertIn("config must be a JSON object", err)

    def test_failed_config_installs_nothing(self) -> None:
        code, _, _ = self.install({**CONFIG, "typo_key": "x"})
        self.assertNotEqual(code, 0)
        self.assertFalse(self.target.exists())

    # --- interactive mode ---

    def test_interview_produces_the_config_run_result(self) -> None:
        self.install()
        config_tree = self.tree_state()
        shutil.rmtree(self.target)
        code, out, _ = self.run_main(
            "--target",
            str(self.target),
            answers=["Sample", "Python", "modular monolith", "conventional", "github", ""],
        )
        self.assertEqual(code, 0)
        self.assertEqual(config_tree, self.tree_state())
        self.assertIn("To repeat this setup non-interactively", out)
        self.assertIn('"commit_format": "conventional"', out)

    def test_interview_reprompts_until_a_shipped_variant(self) -> None:
        code, _, _ = self.run_main(
            "--target",
            str(self.target),
            answers=["Sample", "Python", "arch", "bogus", "conventional", "", ""],
        )
        self.assertEqual(code, 0)
        self.assertTrue(
            (self.target / ".agents/standards/commit-conventional.md").is_file()
        )

    def test_interview_defaults_project_name_to_target_directory(self) -> None:
        code, _, _ = self.run_main(
            "--target",
            str(self.target),
            answers=["", "Python", "arch", "", "", ""],
        )
        self.assertEqual(code, 0)
        coding = (self.target / ".agents/standards/coding.md").read_text(encoding="utf-8")
        self.assertIn("# Coding — project", coding)

    def test_interview_asks_project_name_first(self) -> None:
        prompts: list[str] = []
        answers = iter(["Sample", "Python", "arch", "", "", ""])

        def ask(prompt: str) -> str:
            prompts.append(prompt)
            return next(answers)

        init.interview(
            {"commit": ["conventional"], "pr": ["github"], "ticket": []}, "project", ask
        )
        self.assertTrue(prompts[0].startswith("PROJECT_NAME"), prompts[0])
        self.assertIn("[project]", prompts[0])

    def test_no_terminal_and_no_config_fails(self) -> None:
        fake_stdin = unittest.mock.Mock()
        fake_stdin.isatty.return_value = False
        with unittest.mock.patch("sys.stdin", fake_stdin):
            code, _, err = self.run_main("--target", str(self.target))
        self.assertNotEqual(code, 0)
        self.assertIn("pass --config for non-interactive setup", err)

    # --- source tag ---

    def test_source_tag_override_lands_in_the_manifest(self) -> None:
        self.install(CONFIG, "--source-tag", "v1.2.3-test")
        entries = self.read_manifest()["entries"]
        self.assertEqual(entries[".agents/skills/awf-alpha"]["source_tag"], "v1.2.3-test")

    def test_retag_with_unchanged_content_keeps_the_manifest(self) -> None:
        self.install(CONFIG, "--source-tag", "old-tag")
        before = (self.target / init.MANIFEST_PATH).read_bytes()
        _, out, _ = self.install(CONFIG, "--source-tag", "new-tag")
        self.assertIn("6 up to date", out)
        self.assertEqual(before, (self.target / init.MANIFEST_PATH).read_bytes())

    def test_refresh_records_the_new_source_tag(self) -> None:
        self.install(CONFIG, "--source-tag", "old-tag")
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v2\n")
        _, out, _ = self.install(CONFIG, "--source-tag", "new-tag")
        self.assertIn("skill awf-alpha: refreshed", out)
        entries = self.read_manifest()["entries"]
        self.assertEqual(entries[".agents/skills/awf-alpha"]["source_tag"], "new-tag")

    def test_interrupted_refresh_is_reconciled_not_misread_as_modified(self) -> None:
        self.install()
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v2\n")
        # A run that dies between writing the refresh and saving the manifest
        # leaves the new content on disk under the old record.
        shutil.rmtree(self.target / ".agents/skills/awf-alpha")
        shutil.copytree(self.source / "skills/awf-alpha", self.target / ".agents/skills/awf-alpha")
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: up to date", out)
        self.write("skills/awf-alpha/SKILL.md", "---\nname: awf-alpha\n---\n\n# v3\n")
        _, out, _ = self.install()
        self.assertIn("skill awf-alpha: refreshed", out)
        self.assertIn(
            "# v3",
            (self.target / ".agents/skills/awf-alpha/SKILL.md").read_text(encoding="utf-8"),
        )

    def test_source_tag_falls_back_to_the_changelog(self) -> None:
        _, out, _ = self.install()
        self.assertIn("source tag 0.2.0", out)

    def test_source_tag_unknown_without_git_or_changelog(self) -> None:
        (self.source / "CHANGELOG.md").unlink()
        _, out, _ = self.install()
        self.assertIn("source tag unknown", out)

    def test_source_tag_survives_a_broken_git_checkout(self) -> None:
        (self.source / ".git").mkdir()
        _, out, _ = self.install()
        self.assertIn("source tag 0.2.0", out)

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_source_tag_from_git_describe(self) -> None:
        git = [
            "git", "-C", str(self.source),
            "-c", "user.name=t", "-c", "user.email=t@t",
            "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
        ]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
        subprocess.run([*git, "tag", "v9.9.9"], check=True)
        _, out, _ = self.install()
        self.assertIn("source tag v9.9.9", out)

    # --- manifest handling ---

    def test_incompatible_manifest_version_fails(self) -> None:
        self.write_target(
            init.MANIFEST_PATH, json.dumps({"manifest_version": 2, "entries": {}})
        )
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("manifest_version 2 is not 1", err)

    def test_invalid_manifest_json_fails(self) -> None:
        self.write_target(init.MANIFEST_PATH, "{not json")
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("invalid JSON", err)

    def test_manifest_without_entries_fails(self) -> None:
        self.write_target(init.MANIFEST_PATH, json.dumps({"manifest_version": 1}))
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("not an install manifest", err)

    def test_malformed_manifest_entry_fails(self) -> None:
        for entry in ("a string", {"source_tag": "0.2.0"}, {"digest": 7, "source_tag": "x"}):
            with self.subTest(entry=entry):
                self.write_target(
                    init.MANIFEST_PATH,
                    json.dumps({"manifest_version": 1, "entries": {"x": entry}}),
                )
                code, _, err = self.install()
                self.assertNotEqual(code, 0)
                self.assertIn("entry 'x' is not an install record", err)

    def test_directory_at_the_manifest_path_fails_before_installing(self) -> None:
        (self.target / init.MANIFEST_PATH).mkdir(parents=True)
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("not a regular file", err)
        self.assertFalse((self.target / ".agents/skills").exists())

    def test_dangling_symlink_at_the_manifest_path_fails(self) -> None:
        manifest = self.target / init.MANIFEST_PATH
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(self.target / "nowhere.json")
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("not a regular file", err)

    def test_manifest_save_leaves_no_staging_residue(self) -> None:
        self.install()
        agents = self.target / ".agents"
        residue = [p.name for p in agents.iterdir() if p.name.startswith("awf-install-manifest.json") and p.name != "awf-install-manifest.json"]
        self.assertEqual(residue, [])

    # --- target and source guards ---

    def test_target_that_is_a_file_fails(self) -> None:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("a file where the project should be", encoding="utf-8")
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("not a directory", err)

    def test_source_shipping_a_symlink_is_refused_before_installing(self) -> None:
        (self.source / "skills/awf-alpha/references/link.md").symlink_to(
            self.source / "skills/awf-alpha/SKILL.md"
        )
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("the source ships a symlink", err)
        self.assertFalse(self.target.exists())

    def test_missing_skills_fails(self) -> None:
        shutil.rmtree(self.source / "skills")
        code, _, err = self.install()
        self.assertNotEqual(code, 0)
        self.assertIn("no skill packages under", err)


if __name__ == "__main__":
    unittest.main()
