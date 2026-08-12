#!/usr/bin/env python3
"""Install the framework into a consuming project.

Copies every skill package from skills/ into the project's .agents/skills/
(the canonical cross-client path) and renders the project's standards from
the standards/ single source into .agents/standards/ per the consumer's
answers — collected at the prompt, or supplied as a JSON config for
non-interactive/CI onboarding.

Re-runs are idempotent and never silently overwrite: an install manifest
(.agents/awf-install-manifest.json) records every installed path with a
content digest and the framework source tag, so a re-run refreshes what it
installed and the consumer left unmodified, and reports — without touching —
what the consumer changed or what setup never installed.

Usage:
    python3 setup/init.py --target /path/to/project
        # interactive: answers collected at the prompt
    python3 setup/init.py --target /path/to/project --config setup.json
        # non-interactive: answers supplied as JSON
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NoReturn

# Repository scripts are plain files, not a package; the path entry makes the
# placeholder vocabulary and rendering machinery in scripts/ importable here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_standards  # noqa: E402

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

SKILLS_DIR = ".agents/skills"
STANDARDS_DIR = ".agents/standards"
MANIFEST_PATH = ".agents/awf-install-manifest.json"
MANIFEST_VERSION = 1

# The only digest form setup ever writes; anything else in a manifest is
# corruption, and without this check it would present forever as a
# "locally modified" install instead of as the manifest problem it is.
DIGEST_FORM = re.compile(r"sha256:[0-9a-f]{64}")

# Artifact-format families: a project picks at most one variant per family,
# while every standard outside these families always renders. A stem in
# standards/ encodes its family as the prefix before the first dash.
FORMAT_FAMILIES = ("commit", "pr", "ticket")
NO_VARIANT = "none"

# Junk the copy and the digest both skip, so checkouts on different platforms
# agree about what an installed directory contains.
IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def fail(message: str) -> NoReturn:
    sys.exit(f"setup: {message}")


@dataclass(frozen=True)
class Selection:
    """The consumer's answers: placeholder values plus one chosen variant per
    format family (families left out render nothing)."""

    placeholders: dict[str, str]
    formats: dict[str, str]


@dataclass(frozen=True)
class Item:
    """One installable unit: a skill directory or a rendered standard file."""

    kind: str
    name: str
    source: Path
    target_rel: str


def discover_standards(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Split the standards/ stems into the always-rendered set and the
    per-family variant choices."""
    stems = [path.stem for path in render_standards.source_paths(root)]
    prefixes = tuple(f"{family}-" for family in FORMAT_FAMILIES)
    always = sorted(stem for stem in stems if not stem.startswith(prefixes))
    variants = {
        family: sorted(
            stem[len(family) + 1 :]
            for stem in stems
            if stem.startswith(f"{family}-")
        )
        for family in FORMAT_FAMILIES
    }
    return always, variants


def load_setup_config(path: Path, variants: dict[str, list[str]]) -> Selection:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"{path}: {error.strerror or error}")
    except json.JSONDecodeError as error:
        fail(f"{path}: invalid JSON — {error}")
    if not isinstance(raw, dict):
        fail(f"{path}: config must be a JSON object")
    known = {"placeholders", *(f"{family}_format" for family in FORMAT_FAMILIES)}
    unknown = sorted(set(raw) - known)
    if unknown:
        fail(
            f"{path}: unknown key(s): {', '.join(unknown)} "
            f"(known: {', '.join(sorted(known))})"
        )
    if "placeholders" not in raw:
        fail(f'{path}: missing "placeholders" object')
    placeholders = render_standards.validate_config(
        raw["placeholders"], f"{path}: placeholders"
    )
    formats = {}
    for family in FORMAT_FAMILIES:
        value = raw.get(f"{family}_format", NO_VARIANT)
        if not isinstance(value, str):
            fail(f'{path}: "{family}_format" must be a string')
        if value == NO_VARIANT:
            continue
        if value not in variants[family]:
            available = ", ".join(variants[family]) or "(none shipped)"
            fail(
                f'{path}: unknown {family} format "{value}" '
                f"(available: {available}, or {NO_VARIANT})"
            )
        formats[family] = value
    return Selection(placeholders, formats)


def interview(
    variants: dict[str, list[str]], default_project: str, ask: Callable[[str], str]
) -> Selection:
    placeholders = {}
    # The vocabulary's own order puts PROJECT_NAME — the one answer with a
    # default — first, which is also the natural interview order.
    for name, meaning in render_standards.PLACEHOLDERS.items():
        default = default_project if name == "PROJECT_NAME" else ""
        suffix = f" [{default}]" if default else ""
        answer = ""
        while not answer:
            answer = ask(f"{name} — {meaning}{suffix}: ").strip() or default
        placeholders[name] = answer
    formats = {}
    for family in FORMAT_FAMILIES:
        options = variants[family]
        if not options:
            continue
        prompt = f"{family} format ({', '.join(options)}) [{NO_VARIANT}]: "
        while True:
            answer = ask(prompt).strip() or NO_VARIANT
            if answer == NO_VARIANT or answer in options:
                break
        if answer != NO_VARIANT:
            formats[family] = answer
    return Selection(placeholders, formats)


