#!/usr/bin/env python3
"""Render project-specific standards from the standards/ single source.

standards/*.md are the canonical, placeholder-parameterized sources; rendered
copies are generated, never hand-maintained. Substitution replaces every
`{{PLACEHOLDER}}` with the value the consumer supplies in a JSON config, and
the placeholder vocabulary is closed: a source using an unregistered token, or
malformed double-brace syntax, fails loudly. Single-brace text (URL templates
like `/users/{id}`, JSON examples) passes through untouched.

Usage:
    python3 scripts/render_standards.py --check
        # validate placeholder integrity of every source (run by CI)
    python3 scripts/render_standards.py --config cfg.json --out DIR [--only a,b]
        # render sources into DIR; --only limits to named standards
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

# The closed placeholder vocabulary. A new placeholder is added here first;
# sources may then use it and configs must then supply it.
PLACEHOLDERS = {
    "PROJECT_NAME": "the consuming project's name",
    "TECH_STACK": "the project's primary language/framework stack",
    "ARCHITECTURE_TYPE": "the project's architecture pattern",
}

WELL_FORMED = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def fail(message: str) -> NoReturn:
    sys.exit(f"render-standards: {message}")


def source_paths(root: Path) -> list[Path]:
    standards = root / "standards"
    if not standards.is_dir():
        fail(f"{standards}: not a directory")
    paths = sorted(p for p in standards.glob("*.md") if p.name != "README.md")
    if not paths:
        fail(f"no sources match {standards}/*.md")
    return paths


def integrity_problems(path: Path, root: Path) -> list[str]:
    """Placeholder-integrity findings for one source file."""
    at = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    problems = []
    known = ", ".join("{{" + name + "}}" for name in sorted(PLACEHOLDERS))
    for token in dict.fromkeys(WELL_FORMED.findall(text)):
        if token not in PLACEHOLDERS:
            problems.append(
                f'{at}: unknown placeholder "{{{{{token}}}}}" (registered: {known})'
            )
    # With well-formed occurrences removed, any surviving double brace is
    # malformed syntax: an unclosed `{{TOKEN}`, a lowercase token, etc.
    stripped = WELL_FORMED.sub("", text)
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        if "{{" in line or "}}" in line:
            problems.append(
                f"{at}:{lineno}: malformed double-brace placeholder syntax"
            )
    return problems


def check(root: Path) -> int:
    problems = []
    for path in source_paths(root):
        problems += integrity_problems(path, root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"standards: {len(problems)} placeholder problem(s)", file=sys.stderr)
        return 1
    # Prove a full render resolves everything: substitute sample values and
    # assert no residue. Guards the check itself against regex drift.
    sample = {name: f"<{name}>" for name in PLACEHOLDERS}
    for path in source_paths(root):
        rendered = substitute(path.read_text(encoding="utf-8"), sample)
        if "{{" in rendered or "}}" in rendered:
            fail(f"{path.relative_to(root).as_posix()}: unresolved placeholder after render")
    print(f"standards: {len(source_paths(root))} source(s) clean")
    return 0


def load_config(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"{path}: {error.strerror or error}")
    except json.JSONDecodeError as error:
        fail(f"{path}: invalid JSON — {error}")
    if not isinstance(raw, dict):
        fail(f"{path}: config must be a JSON object of placeholder → value")
    known = ", ".join(sorted(PLACEHOLDERS))
    for key, value in raw.items():
        if key not in PLACEHOLDERS:
            fail(f'{path}: unknown placeholder "{key}" (registered: {known})')
        if not isinstance(value, str) or not value.strip():
            fail(f'{path}: "{key}" must be a non-empty string')
    return {key: value.strip() for key, value in raw.items()}


def substitute(text: str, values: dict[str, str]) -> str:
    return WELL_FORMED.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def render(root: Path, config: dict[str, str], out: Path, only: list[str] | None) -> int:
    paths = source_paths(root)
    if only is not None:
        by_name = {p.stem: p for p in paths}
        missing = sorted(set(only) - set(by_name))
        if missing:
            available = ", ".join(sorted(by_name))
            fail(f"unknown standard(s): {', '.join(missing)} (available: {available})")
        paths = [by_name[name] for name in sorted(set(only))]

    problems = []
    for path in paths:
        problems += integrity_problems(path, root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        fail("sources failed placeholder integrity; not rendering")

    needed = {
        token
        for path in paths
        for token in WELL_FORMED.findall(path.read_text(encoding="utf-8"))
    }
    unsupplied = sorted(needed - set(config))
    if unsupplied:
        fail(f"config missing value(s) for: {', '.join(unsupplied)}")

    out.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = out / path.name
        target.write_text(
            substitute(path.read_text(encoding="utf-8"), config), encoding="utf-8"
        )
        print(f"rendered {target}")
    print(f"standards: {len(paths)} file(s) rendered to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate placeholder integrity of every source instead of rendering",
    )
    parser.add_argument("--config", type=Path, help="JSON file of placeholder → value")
    parser.add_argument("--out", type=Path, help="directory to write rendered files to")
    parser.add_argument(
        "--only",
        help="comma-separated standard names to render (default: all)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repository root to operate on (default: this script's repository)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.check:
        if args.config or args.out or args.only:
            fail("--check takes no --config/--out/--only")
        return check(root)
    if not args.config or not args.out:
        fail("rendering needs --config and --out (or use --check)")
    only = None
    if args.only is not None:
        only = [name.strip() for name in args.only.split(",")]
        if "" in only:
            fail("--only contains an empty standard name (check for stray commas)")
    return render(root, load_config(args.config), args.out.resolve(), only)


if __name__ == "__main__":
    sys.exit(main())
