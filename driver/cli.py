"""Command-line surface: `python3 -m driver <run|resume|status> --config <path>`.

Exit codes: 0 success, 1 the command cannot run yet (its module has not
landed), 2 bad usage or a config defect.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, ConfigError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="driver",
        description="Reference driver for the agent-workflows protocol.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("run", "start a new run"),
        ("resume", "resume a run from its first unfinished step"),
        ("status", "list the runs in the configured runs directory"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "--config",
            type=Path,
            required=True,
            help="path to the driver config (JSON)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        config = load_config(arguments.config)
    except ConfigError as error:
        print(f"driver: {arguments.config}: {error}", file=sys.stderr)
        return 2
    if arguments.command == "status":
        return _status(config)
    # run and resume need the state machine, which has not landed; the
    # commands exist now so the surface consumers script against is stable
    # while the driver's modules arrive one PR at a time.
    print(
        f"driver: {arguments.command} is not implemented yet — "
        "the state machine module has not landed",
        file=sys.stderr,
    )
    return 1


def _status(config: Config) -> int:
    """Print one run id (directory name) per line, sorted."""
    # A missing runs directory is zero runs, not a defect: the first run
    # creates it. An existing non-directory is a defect — reporting zero
    # runs for it would hide the misconfiguration.
    if not config.runs_dir.exists():
        return 0
    if not config.runs_dir.is_dir():
        print(f"driver: {config.runs_dir} is not a directory", file=sys.stderr)
        return 2
    for entry in sorted(config.runs_dir.iterdir()):
        if entry.is_dir():
            print(entry.name)
    return 0
