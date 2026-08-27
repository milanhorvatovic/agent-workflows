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
| `run --workflow <name> <run-id>` | create the run — its directory under `{artifacts}/runs/` and the bootstrap state the spec's §10 prescribes, the entry stage's records alone — resolve its first step, and assemble the context that step would execute from. The id is caller-chosen and a plain name only: separators, dot entries, and absolute paths are rejected, and an existing run is refused rather than shared. |
| `resume <run-id>` | resolve that run's position per spec §8.5 — the active record first, else the first record neither done nor skipped — its id a plain name like `run`'s, naming a real directory rather than a link, and holding state that names the same run, then assemble that position's context as `run` does |
| `status` | list the runs under the configured artifact root |

The driver is built module by module, and the command surface is stable from the start: `status` works fully, and `run` and `resume` go as far as a run can go without an agent to send anything to — create, resolve, assemble — then exit with an explicit message (code 1) at the point invocation would begin, which needs an invocation backend still to land. Assembling is what says the position is runnable rather than merely next: a required input the run has not produced blocks the step (§9.1), and that is reported as the position it is, at the same exit code, rather than as a defect. Nothing is written by it — the scaffold §8.3 asks for belongs to the invocation that fills it. The created run is durable — how firmly is a platform property, stated with the containment one below — and the later modules pick up exactly where these commands stop. Exit codes: 0 success (a finished run resumes to "nothing left to run"), 1 the command cannot go further yet, 2 bad usage or a defective config, environment, state file, or framework (an unreadable or non-directory runs path included, a dangling link — symlink or NTFS junction — anywhere on the way to it, and a skill whose declared contract disagrees with the stage composing it). A link under the runs directory is never listed as a run and never resumed — following one would present an external directory as a run and read, then later write, state outside the artifact root — nor is a state file that names a different run than the directory holding it, since the id is the run's identity (§8.1) and the disagreement means one of them is wrong about where the run's artifacts live. A run directory whose name cannot be carried on one output line is reported rather than printed, and the configured roots are held to the same rule, since `run` prints the directory it created.

How firmly that containment holds is a platform property, and worth stating rather than implying. Where the operating system can bind a file operation to a directory already open — POSIX, through `dir_fd` — the runs directory and the run inside it are opened once, refusing a link at the open itself, and every read and write names the state file relative to those descriptors, so no part of the path can be re-pointed after it was checked. Windows has no such binding in Python's standard library: there the same rules are enforced by checking, which closes the case a link is already in place and leaves a window between the check and the open. Narrowing that further needs handle-relative Win32 calls this driver does not reach for while it stays stdlib-only, and the exposure it leaves is bounded by who can already write inside the artifact root — anyone who can put a link there can equally rewrite the state files it contains. Durability divides the same way. Every write is one atomic replace of a temp file whose bytes have been synced, so no published name ever points at content that never landed; where the operating system can sync a directory — POSIX again — the entry that publishes it is synced too, in that order, and a power loss leaves the previous state or the next one and nothing between. Windows exposes no handle for a directory's own metadata through Python's standard library, so there the entry is persisted when the filesystem gets to it: a crash can lose the newest write, or a newly created run, after the command reporting it returned. Closing that needs the same write-through Win32 calls the containment gap does. Every declaration the driver reads states the protocol version it was authored against (§9), and one from a version this driver does not implement — a different major, or a newer minor, since `0.x` minors may break — is reported rather than interpreted (§11).

## Configuration

One JSON file, passed via `--config`. [`config.example.json`](config.example.json) is a complete example. Validation is strict and happens at load time — unknown keys, undefined backend references, and missing role routes fail before anything runs.

| Field | Meaning |
| --- | --- |
| `artifacts_dir` | The consuming project's artifact root — `{artifacts}` in [the protocol spec](../protocol/spec.md#8-artifacts-and-runs), which names resolving it as project configuration. Optional, default `.`; a relative path anchors at the config file's directory, so artifacts land in the consuming project no matter where the driver is invoked from, and a leading `~` expands to the home directory. Runs live at `{artifacts}/runs/<run-id>/` — the `runs` segment is the spec's, so the driver derives it rather than taking it as configuration. |
| `framework_dir` | Where the protocol content lives — a checkout of the framework, holding `workflows/` and `workflows/stages/`, which `run` composes the workflow from, and `roles/` and `skills/`, which a step's context is assembled from. Not the consuming project's `.agents/skills/`: those copies are for that project's harness to route to, and the driver executes from the framework it was configured with. Optional, default `.`, resolved by exactly the rules `artifacts_dir` follows: relative paths anchor at the config file's directory, `~` expands, partially anchored Windows forms are rejected. |
| `backends` | Named harness command lines — for each, `command` is the argv of any CLI that accepts a prompt and returns text (`["claude", "-p"]`, `["codex", "exec"]`, …). How the prompt reaches the command is the invocation backend's concern and lands with that module. |
| `roles` | One route per protocol role — all six (`analyst`, `planner`, `implementer`, `reviewer`, `validator`, `arbiter`) are required, since which of them a run needs is decided at intake, after config load. Each names a configured `backend` and optionally a `model`; the model is validated and carried now, consumed once per-step model routing lands in a later release. |

## Context assembly

What a step is given is assembled deterministically from declarations, never chosen: the role from the step's own contract (`roles/<role>.md`), the instructions from the skill bound to that step, the reference files from the ones that skill's body names, the material from the artifacts the contract declares as inputs, and the structure of the output from the template the contract names. The same run, step, and framework produce the same bytes.

A step-bound skill lives at `skills/awf-<step-id>/`, and the name is only how the pair is found — what makes it the binding is the `metadata.workflow.step` inside, which must agree with the stage's copy on role, inputs, output artifact, and edges (spec §9.1). A disagreement is refused rather than resolved: the stage composes the run and the skill is what the step executes from, so running one against the other means running prose written for inputs the step was never given. Conformance holds this repository's copies to that agreement; the driver holds the framework it was pointed at, which no CI has seen.

Input paths resolve per spec §8.1. `{N}` is the phase the step is executing and names one artifact. `{P}` is every phase *other* than this step's that the run's manifest records that artifact for — with which phase counts as the step's own settled by the step's own output, never by `run.phase`, since that field still names the last phase while the stages after it are running. The manifest is what defines both sets: an artifact sitting in the run directory that no step declared is working material (§8.2) and satisfies nothing. A required input the manifest does not name blocks the step; an optional one is simply absent. Satisfying an optional input from an earlier run is the spec §8.4 cache, which is judgment rather than resolution and lands with the artifact-manager work.

Scaffolding (§8.3) copies the declared template to the output path verbatim and refuses to overwrite. Both halves are the rule: a scaffolded artifact must carry every placeholder its template defines until the step fills it, so nothing is substituted by script, and a step revising, re-entering, or appending is given the artifact it already has — re-scaffolding would discard the content it was given to work from, a gate's recorded direction (§7) among it. The three shipped steps that declare no template — `risk-route`, `plan-revise`, `ideate-revise` — write artifacts an earlier step already scaffolded.

## Tests

From the repository root:

```sh
python3 -m unittest discover -s driver -t .
```
