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

Every run is classified into exactly one of four risk classes at the `intake` stage. The class the human accepts there, and a one-line rationale for it, MUST be recorded in run state — and are recorded nowhere in it before that, the fields carrying a decision rather than the proposal that preceded it ([5.3](#53-override-and-reclassification)).

### 5.1 The four classes

|  | R0 exploratory | R1 trivial | R2 standard | R3 high |
| --- | --- | --- | --- | --- |
| **Typical work** | Spike, throwaway prototype, "what would it take" | Typo-class fix, config tweak, pattern-following small change | Ordinary feature or bugfix | Multi-phase, security-surface, irreversible, or architecturally novel work |
| **Mode** | `inline`, no role split | `inline`, implementer only | `inline` persona-switching, all roles | `isolated` per role |
| **Roles** | none (free agent) | `implementer` (+ machine checks) | `analyst` → `planner` → `implementer` → `reviewer` → `validator` | full set; `arbiter` mandatory |
| **Arbiter** | — | — | only on reviewer/validator disagreement | mandatory |
| **Gates** | none; exit note only | delivery gate, batched to inbox | plan approval **blocking**; others batched to inbox | all blocking by default (per-gate configuration allowed) |
| **Security review** | no | no | conditional on the security-surface signal recorded at intake ([5.2](#52-classification-rubric)) | mandatory |
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

The human sees the proposed classification at the intake gate ([6.2](#62-intake)) and MAY override it. The gate's decision is recorded in the `gates` record like any other outcome ([7](#7-gates)); the decision the human accepts — overridden or not — is what run state carries: `run.risk` takes the accepted class, `risk_rationale` the one-line reason for it. Both are absent until then. They hold a decision, and a proposal written into them would be a proposal impersonating one, so run state exists through intake without them and the two appear together when the gate accepts ([10](#10-run-state)). An override MAY fall below a floor one of the rubric's binding rules sets ([5.2](#52-classification-rubric)) — the human decides and the router only proposes, which is what that gate is for — but MUST NOT do so silently. `risk_rationale` justifies the class run state carries, so where the human overrides it takes the human's reason rather than the router's line for the class it displaced; a rationale arguing for a class `run.risk` does not hold is precisely what makes an override invisible. An override MUST therefore carry one: `risk_rationale` is required and non-empty ([10](#10-run-state)), and a decision that supplies nothing leaves the field holding an argument for the class the human just rejected. It is recorded with the accepted class in the brief's routing record, alongside the router's proposal rather than over it — one field cannot hold both the argument for the class proposed and the reason for rejecting it, and those disagree in exactly the case this clause is about. It is not direction in the sense of [7](#7-gates): an override is an `accept`, so no step re-reads the brief to apply it, and what reads it is the executor transcribing `risk_rationale`. It takes that clause's ordering even so, and the whole order is stated rather than half of it: the accepted class and its rationale are written to the brief first, then `run.risk` takes that class and `risk_rationale` that rationale, and the gate outcome is recorded last. A retried decision that no longer accepts that class clears both run-state fields before recording its own outcome, the pairing that stops them being half-written stopping them being half-cleared ([10](#10-run-state)): a `reject` would otherwise end a run carrying a class nobody accepted, and a `revise` would re-enter intake while run state still claims a decision. Ordering only the brief write would leave the other two free of each other, and a crash between them resumes past an accepted gate carrying the class it rejected — so every stage after it runs at the wrong one. Recording the outcome last means a crash costs a decision re-asked rather than a decision misapplied, and excluded from §7 these fields would have inherited no ordering at all. The executor MUST surface the conflict rather than resolve it, and MUST NOT amend the classifier's recorded reading to agree with the accepted class: the disagreement between that reading and `run.risk` is the whole record that a floor was crossed, so erasing it is how the override becomes silent. A security-surface signal accepted below R2 is the case this exists for — the review stage does not run there, so no later step re-derives the reading and nothing in the run can catch it. Mid-run, stall or scope-drift signals (see [Loop contracts](#92-loop-contracts)) MAY trigger reclassification upward, never downward. A reclassification updates `run.risk` and `risk_rationale` together and applies the new class's defaults to all subsequent steps. Both, because the rationale justifies the class the field beside it holds: moving the class alone leaves the argument for the one it replaced, which is the same mismatch this paragraph forbids an override from creating, reached by the one path that is not a gate decision. The new rationale is the signal that triggered the reclassification — the stall or the scope drift and what it was — written before the new class's defaults take effect, so the run never runs under a class whose reason is unrecorded.

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

Its outputs are a confirmed brief artifact, carrying the router's security-surface reading alongside the class it proposes, and the accepted risk class recorded in run state. That recorded reading is what the conditional security review at R2 is evaluated against ([5.1](#51-the-four-classes)); where it lives in the brief is the intake stage's contract.

## 7. Gates

A gate is where the protocol collects a human decision. Gates come in two transports:

- **Blocking** — the run pauses until the human decides.
- **Inbox** — the decision request is batched; the run continues where safe and the human clears the inbox asynchronously.

Which gates exist and which transport they default to is a property of the risk class ([5.1](#51-the-four-classes)). At R3, transports MAY be configured per gate.

Every gate decision has exactly one outcome: `accept`, `revise`, or `reject`. Unless a stage declares otherwise, outcomes route by default: `accept` proceeds to the next step in composition order; `revise` returns to the step that produced the gated artifact; `reject` ends the run — or the phase, where the workflow declares phases. A stage MAY override these defaults with explicit edges.

A gate decision MAY carry the human's direction — what they want changed, or the content of an answer to a question the gate asked. A gate record holds the outcome and never that content: its shape is closed to exactly the four fields the instrumentation requirement below names ([10](#10-run-state)), so this is enforced rather than asked for.

Direction that outlives the decision has to be written down, and the executor MUST record it in the gated artifact — in a section reserved for it, never woven into the content — before recording the outcome. Resume is defined entirely by run state and requires no other memory ([8.5](#85-resume)), and an `inbox` transport is asynchronous by construction, so a decision may reach a driver other than the one that requested it: direction held only in the session that collected it survives neither.

The reserved section is what keeps an instruction an instruction. Written into the surrounding content it would pre-apply the change the human asked for, or become indistinguishable from what the artifact already said. The direction therefore needs no input declaration of its own and no lifecycle rule either: the step reads the section, folds what it asks for into the parts of the artifact it is about, and its rewrite returns the section to `None`, the empty-state marker the artifact templates use.

That rests on the destination reading the artifact, which the routing does not otherwise guarantee: the default route names the step that *produced* the gated artifact, and producing it means declaring it as an output, not as an input — an executor materializes only declared inputs ([9.1](#91-step-and-handoff)). Wherever an outcome may carry direction — every `revise`, and the one `accept` scoped below — the gate MUST therefore route it to a step that declares the gated artifact among its inputs, by the default route where the producer also reads it and by an explicit edge where it does not. A route that ends the run or leaves the stage carries no direction and is outside this, which is what an `accept` completing a run or a `reject` ending one does. Routing direction to a step that only writes the artifact hands it something it cannot see. An artifact that leaves its stage with anything other than `None` in that section carries direction nobody applied — which is the check the section buys, and why the empty state is a marker rather than an absence: a section left blank is indistinguishable from one a producer forgot to scaffold.

The ordering also decides which failure a crash produces, wherever the gate fires once run state exists: recording the direction first re-asks a question whose answer is already on disk, where recording the outcome first loses the answer and keeps a decision nothing can act on.

That rests on a resume returning to the gate rather than continuing past it, which the step statuses have to say. A gate has its own `steps` entry — the starter fixture models `plan-approval` that way beside the `plan-create` entry that produced the artifact — and it is that entry, not the producer's, which MUST NOT be marked `done` while the outcome is unrecorded: it stays `blocked` ([10](#10-run-state)). §8.5 resumes at the first step that is neither `done` nor `skipped`, so the resume lands on the gate and asks it again, where blocking the producer instead would re-run the step that wrote the artifact and never reach the gate at all.

Recording the outcome is not the last write, wherever the outcome routes the run onward. Where it does, the outcome and that routing MUST land together, in one write that leaves the run resumable: a gate whose outcome is recorded with nothing un-`done` after it resumes to no step at all, which loses the decision on the far side of the window this ordering closes on the near one. What that write contains is the routing below; the gate's own status within it is the outcome's, stated there rather than assumed here. A `revise` always routes onward, and so does an `accept` a stage sends back to a step rather than forward; an `accept` that proceeds in composition order needs no routing write only where the step it proceeds to already has a record; where the decision is what determines the records — the accepted class deciding which later steps a risk class skips — that gate populates the remaining entries as `pending` or `skipped` before its own becomes `done`, or it resumes to nothing having decided what the rest of the run was going to be. The terminal outcomes are the other case and want the opposite: a `reject` ends the run, and an `accept` at the last gate completes it, so there is no destination to enter `pending` and nothing un-`done` afterwards is exactly right — that state *is* the ending, and requiring a routing write there would make rejection unrepresentable.

Re-entry resets more than the step it re-enters, and by the same write. A step run again — by a `revise` routing back to it, or by a loop iterating — invalidates what its output fed: the validator that must re-check it, the gate that must decide again. Those leave `done` when the step does, or the guarantee holds for exactly one step: the run resumes into the revision, and once that finishes finds nothing un-`done` after it and stops with the revised artifact never re-validated and never re-approved. What a re-entry invalidates is what actually ran on the artifact, which differs by route and MUST be read from the stage rather than assumed: the validator where the stage has one, the classifier that read the artifact at intake, the gate that must decide again. Intake has no validator and re-entering `brief-confirm` invalidates `risk-route`, which is not one; a validator the risk class skipped stays `skipped` and is not resurrected by a rule expecting it. Resetting a fixed shape would both miss a dependent and run a step the overlay excludes.

A gate's own status in that write is its outcome's. On a `revise` it returns to `pending` with the steps it invalidated, ordered so the re-entered step is the first a resume finds: the gate decided that the artifact must change, which is a decision to run this cycle again rather than one the run proceeds past. On an `accept` the run proceeds past, and on a `reject` the run ends, so the entry is `done` — the decision stands and this gate is not asked about this artifact again.

Writes staged for a decision belong to that decision. A gate re-asked after a crash may resolve differently from the one whose writes were already on disk, and those writes are then nobody's: before recording the retried outcome the executor MUST clear or replace what the abandoned one staged. Direction written for a `revise` that comes back `accept` or `reject` would otherwise ride out of the stage inside the artifact, which is exactly the state above calls direction nobody applied — reached not by a step forgetting to clear it but by a decision that never happened. Marked `done` before its outcome exists, the step is skipped on resume and the run continues past a gate nobody answered — which would leave outcome-last ordering buying detection rather than recovery. That holds at every gate, because none of them fires before run state exists: the file is created when the run starts and carries no class until one is accepted ([10](#10-run-state)), so a gate reached during intake has the same state to be resumed from as one reached later. What the reserved section buys at every gate, durable or not, is the separation above — the human's instruction reaches the step as an instruction rather than as content already folded into the artifact.

A `revise` SHOULD carry direction. The protocol cannot judge whether a direction is adequate, so it is not a MUST, but a `revise` carrying none returns the run to a step whose inputs are unchanged, and nothing then distinguishes its next output from the one the gate has just declined.

An `accept` MAY carry direction only where the stage routes it to a step that re-reads the gated artifact, which is the clarifying question ([6.2](#62-intake)): its `accept` returns through the step that restates the brief before the run continues, rather than proceeding past it. That the outcome is `accept` says the answer settled the question, not that nothing is left to apply. Everywhere else `accept` means accepted — the run proceeds to a step that treats the artifact as settled, so a change the human wants there is a `revise`. Direction attached to such an `accept` would be recorded and never applied, and would travel inside the artifact that carries it.

**Instrumentation requirement:** every gate outcome MUST be recorded in run state with its gate id, transport, outcome, and timestamp (the `at` field, [10](#10-run-state)). This record is not optional bookkeeping — accumulated gate outcomes are the evidence for tuning gate placement, and a client that skips recording does not conform.

## 8. Artifacts and runs

### 8.1 Run-scoped directories

Each run owns a directory, `{artifacts}/runs/<run-id>/`, referred to in metadata as `{run}`. `{artifacts}` is the consuming project's artifact root: where it lives is project configuration, and the executor MUST resolve it identically for every step of a run. Concurrent runs and re-runs MUST NOT share a run directory. All step inputs and outputs are addressed relative to `{run}`.

### 8.2 Manifest

The run state carries a manifest listing the artifacts the run has produced. The executor maintaining the run state MUST keep the manifest current as outputs land.

### 8.3 Templates

Where an output declares a template, the artifact is scaffolded from that template by script — not generated freehand — so structure is guaranteed before content is written. Scaffolding creates and MUST NOT overwrite: a step revising, re-entering, or appending to an artifact is given one that already exists, and re-scaffolding it would discard the content it was given to work from, a gate's recorded direction ([7](#7-gates)) included. Placeholders in templates are contracts: a scaffolded artifact MUST contain every placeholder its template defines until the step fills it.

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

- `inputs` is the handoff contract: each entry names an artifact and whether it is required. A required input that is missing blocks the step. The declaration MUST be complete: a step MUST declare every artifact whose content its instructions depend on — judged by, quoted from, checked against, or assembled out of — because an executor materializes only what is declared. A step whose prose reaches for an artifact it does not declare is unexecutable in the general case, however carefully that prose is written. Completeness is a property of the step's instructions, not of what a particular run produced: an input some risk class skips is declared `required: false`, never omitted. Because an optional input MAY be satisfied from an earlier run ([8.4](#84-grounding-cache)), a step that depends on same-run identity MUST either declare the input required or state the freshness check its prose applies; silence on that point is a defect, not a default.
- `output` names the artifact the step produces and, optionally, the template it is scaffolded from ([8.3](#83-templates)).
- `on` maps each verdict to the next step or gate id. The verdict that routes a step is produced by the validation of that step's output — a `validator` step or machine checks ([3.3](#33-verdicts)) — never by the producing role grading its own work; declaring `on` does not make the step emit verdicts itself. A step MAY omit `on` when its output has no validation, or when a loop contract's exit criteria consume its validation verdict ([9.2](#92-loop-contracts)); it then proceeds to the next step in composition order, the same default that routes a gate's `accept` ([7](#7-gates)). A target is normally a step or gate id; a stage id MAY also stand as a target, resolving to that stage's first step, past any content the run's risk class skips ([6.1](#61-composition)). A declared `on` MUST route at least `PASS` and `FAIL` — machine checks produce only those two — and every verdict its validation can actually produce MUST have an edge (`PASS_WITH_CONDITIONS` wherever a validator is the source); an executor encountering a verdict with neither an edge nor a consuming loop contract MUST stop and escalate rather than guess.

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

- `exit_criteria` is a conjunction: every criterion must hold. A criterion is either an artifact carrying a required verdict or a command that must exit 0. A command criterion MAY be the placeholder `{machine-checks}`, standing for the project's own machine-check command ([5.1](#51-the-four-classes)); the consuming project binds it in configuration, and the executor MUST resolve it before evaluating the criterion. Exit criteria are a verdict consumer: a verdict they name routes the loop — iterate or exit — instead of a step edge, so the producing step MAY omit `on` ([9.1](#91-step-and-handoff)); on exit, the loop's owner proceeds in composition order.
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
- A client that understands the block partially SHOULD honor what it understands and ignore the rest; unknown top-level keys under `workflow` — siblings of the declared structures — MUST NOT be treated as errors during 0.x. Inside a declared structure (`step`, `loop`, `trigger`), unknown keys are authoring errors, and the schemas reject them.
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
  - id: plan-revise # the revise outcome's destination, and the first entry a resume finds
    status: pending
  - id: plan-validate # must re-check what the revision changes
    status: pending
  - id: plan-approval # decides again; a gate is `done` only where its decision stands
    status: pending
gates:
  - gate: plan-approval
    transport: blocking # blocking | inbox
    outcome: revise # accept | revise | reject
    at: 2026-08-03T14:12:00Z
instrumentation: # optional enrichment (tokens, duration) per step
artifacts: [] # run manifest, see spec §8.2
```

- `run` identifies the run: id, workflow, risk class with rationale ([5](#5-risk-classes)), and the protocol version the run executes under.
- `run.risk` and `risk_rationale` MUST be absent before the intake gate accepts a class and present from then on, and they move together. The schema enforces the pairing and not the timing: whether that gate has decided is not visible in this document — gate ids are workflow vocabulary rather than protocol vocabulary, and a clarifying question also records `accept` while no class exists — so the timing is one of the semantics this prose carries for a structure the schema defines. Run state exists before either field: it is created when the run starts, which is what gives a gate reached during intake something to resume from.
- `steps` holds one record per step, not one per invocation: a step that runs again reuses its record and `iterations` counts the re-entries, which is what that field is for. The list is ordered so that the first entry which is neither `done` nor `skipped` is the next step to run — that is what makes resume ([8.5](#85-resume)) mean anything, and a transition that re-enters steps keeps it true. Each record carries `status` (`pending` | `active` | `blocked` | `done` | `skipped`), its `iterations` count against the loop cap, and any accumulated `stall_flags`. `iterations` counts against the cap of the loop instance it is in, not across the run: a multi-phase workflow repeats a stage per phase ([6.1](#61-workflows)), each repetition is its own loop with its own cap ([9.2](#92-loop-contracts)), and the count starts at zero when a phase enters one. Carrying it forward would let a phase that revised twice spend the next phase's allowance, and the caps are per loop precisely so one phase's difficulty is not another's. `blocked` is what a *gate's own* entry wears while it waits on a human — not the entry of the step that produced the artifact, which is `done` by then: it is not `done`, so a resume returns to the gate rather than past it, and blocking the producer instead would re-run the step and never reach the gate ([7](#7-gates), [8.5](#85-resume)). It becomes `done` when its decision stands: an `accept` the run proceeds past, or a `reject` that ends the run. A `revise` is the decision that does not stand — the cycle runs again and this gate decides again — so its entry returns to `pending` with the rest of what the revision invalidates.
- `gates` is the instrumentation record required by [section 7](#7-gates).
- `instrumentation` MAY carry per-step enrichment such as token counts and durations.
- `artifacts` is the run manifest ([8.2](#82-manifest)).

## 11. Versioning

The protocol version is `<major>.<minor>`, declared in every `metadata.workflow` block and in each run's state.

- During `0.x`, any minor version MAY contain breaking changes; that is what the `0` major signals. Breaking changes are recorded in the repository changelog.
- A client SHOULD warn when it encounters a `protocol` value newer than the version it implements, and MUST NOT silently misinterpret structures from a newer major version.
- From protocol version `1.0`, minor versions are backward-compatible additions; breaking changes require a major version.

The repository's release tags use full semantic versioning (`0.1.0`, `1.0.0`, …) and version the whole surface — this specification, the schemas, roles, and workflows — together; the `protocol` field tracks the major and minor components of that release line.
