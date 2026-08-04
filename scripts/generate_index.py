#!/usr/bin/env python3
"""Generate the tier sections of AGENTS.md from file frontmatter.

AGENTS.md is the discovery surface: one line per role, skill, workflow, and
stage, each line taking its description verbatim from the file's frontmatter
so the index cannot drift from its sources. Only the regions between
`<!-- generated:<key> -->` markers are rewritten; hand-written prose outside
them is left untouched.

Usage:
    python3 scripts/generate_index.py           # rewrite AGENTS.md in place
    python3 scripts/generate_index.py --check   # exit 1 if AGENTS.md is stale
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
DESCRIPTION = re.compile(r"^description:[ \t]*(\S.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    key: str  # marker name: <!-- generated:<key> -->
    pattern: str  # glob relative to the repo root
    order: tuple[str, ...] = ()  # canonical order; extras follow alphabetically
    placeholder: str | None = None  # emitted when the glob matches nothing


SECTIONS = (
    Section(
        key="roles",
        pattern="roles/*.md",
        order=("analyst", "planner", "implementer", "reviewer", "validator", "arbiter"),
    ),
    Section(
        key="skills",
        pattern="skills/*/SKILL.md",
        placeholder="_Not yet populated — one line per skill._",
    ),
    Section(
        key="workflows",
        pattern="workflows/*.md",
        order=("feature", "bugfix", "plan", "overlays"),
    ),
    Section(
        key="stages",
        pattern="workflows/stages/*.md",
        order=("intake", "ideation", "planning", "implementation", "review", "delivery"),
    ),
)


def fail(message: str) -> NoReturn:
    sys.exit(f"generate-index: {message}")


def description_of(path: Path, root: Path) -> str:
    text = path.read_text(encoding="utf-8")
    frontmatter = FRONTMATTER.match(text)
    if frontmatter is None:
        fail(f"{path.relative_to(root)}: no frontmatter block")
    found = DESCRIPTION.search(frontmatter.group(1))
    if found is None:
        fail(f"{path.relative_to(root)}: frontmatter has no description")
    value = found.group(1).strip()
    if value[0] in ">|":
        fail(f"{path.relative_to(root)}: description must be a single-line scalar")
    if len(value) > 1 and value[0] in "'\"" and value[-1] == value[0]:
        value = value[1:-1].strip()
    if not value:
        fail(f"{path.relative_to(root)}: description is empty")
    return value


def slug_of(path: Path) -> str:
    return path.parent.name if path.name == "SKILL.md" else path.stem


def section_lines(section: Section, root: Path) -> list[str]:
    paths = [p for p in root.glob(section.pattern) if p.name != "README.md"]
    if not paths:
        if section.placeholder is None:
            fail(f"no files match {section.pattern}")
        return [section.placeholder]

    def sort_key(path: Path) -> tuple[int, str]:
        slug = slug_of(path)
        rank = section.order.index(slug) if slug in section.order else len(section.order)
        return (rank, slug)

    paths.sort(key=sort_key)
    return [
        f"- `{p.relative_to(root).as_posix()}` — {description_of(p, root)}"
        for p in paths
    ]


def replace_region(text: str, key: str, lines: list[str]) -> str:
    begin = f"<!-- generated:{key} -->"
    end = f"<!-- /generated:{key} -->"
    region = re.compile(re.escape(begin) + r"\n(?:.*\n)*?" + re.escape(end))
    count = len(region.findall(text))
    if count != 1:
        fail(f"AGENTS.md: expected exactly one {begin} … {end} region, found {count}")
    replacement = "\n".join([begin, *lines, end])
    return region.sub(lambda _: replacement, text)


def regenerate(text: str, root: Path) -> str:
    for section in SECTIONS:
        text = replace_region(text, section.key, section_lines(section, root))
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify AGENTS.md matches its sources instead of rewriting it",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repository root to operate on (default: this script's repository)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    index = root / "AGENTS.md"
    if not index.is_file():
        fail(f"{index}: not found")

    current = index.read_text(encoding="utf-8")
    regenerated = regenerate(current, root)

    if regenerated == current:
        print("AGENTS.md: up to date")
        return 0
    if args.check:
        sys.stdout.writelines(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                regenerated.splitlines(keepends=True),
                fromfile="AGENTS.md (committed)",
                tofile="AGENTS.md (regenerated)",
            )
        )
        print("AGENTS.md: stale — run scripts/generate_index.py")
        return 1
    index.write_text(regenerated, encoding="utf-8")
    print("AGENTS.md: regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