def replay_config(selection: Selection) -> str:
    """The JSON that repeats an interactive run non-interactively."""
    raw: dict[str, object] = {"placeholders": selection.placeholders}
    for family, variant in selection.formats.items():
        raw[f"{family}_format"] = variant
    return json.dumps(raw, indent=2)


def resolve_source_tag(root: Path, override: str | None) -> str:
    if override:
        return override
    # A vendored copy can sit inside some other project's git repository, and
    # describing that repository would record the wrong provenance — so git is
    # asked only when the framework root is itself a checkout.
    if (root / ".git").exists():
        try:
            described = subprocess.run(
                ["git", "-C", str(root), "describe", "--tags", "--always", "--dirty"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            described = ""
        if described:
            return described
    changelog = root / "CHANGELOG.md"
    # The same stance as every other source read: never through a link.
    if changelog.is_symlink():
        fail(f"{changelog}: the source ships a symlink — refusing to read through it")
    if changelog.is_file():
        for line in changelog.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^## \[(\d+\.\d+\.\d+)\]", line)
            if match:
                return match.group(1)
    return "unknown"


def content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    # The kind seeds the hash: an empty file and an empty directory would
    # otherwise digest identically, letting the identical-content branches
    # treat a directory at a file's path as that file.
    if path.is_file():
        digest.update(b"file\0")
        digest.update(path.read_bytes())
    else:
        digest.update(b"tree\0")
        # Every entry kind carries its own marker, and variable-length
        # payloads are length-prefixed so the stream is self-delimiting —
        # file bytes embedding the serialization cannot forge another tree.
        # Directories are hashed too (a tree digested by files alone reads a
        # copy with an extra empty directory as identical), and a symlink is
        # hashed as its target string rather than followed, so a file the
        # consumer replaced with an equivalent link still reads as modified
        # instead of being refreshed over.
        for entry in sorted(path.rglob("*")):
            relative = entry.relative_to(path)
            if IGNORED_NAMES & set(relative.parts):
                continue
            name = relative.as_posix().encode("utf-8")
            if entry.is_symlink():
                link = os.readlink(entry).encode("utf-8", "surrogateescape")
                digest.update(b"l\0" + name + b"\0")
                digest.update(str(len(link)).encode("ascii") + b"\0" + link)
            elif entry.is_dir():
                digest.update(b"d\0" + name + b"\0")
            elif entry.is_file():
                payload = entry.read_bytes()
                digest.update(b"f\0" + name + b"\0")
                digest.update(str(len(payload)).encode("ascii") + b"\0" + payload)
    return f"sha256:{digest.hexdigest()}"


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    # Checked without following links: a directory or symlink here would read
    # as an absent manifest, and the run would proceed unowned only to fail
    # late — or replace the foreign link — when the manifest is saved.
    if path.is_symlink() or (path.exists() and not path.is_file()):
        fail(f"{path}: not a regular file — refusing to treat it as the install manifest")
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"{path}: {error.strerror or error}")
    except json.JSONDecodeError as error:
        fail(f"{path}: invalid JSON — {error}")
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
        fail(f"{path}: not an install manifest")
    if raw.get("manifest_version") != MANIFEST_VERSION:
        fail(
            f"{path}: manifest_version {raw.get('manifest_version')!r} is not "
            f"{MANIFEST_VERSION} — written by an incompatible setup version"
        )
    for rel, entry in raw["entries"].items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("source_tag"), str)
            or not isinstance(entry.get("digest"), str)
            or not DIGEST_FORM.fullmatch(entry["digest"])
        ):
            fail(f"{path}: entry {rel!r} is not an install record")
    return raw["entries"]


def save_manifest(path: Path, entries: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "entries": {rel: entries[rel] for rel in sorted(entries)},
    }
    # Written beside the manifest and swapped in atomically: an in-place
    # truncate interrupted mid-write would corrupt the one file every re-run
    # needs to recover ownership state.
    descriptor, staged = tempfile.mkstemp(dir=path.parent, prefix=path.name)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")
    os.replace(staged, path)


