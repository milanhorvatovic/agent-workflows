"""Command-line surface: `python3 -m driver <run|resume|status> --config <path>`,
with `resume` also naming the run to resume.

Exit codes: 0 success, 1 the command cannot run yet (its module has not
landed), 2 bad usage or a defective config or environment.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path, PureWindowsPath

from .config import Config, ConfigError, load_config


def _run_id(value: str) -> str:
    # Path safety only, not id-format validation — the run id joins under
    # {artifacts}/runs/, so NUL, separators, dot entries, absolute paths,
    # and Windows drive prefixes would break or escape it. Drive prefixes
    # are detected with PureWindowsPath rather than by rejecting every
    # colon, which would refuse POSIX-legal ids such as ISO timestamps.
    # What a well-formed id looks like is the run-state schema's business,
    # enforced where run state is read, not here.
    if (
        not value.strip()
        or value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or PureWindowsPath(value).drive
        or Path(value).is_absolute()
    ):
        raise argparse.ArgumentTypeError(f"not a run id: {value!r}")
    return value


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
        type=_run_id,
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
    # No probes: pathlib's probe methods (exists, is_dir) suppress
    # filesystem errors, so an unreadable path would read as absent and an
    # unclassifiable child would be silently dropped — zero runs as the
    # wrong answer either way. os.scandir opens the directory directly,
    # and only absence at that open means zero runs (the first run creates
    # the directory) — and true absence only: a dangling runs symlink
    # raises the same error and is a defect, not an empty state. Every
    # later failure is a defect too — exit 1 is reserved for unimplemented
    # commands, so defects land in 2 rather than escaping as tracebacks or
    # hiding as empty output.
    try:
        scan = os.scandir(config.runs_dir)
    except FileNotFoundError:
        if config.runs_dir.is_symlink():
            print(f"driver: {config.runs_dir} is a dangling symlink", file=sys.stderr)
            return 2
        return 0
    except NotADirectoryError:
        print(f"driver: {config.runs_dir} is not a directory", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    # follow_symlinks=False: a symlink is never a run — following one
    # would present an external directory as a run under {artifacts}/runs/
    # and let a later resume escape the artifact root past the run-id
    # guard. A child that cannot be classified — vanished mid-scan
    # included, hence no FileNotFoundError carve-out here — is a defect.
    try:
        with scan:
            run_ids = sorted(
                entry.name for entry in scan if entry.is_dir(follow_symlinks=False)
            )
    except OSError as error:
        print(f"driver: cannot read {config.runs_dir}: {error}", file=sys.stderr)
        return 2
    for run_id in run_ids:
        print(run_id)
    return 0
