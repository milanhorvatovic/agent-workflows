# driver/

Python reference driver (stdlib only): state machine, context assembly, pluggable invocation backends, loop-contract evaluation, gate handling. The guaranteed execution floor — a human or a capable harness can substitute at any step.

## Usage

Nothing to install: clone the repository and run the package from its root with any Python 3.10+.

```sh
python3 -m driver status --config path/to/driver.json
```

Three commands, each taking `--config`; `resume` additionally names the run to resume, since the protocol permits concurrent runs and the choice can never be inferred:

| Command | Does |
| --- | --- |
| `run` | start a new run |
| `resume <run-id>` | resume that run — its directory name under `{artifacts}/runs/`, a plain name only: separators, dot entries, and absolute paths are rejected — from its first unfinished step |
| `status` | list the runs under the configured artifact root |

The driver is built module by module, and the command surface is stable from the start: `status` works today; `run` and `resume` exit with an explicit message (code 1) until the state machine module lands. Exit codes: 0 success, 1 the command cannot run yet, 2 bad usage or a defective config or environment (an unreadable or non-directory runs path included, and a dangling link — symlink or NTFS junction — anywhere on the way to it). A link under the runs directory is never listed as a run — following one would present an external directory as a run and let a later `resume` escape the artifact root — and a run directory whose name cannot be carried on one output line is reported rather than printed.

## Configuration

One JSON file, passed via `--config`. [`config.example.json`](config.example.json) is a complete example. Validation is strict and happens at load time — unknown keys, undefined backend references, and missing role routes fail before anything runs.

| Field | Meaning |
| --- | --- |
| `artifacts_dir` | The consuming project's artifact root — `{artifacts}` in [the protocol spec](../protocol/spec.md#8-artifacts-and-runs), which names resolving it as project configuration. Optional, default `.`; a relative path anchors at the config file's directory, so artifacts land in the consuming project no matter where the driver is invoked from, and a leading `~` expands to the home directory. Runs live at `{artifacts}/runs/<run-id>/` — the `runs` segment is the spec's, so the driver derives it rather than taking it as configuration. |
| `backends` | Named harness command lines — for each, `command` is the argv of any CLI that accepts a prompt and returns text (`["claude", "-p"]`, `["codex", "exec"]`, …). How the prompt reaches the command is the invocation backend's concern and lands with that module. |
| `roles` | One route per protocol role — all six (`analyst`, `planner`, `implementer`, `reviewer`, `validator`, `arbiter`) are required, since which of them a run needs is decided at intake, after config load. Each names a configured `backend` and optionally a `model`; the model is validated and carried now, consumed once per-step model routing lands in a later release. |

## Tests

From the repository root:

```sh
python3 -m unittest discover -s driver -t .
```