def guard_source_tree(root: Path) -> None:
    """Refuse a source that ships a symlink, before anything is read or
    written: the digest records links as links while the staging copy would
    dereference them, so an installed tree would immediately read as locally
    modified — and installing links into a consumer project is not a promise
    setup makes. Checked at the containers, the packages, the standards
    sources, and every descendant, because a link at the top levels is
    invisible to a per-item walk and rendering would launder a linked
    standard into a regular temporary file before any later guard saw it.
    No skill ships one; if one ever does, this makes it a decision."""
    for container in ("skills", "standards"):
        base = root / container
        if base.is_symlink():
            fail(f"{base}: the source ships a symlink — setup installs none")
        if not base.is_dir():
            continue
        for entry in base.rglob("*"):
            if entry.is_symlink():
                fail(f"{entry}: the source ships a symlink — setup installs none")


def guard_managed_paths(target: Path) -> None:
    """Refuse to install through a symlinked managed directory: a link
    pointing outside the project would carry writes — including refreshes of
    manifest-owned content — past the --target boundary, which matters most in
    the non-interactive/CI mode where the repository contents are the input."""
    for rel in (".agents", SKILLS_DIR, STANDARDS_DIR):
        path = target / rel
        if path.is_symlink():
            fail(f"{path}: managed path is a symlink — refusing to install through it")
        # A regular file here would fail deep inside the run, after items
        # were already promoted, with no manifest written.
        if path.exists() and not path.is_dir():
            fail(f"{path}: managed path is not a directory")


