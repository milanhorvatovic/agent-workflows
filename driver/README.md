# driver/

Python reference driver (stdlib only): state machine, context assembly, pluggable invocation backends, loop-contract evaluation, gate handling. The guaranteed execution floor — a human or a capable harness can substitute at any step.

## Usage

Nothing to install: clone the repository and run the package from its root with any Python 3.10+.

```sh
python3 -m driver status --config path/to/driver.json
```

Three commands, each taking `--config`; `run` names the workflow and the new run's id, and `resume` names the run to resume, since the protocol permits concurrent runs and the choice can never be inferred:

| Command | Does |
| --- | --- |
| `run --workflow <name> <run-id>` | create the run — its directory under `{artifacts}/runs/` and the bootstrap state the spec's §10 prescribes, the entry stage's records alone — and resolve its first step. The id is caller-chosen and a plain name only: separators, dot entries, and absolute paths are rejected, and an existing run is refused rather than shared. |
| `resume <run-id>` | resolve that run's position per spec §8.5 — the active record first, else the first record neither done nor skipped — its id a plain name like `run`'s, naming a real directory rather than a link, and holding state that names the same run |
| `status` | list the runs under the configured artifact root |

The driver is built module by module, and the command surface is stable from the start: `status` works whole, and `run` and `resume` do their state-machine half — create, resolve, report — then exit with an explicit message (code 1) at the point executing a step would begin, which needs the context assembler and an invocation backend still to land. The created run is durable: the later modules pick up exactly where these commands stop. Exit codes: 0 success (a finished run resumes to "nothing left to run"), 1 the command cannot go further yet, 2 bad usage or a defective config, environment, or state file (an unreadable or non-directory runs path included, and a dangling link — symlink or NTFS junction — anywhere on the way to it). A link under the runs directory is never listed as a run and never resumed — following one would present an external directory as a run and read, then later write, state outside the artifact root — nor is a state file that names a different run than the directory holding it, since the id is the run's identity (§8.1) and the two disagreeing means one of them is wrong about where the run's artifacts live. A run directory whose name cannot be carried on one output line is reported rather than printed. Every declaration the driver reads states the protocol version it was authored against (§9), and one from a version this driver does not implement — a different major, or a newer minor, since `0.x` minors may break — is reported rather than interpreted (§11).

## Configuration

One JSON file, passed via `--config`. [`config.example.json`](config.example.json) is a complete example. Validation is strict and happens at load time — unknown keys, undefined backend references, and missing role routes fail before anything runs.

| Field | Meaning |
| --- | --- |
| `artifacts_dir` | The consuming project's artifact root — `{artifacts}` in [the protocol spec](../protocol/spec.md#8-artifacts-and-runs), which names resolving it as project configuration. Optional, default `.`; a relative path anchors at the config file's directory, so artifacts land in the consuming project no matter where the driver is invoked from, and a leading `~` expands to the home directory. Runs live at `{artifacts}/runs/<run-id>/` — the `runs` segment is the spec's, so the driver derives it rather than taking it as configuration. |
| `framework_dir` | Where the protocol content lives — the directory holding `workflows/` and `workflows/stages/`, which `run` composes the workflow from. Optional, default `.`, resolved by exactly the rules `artifacts_dir` follows: relative paths anchor at the config file's directory, `~` expands, partially anchored Windows forms are rejected. |
| `backends` | Named harness command lines — for each, `command` is the argv of any CLI that accepts a prompt and returns text (`["claude", "-p"]`, `["codex", "exec"]`, …). How the prompt reaches the command is the invocation backend's concern and lands with that module. |
| `roles` | One route per protocol role — all six (`analyst`, `planner`, `implementer`, `reviewer`, `validator`, `arbiter`) are required, since which of them a run needs is decided at intake, after config load. Each names a configured `backend` and optionally a `model`; the model is validated and carried now, consumed once per-step model routing lands in a later release. |

## Tests

From the repository root:

```sh
python3 -m unittest discover -s driver -t .
```
