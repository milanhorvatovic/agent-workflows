"""Command-line surface: `python3 -m driver <run|resume|status> --config <path>`,
with `resume` also naming the run to resume.

Exit codes: 0 success, 1 the command cannot run yet (its module has not
landed), 2 bad usage or a defective config or environment.
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
    run = subparsers.add_parser("run", help="start a new run")
    resume = subparsers.add_parser("resume", help="resume a run from its first unfinished step")
    # The protocol permits concurrent runs (spec §8.1), so which run to
    # resume can never be inferred; the id is part of the contract even
    # while the command itself awaits the state machine.
    resume.add_argument(
        "run_id",
        help="the run to resume: its directory name under {artifacts}/runs/",
    )
    status = subparsers.add_parser("status", help="list the runs under the configured artifact root")
    for command in (run, resume, status):
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
    # No exists() probe: pathlib's probe methods suppress filesystem
    # errors, so an unreadable path would read as absent and be reported
    # as zero runs. Iterating directly distinguishes the cases — absence
    # is zero runs (the first run creates the directory), while a
    # non-directory or any other filesystem failure is a defect: exit 1
    # is reserved for unimplemented commands, so these land in 2 rather
    # than escaping as tracebacks or hiding as empty output.
    try:
        run_ids = sorted(entry.name for entry in config.runs_dir.iterdir() if entry.is_dir())
    except FileNotFoundError:
        return 0
    except NotADirectoryError:
        print(f"driver: {config.runs_dir} is not a directory", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    for run_id in run_ids:
        print(run_id)
    return 0