def skill_items(root: Path) -> list[Item]:
    skills = root / "skills"
    directories = (
        sorted(p for p in skills.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
        if skills.is_dir()
        else []
    )
    if not directories:
        fail(f"no skill packages under {skills} — is --root a framework checkout?")
    return [
        Item("skill", path.name, path, f"{SKILLS_DIR}/{path.name}")
        for path in directories
    ]


def render_selected(
    root: Path, always: list[str], selection: Selection, out: Path
) -> list[Item]:
    names = always + [
        f"{family}-{variant}" for family, variant in selection.formats.items()
    ]
    # render() narrates every file it writes; those paths name a temporary
    # directory here, so the narration is suppressed and this installer's own
    # report speaks for each standard instead. Failures still exit loudly.
    with contextlib.redirect_stdout(io.StringIO()):
        render_standards.render(root, selection.placeholders, out, sorted(names))
    return [
        Item("standard", path.name, path, f"{STANDARDS_DIR}/{path.name}")
        for path in sorted(out.glob("*.md"))
    ]


def write_item(item: Item, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Staged beside the destination (same filesystem, so every rename is
    # atomic) and renamed into place only after the copy completed: a run that
    # dies mid-copy must not leave a half-written install at the real name,
    # which later runs would permanently skip as foreign. A refresh swaps the
    # old content aside by rename rather than deleting it in place — a
    # recursive delete interrupted midway would leave a partial destination in
    # the same permanently-skipped state — restores it if promotion fails, and
    # otherwise lets the staging cleanup take it; a crash between the two
    # renames leaves the destination absent, which the next run reinstalls.
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        staged = Path(staging) / item.name
        if item.source.is_dir():
            shutil.copytree(
                item.source, staged, ignore=shutil.ignore_patterns(*IGNORED_NAMES)
            )
        else:
            staged.write_bytes(item.source.read_bytes())
        replaced = Path(staging) / "replaced"
        if destination.exists():
            destination.rename(replaced)
        try:
            staged.rename(destination)
        except OSError:
            if replaced.exists():
                replaced.rename(destination)
            raise


def apply(
    items: list[Item],
    target: Path,
    entries: dict[str, dict[str, str]],
    source_tag: str,
) -> tuple[list[str], Counter[str]]:
    report = []
    outcomes: Counter[str] = Counter()
    for item in items:
        destination = target / item.target_rel
        # A following exists() reads a dangling symlink as absence, and the
        # promotion rename would then replace the foreign link in place.
        if destination.is_symlink():
            outcomes["skipped"] += 1
            report.append(
                f"{item.kind} {item.name}: skipped — a symlink sits at this "
                "path and setup never writes through links; left untouched"
            )
            continue
        desired = content_digest(item.source)
        current = content_digest(destination) if destination.exists() else None
        entry = entries.get(item.target_rel)
        detail = ""
        if current is None:
            write_item(item, destination)
            entries[item.target_rel] = {"source_tag": source_tag, "digest": desired}
            outcome = "installed"
        elif current == desired:
            if entry is None:
                entries[item.target_rel] = {"source_tag": source_tag, "digest": desired}
                outcome = "adopted"
                detail = "already identical to this source; recorded in the manifest"
            else:
                # A matching entry keeps its install-time tag, so a re-run is
                # byte-idempotent even when only the source's tag moved. A
                # differing one is re-recorded: a run interrupted between a
                # refresh and the manifest save leaves exactly this state, and
                # keeping the stale digest would misread the unmodified
                # install as locally modified on the next source change.
                # Content byte-identical to the source is the source's by the
                # same rule adoption applies, whichever hand wrote it —
                # ownership here is content-addressed, deliberately.
                if entry.get("digest") != desired:
                    entries[item.target_rel] = {
                        "source_tag": source_tag,
                        "digest": desired,
                    }
                outcome = "up to date"
        elif entry is None:
            outcome = "skipped"
            detail = "exists but was not installed by setup; left untouched"
        elif current == entry.get("digest"):
            write_item(item, destination)
            entries[item.target_rel] = {"source_tag": source_tag, "digest": desired}
            outcome = "refreshed"
        else:
            outcome = "skipped"
            detail = (
                "locally modified since install; left untouched "
                "(remove it and re-run to reinstall)"
            )
        outcomes[outcome] += 1
        suffix = f" — {detail}" if detail else ""
        report.append(f"{item.kind} {item.name}: {outcome}{suffix}")
    return report, outcomes


def stale_entries(
    items: list[Item],
    target: Path,
    entries: dict[str, dict[str, str]],
    source_stems: set[str],
) -> list[str]:
    """Manifest entries this run did not plan: report the ones still on disk,
    drop the ones the consumer already removed."""
    report = []
    planned = {item.target_rel for item in items}
    for rel in sorted(set(entries) - planned):
        occupant = target / rel
        # A dangling symlink still occupies the path; only true absence drops
        # the record — everything else stays recorded and reported.
        if not occupant.exists() and not occupant.is_symlink():
            del entries[rel]
            continue
        if rel.startswith(f"{STANDARDS_DIR}/") and Path(rel).stem in source_stems:
            reason = "not selected by this run"
        else:
            reason = "no longer shipped by this source"
        kind = "skill" if rel.startswith(f"{SKILLS_DIR}/") else "standard"
        report.append(
            f"{kind} {Path(rel).name}: stale — installed by an earlier run but "
            f"{reason}; remove manually if unwanted"
        )
    return report


def main(argv: list[str] | None = None, ask: Callable[[str], str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="consuming project directory to install into",
    )
    parser.add_argument(
        "--config", type=Path, help="JSON answers for non-interactive setup"
    )
    parser.add_argument(
        "--source-tag",
        help="provenance tag recorded in the manifest (default: git describe, "
        "then the CHANGELOG's latest release, then unknown)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="framework repository root to install from (default: this script's repository)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    target = args.target.resolve()
    if target.exists() and not target.is_dir():
        fail(f"{target}: not a directory")
    # A target under the framework root would put the staging directory
    # inside a directory being copied, which copies its own output until
    # the disk fills; installing into the framework checkout is never right.
    if target == root or root in target.parents:
        fail(f"{target}: target is inside the framework repository at {root}")
    # A tree that ships its own installer is installed by that installer, so
    # the renderer and placeholder vocabulary always match the standards they
    # render; --root stays for trees that carry only the data.
    if root != DEFAULT_ROOT and (root / "setup" / "init.py").is_file():
        fail(
            f"{root}: ships its own installer — run its setup/init.py instead, "
            "so its renderer matches its standards"
        )
    guard_managed_paths(target)
    guard_source_tree(root)

    always, variants = discover_standards(root)
    interactive = args.config is None
    if interactive:
        if ask is None:
            if not sys.stdin.isatty():
                fail("no terminal to ask on — pass --config for non-interactive setup")
            ask = input
        selection = interview(variants, target.name, ask)
    else:
        selection = load_setup_config(args.config, variants)

    source_tag = resolve_source_tag(root, args.source_tag)
    manifest_path = target / MANIFEST_PATH
    entries = load_manifest(manifest_path)
    loaded = {rel: dict(entry) for rel, entry in entries.items()}

    with tempfile.TemporaryDirectory() as tmp:
        items = skill_items(root) + render_selected(
            root, always, selection, Path(tmp) / "standards"
        )
        report, outcomes = apply(items, target, entries, source_tag)

    source_stems = set(always)
    for family, names in variants.items():
        source_stems.update(f"{family}-{name}" for name in names)
    stale = stale_entries(items, target, entries, source_stems)
    # Saved only on change: a no-op re-run must not touch the manifest's
    # bytes, inode, or mtime — "changes nothing" means nothing.
    if entries != loaded or not manifest_path.is_file():
        save_manifest(manifest_path, entries)

    for line in report + stale:
        print(line)
    print(
        f"setup: {outcomes['installed']} installed, {outcomes['refreshed']} refreshed, "
        f"{outcomes['up to date']} up to date, {outcomes['adopted']} adopted, "
        f"{outcomes['skipped']} skipped, {len(stale)} stale — {target} "
        f"(source tag {source_tag})"
    )
    if interactive:
        print(
            "\nTo repeat this setup non-interactively, save this as setup.json "
            "and pass --config setup.json:\n" + replay_config(selection)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
