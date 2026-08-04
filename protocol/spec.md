# Protocol Specification

**Protocol version:** `0.1` (pre-release — see [Versioning](#11-versioning))

This document is the normative surface of the agent-workflows protocol. The JSON Schemas in [`schemas/`](schemas/) normatively define the structures described in sections 9 and 10; this prose defines their semantics. The two MUST NOT diverge — a divergence is a defect in one of them, to be fixed rather than resolved by precedence.

## 1. Scope

The protocol structures how AI agents and humans collaborate on software work. It is a protocol, not a platform: there is no required SDK, runtime, or vendor. Three tiers divide the concerns:

- **Roles** define WHO acts: a bounded function with its own success criteria (see [Roles](#3-roles)).
- **Skills** define WHAT is done: task instructions packaged as Agent Skills-conformant directories, readable as plain prose by any agent.
- **Workflows** define HOW work flows: stages composed into sequences, with loop contracts and gates (see [Workflows and stages](#6-workflows-and-stages)).

State lives in markdown artifacts and one YAML run-state file, all in the repository. Any agent that can read a prompt can execute the protocol; any orchestration the protocol enables is carried as machine-readable hints that degrade to prose (see [Degradation](#94-degradation)).

## 2. Conformance language and terms

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119.

- **Executor** — whatever advances the loop: a human, a capable agent harness, or a driver program. The executor is not a role and holds no intelligence of its own.
- **Client** — software that reads protocol files (an executor, a validator, an editor plugin).
- **Run** — one execution of a workflow, with its own identifier, artifact directory, and run state.
- **Step** — the smallest unit of execution: one role applying one skill to declared inputs, producing a declared output.
- **Stage** — a named sub-workflow (steps, loop contracts, gates) that workflows compose.
- **Gate** — a point where a human decision is required or collected (see [Gates](#7-gates)).
- **Artifact** — a file produced or consumed by a step, addressed relative to the run directory.
- **Verdict** — a categorical validation outcome: `PASS`, `PASS_WITH_CONDITIONS`, or `FAIL`.
- **Brief** — the confirmed statement of intent produced by the `intake` stage.

## 3. Roles

### 3.1 The six roles

| Role | Function |
| --- | --- |
| `analyst` | Grounding: codebase analysis, requirement parsing |
| `planner` | Plans (high-level, detailed, bugfix) and their revisions |
| `implementer` | Code changes within the scope a plan declares |
| `reviewer` | Code, security, and performance review of implementations |
| `validator` | Artifact validation with categorical verdicts |
| `arbiter` | Synthesis between reviewers/validators and the planner: dedupes, triages, and resolves findings before they reach the planner; institutionalizes disagreement (refutation quota, devil's-advocate framing) to prevent false consensus |

### 3.2 Roles are not sessions

Roles are protocol semantics, not session requirements. The mapping of roles to agent sessions is an execution-mode decision made per risk class (see [Execution modes](#4-execution-modes)); a role definition MUST NOT demand a session arrangement, and a skill MUST NOT carry a per-skill isolation flag.

The executor is not a role. A run is advanced by whoever executes the loop, and a human or a capable harness MAY substitute for a driver at any step — the run state is the interface, not the executor's identity.

### 3.3 Verdicts

Validation steps produce exactly one verdict: `PASS`, `PASS_WITH_CONDITIONS`, or `FAIL`. Verdicts are step outputs and drive state-machine edges (see [Step and handoff](#91-step-and-handoff)); they are distinct from gate outcomes, which are human decisions (see [Gates](#7-gates)).

## 4. Execution modes

| Mode | Sessions | Default for |
| --- | --- | --- |
| `inline` | One session persona-switches through roles sequentially over the same artifacts | Risk classes R0, R1, R2 |
| `isolated` | Fresh context per role | Risk class R3 |

`inline` avoids reprocessing shared context; `isolated` buys independence at the cost of re-reading it. A run MAY escalate individual roles to fresh context regardless of mode.

**Review exception:** in `inline` mode, `reviewer` and `validator` steps MUST still run with fresh context (a subagent or new session). Fresh eyes are the point of those roles; a persona-switched review inherits the implementer's assumptions.

## 5. Risk classes

Every run is classified into exactly one of four risk classes at the `intake` stage. The class and a one-line rationale MUST be recorded in run state.

### 5.1 The four classes

|  | R0 exploratory | R1 trivial | R2 standard | R3 high |
| --- | --- | --- | --- | --- |
| **Typical work** | Spike, throwaway prototype, "what would it take" | Typo-class fix, config tweak, pattern-following small change | Ordinary feature or bugfix | Multi-phase, security-surface, irreversible, or architecturally novel work |
| **Mode** | `inline`, no role split | `inline`, implementer only | `inline` persona-switching, all roles | `isolated` per role |
| **Roles** | none (free agent) | `implementer` (+ machine checks) | `analyst` → `planner` → `implementer` → `reviewer` → `validator` | full set; `arbiter` mandatory |
| **Arbiter** | — | — | only on reviewer/validator disagreement | mandatory |
| **Gates** | none; exit note only | delivery gate, batched to inbox | plan approval **blocking**; others batched to inbox | all blocking by default (per-gate configuration allowed) |
| **Security review** | no | no | conditional: touches auth, crypto, input handling, or dependencies | mandatory |
| **Machine checks** | optional | required | required | required |
| **Artifacts** | scratch directory, discardable | minimal (change note) | full set, run-scoped | full set, run-scoped |

Machine checks are the project's own automated verification: tests, linters, builds.

### 5.2 Classification rubric

The classifying agent weighs these signals:

- **Blast radius** — files, modules, and public API surface touched.
- **Reversibility** — how cheaply the change can be undone.
- **Security surface** — auth, crypto, input handling, dependency changes.
- **Decomposability** — does the work want phases?
- **Novelty** — greenfield versus pattern-following.
- **Requirement ambiguity** — how confidently the brief can be restated.

Two rules constrain the rubric:

- Any security-surface signal MUST classify at least R2 and enable security review.
- Ambiguity above threshold MUST route back to the clarifying question (see [Intake](#62-intake)) rather than inflate the class.

### 5.3 Override and reclassification

The human sees the proposed classification at the intake gate ([6.2](#62-intake)) and MAY override it. The gate's decision is recorded in the `gates` record like any other outcome ([7](#7-gates)); the class the human accepts — overridden or not — is what `run.risk` and `risk_rationale` carry. Mid-run, stall or scope-drift signals (see [Loop contracts](#92-loop-contracts)) MAY trigger reclassification upward, never downward. A reclassification updates `run.risk` in run state and applies the new class's defaults to all subsequent steps.

## 6. Workflows and stages

### 6.1 Composition

Six stages exist: `intake`, `ideation`, `planning`, `implementation`, `review`, `delivery`. Each stage owns its steps, loop contracts, and gates. Workflows compose stages **by reference** and MUST NOT restate stage content. The canonical workflows:

- `feature` = `intake` → `ideation` → `planning` → `implementation` → `review` → `delivery`
- `bugfix` = `intake` → `planning` → `implementation` → `review` → `delivery`
- `plan` = `intake` → `ideation` → `planning`

Risk-class overlays — what each class skips or batches — are encoded once, per class, not per workflow.

### 6.2 Intake

`intake` is the entry stage of every workflow. It has three parts, in order:

1. **Clarifying-question gate** — if the brief's ambiguity is above threshold, the run stops here and asks; one cheap question beats a full revision loop later.
2. **Risk router** — applies the classification rubric ([5.2](#52-classification-rubric)) and proposes a class.
3. **Intake gate** — the human sees the confirmed brief and the proposed class, and MAY override the class ([5.3](#53-override-and-reclassification)). Its transport follows the class defaults ([5.1](#51-the-four-classes)).

Its outputs are a confirmed brief artifact and a risk class recorded in run state.

## 7. Gates

A gate is where the protocol collects a human decision. Gates come in two transports:

- **Blocking** — the run pauses until the human decides.
- **Inbox** — the decision request is batched; the run continues where safe and the human clears the inbox asynchronously.

Which gates exist and which transport they default to is a property of the risk class ([5.1](#51-the-four-classes)). At R3, transports MAY be configured per gate.

Every gate decision has exactly one outcome: `accept`, `revise`, or `reject`. Unless a stage declares otherwise, outcomes route by default: `accept` proceeds to the next step in composition order; `revise` returns to the step that produced the gated artifact; `reject` ends the run — or the phase, where the workflow declares phases. A stage MAY override these defaults with explicit edges.

**Instrumentation requirement:** every gate outcome MUST be recorded in run state with its gate id, transport, outcome, and timestamp. This record is not optional bookkeeping — accumulated gate outcomes are the evidence for tuning gate placement, and a client that skips recording does not conform.

## 8. Artifacts and runs

### 8.1 Run-scoped directories

Each run owns a directory, `{artifacts}/runs/<run-id>/`, referred to in metadata as `{run}`. `{artifacts}` is the consuming project's artifact root: where it lives is project configuration, and the executor MUST resolve it identically for every step of a run. Concurrent runs and re-runs MUST NOT share a run directory. All step inputs and outputs are addressed relative to `{run}`.

### 8.2 Manifest

The run state carries a manifest listing the artifacts the run has produced. The executor maintaining the run state MUST keep the manifest current as outputs land.

### 8.3 Templates

Where an output declares a template, the artifact is scaffolded from that template by script — not generated freehand — so structure is guaranteed before content is written. Placeholders in templates are contracts: a scaffolded artifact MUST contain every placeholder its template defines until the step fills it.

### 8.4 Grounding cache

Inputs marked optional (`required: false`) MAY be satisfied from a previous run's artifact when the executor judges it fresh — grounding work (codebase analysis, requirement parsing) is expensive and often reusable. Freshness policy belongs to the executor; the protocol only marks which inputs are cacheable.

### 8.5 Resume

Resuming a run is defined entirely by run state: read it, find the first step whose status is not `done` or `skipped`, and continue there. No other memory is required.

## 9. Orchestration metadata

All orchestration semantics an author declares live under a single `workflow` key inside the `metadata` extension point of Agent Skills frontmatter. One file carries both the prose a plain agent reads and the structure a driver executes.

Every `metadata.workflow` block MUST carry a `protocol` field declaring the protocol version it was authored against (see [Versioning](#11-versioning)).

### 9.1 Step and handoff

A step declares its role, its input contract, its output, and its state-machine edges:

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/grounding.md"
          required: false # cacheable, see spec §8.4
      output:
        artifact: "{run}/phase-{N}-plan.md"
        template: references/plan.template.md
      on:
        PASS: plan-approval
        PASS_WITH_CONDITIONS: plan-revise
        FAIL: plan-revise
```

- `inputs` is the handoff contract: each entry names an artifact and whether it is required. A required input that is missing blocks the step.
- `output` names the artifact the step produces and, optionally, the template it is scaffolded from ([8.3](#83-templates)).
- `on` maps each verdict to the next step or gate id. The verdict that routes a step is produced by the validation of that step's output — a `validator` step or machine checks ([3.3](#33-verdicts)) — never by the producing role grading its own work; declaring `on` does not make the step emit verdicts itself. A step MAY omit `on` when its output has no validation; it then proceeds to the next step in composition order, the same default that routes a gate's `accept` ([7](#7-gates)). A declared `on` MUST route at least `PASS` and `FAIL` — machine checks produce only those two — and every verdict its validation can actually produce MUST have an edge (`PASS_WITH_CONDITIONS` wherever a validator is the source); an executor encountering a verdict with no edge MUST stop and escalate rather than guess.

### 9.2 Loop contracts

A looping step or stage declares when it is allowed to exit and what to do when it spins:

```yaml
metadata:
  workflow:
    protocol: "0.1"
    loop:
      exit_criteria: # ALL must hold
        - artifact: "{run}/phase-{N}-plan-validation.md"
          verdict: PASS
        - command: "npm test" # exit code 0
      max_iterations: 4
      stall:
        signal: no-artifact-delta
        action: escalate
      scope:
        declared_from: "{run}/phase-{N}-plan.md"
        on_drift: flag # flag | escalate
```

- `exit_criteria` is a conjunction: every criterion must hold. A criterion is either an artifact carrying a required verdict or a command that must exit 0.
- `max_iterations` caps the loop. Reaching the cap without exit escalates to the human.
- `stall` detects spinning inside the cap: `no-artifact-delta` means no meaningful output change between iterations. The declared `action` (`escalate`) fires instead of burning remaining iterations.
- `scope` binds the loop to the file scope its plan declared. On drift, `flag` records the signal; `escalate` stops for a human. Either way the signal feeds mid-run reclassification ([5.3](#53-override-and-reclassification)).

### 9.3 Triggers

A workflow entry point declares how it starts:

```yaml
metadata:
  workflow:
    protocol: "0.1"
    trigger:
      kind: interval # manual (default) | interval | cron | event
      every: 5m # interval kind only
      until: # stop condition for recurring runs
        command: "gh pr view --json state -q .state"
        equals: MERGED
```

- `kind: manual` is the default and preserves plain on-demand behavior.
- `interval` runs every `every`; authors SHOULD match the interval to the real change rate of the input being watched.
- `cron` runs on a cron expression carried in a `cron` field (e.g. `"0 9 * * 1"`).
- `event` runs on an executor-defined event.
- `every` and `cron` are each valid only for their own kind; a trigger MUST NOT carry both.
- `until` stops a recurring trigger when `command`'s output equals `equals`. It applies to the recurring kinds — `interval`, `cron`, and `event` (each occurrence starts a run) — and a `manual` trigger MUST NOT declare it.

### 9.4 Degradation

`metadata.workflow` is a degradation-tolerant hint layer:

- A client that does not understand `metadata.workflow` MUST be able to use the skill by ignoring the block entirely and running the body as prose, with the human as executor.
- A client that understands the block partially SHOULD honor what it understands and ignore the rest; unknown keys under `workflow` MUST NOT be treated as errors during 0.x.
- Degradation works in both directions: a human or harness can replace a driver at any step, and a driver can pick up a run a human advanced, because all state is in artifacts and run state.

## 10. Run state

Runtime state lives in `{run}/workflow-state.yaml`. It has exactly one writer — the executor, which MAY be a human acting as executor ([2](#2-conformance-language-and-terms)) — and MUST NOT be edited by anything else while a run is live. It is runtime state the executor maintains, never a hand-authored source document.

```yaml
run:
  id: 2026-08-03-feature-slug
  workflow: feature
  risk: R2
  risk_rationale: "single module, no security surface, one phase"
  protocol: "0.1"
steps:
  - id: plan-create
    status: done # pending | active | blocked | done | skipped
    iterations: 2
    stall_flags: []
gates:
  - gate: plan-approval
    transport: blocking # blocking | inbox
    outcome: revise # accept | revise | reject
    at: 2026-08-03T14:12:00Z
instrumentation: # optional enrichment (tokens, duration) per step
artifacts: [] # run manifest, see spec §8.2
```

- `run` identifies the run: id, workflow, risk class with rationale ([5](#5-risk-classes)), and the protocol version the run executes under.
- `steps` records each step's `status` (`pending` | `active` | `blocked` | `done` | `skipped`), its `iterations` count against the loop cap, and any accumulated `stall_flags`.
- `gates` is the instrumentation record required by [section 7](#7-gates).
- `instrumentation` MAY carry per-step enrichment such as token counts and durations.
- `artifacts` is the run manifest ([8.2](#82-manifest)).

## 11. Versioning

The protocol version is `<major>.<minor>`, declared in every `metadata.workflow` block and in each run's state.

- During `0.x`, any minor version MAY contain breaking changes; that is what the `0` major signals. Breaking changes are recorded in the repository changelog.
- A client SHOULD warn when it encounters a `protocol` value newer than the version it implements, and MUST NOT silently misinterpret structures from a newer major version.
- From protocol version `1.0`, minor versions are backward-compatible additions; breaking changes require a major version.

The repository's release tags use full semantic versioning (`0.1.0`, `1.0.0`, …) and version the whole surface — this specification, the schemas, roles, and workflows — together; the `protocol` field tracks the major and minor components of that release line.
