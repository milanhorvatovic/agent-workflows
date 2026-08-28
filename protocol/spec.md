# Protocol Specification

**Protocol version:** `0.2` (pre-release — see [Versioning](#11-versioning))

This document is the normative surface of the agent-workflows protocol. The JSON Schemas in [`schemas/`](schemas/) normatively define the structures described in sections 9 and 10; this prose defines their semantics. The two MUST NOT diverge — a divergence is a defect in one of them, to be fixed rather than resolved by precedence.

## 1. Scope

The protocol structures how AI agents and humans collaborate on software work. It is a protocol, not a platform: there is no required SDK, runtime, or vendor. Three tiers divide the concerns:

- **Roles** define WHO acts: a bounded function with its own success criteria (see [Roles](#3-roles)).
- **Skills** define WHAT is done: task instructions packaged as Agent Skills-conformant directories, readable as plain prose by any agent.
- **Workflows** define HOW work flows: stages composed into sequences, with loop contracts and gates (see [Workflows and stages](#6-workflows-and-stages)).

State lives in markdown artifacts and one YAML run-state file, all in the repository. Any agent that can read a prompt can execute the protocol; any orchestration the protocol enables is carried as machine-readable hints that degrade to prose (see [Degradation](#95-degradation)).

## 2. Conformance language and terms

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119.

- **Executor** — whatever advances the loop: a human, a capable agent harness, or a driver program. The executor is not a role and holds no intelligence of its own.
- **Client** — software that reads protocol files (an executor, a validator, an editor plugin).
- **Run** — one execution of a workflow, with its own identifier, artifact directory, and run state.
- **Step** — the smallest unit of execution: one role applying one skill to declared inputs, producing a declared output.
- **Stage** — a named sub-workflow (steps, loop contracts, gates) that workflows compose.
- **Gate** — a point where a human decision is required or collected (see [Gates](#7-gates)).
- **Artifact** — a file a step declares as an input or an output, addressed relative to the run directory.
- **Working material** — a file a step writes into the run directory and declares as neither ([8.2](#82-manifest)). Not an artifact, and nothing outside the invocation that wrote it may depend on it.
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

Every run that proceeds past the `intake` stage is classified into exactly one of four risk classes there. The class the human accepts, and a one-line rationale for it, MUST be recorded in run state — a run rejected at either intake gate ends without one, which is not an unrecorded classification but the absence of a decision to record — and are recorded nowhere in it before that, the fields carrying a decision rather than the proposal that preceded it ([5.3](#53-override-and-reclassification)).

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

Its input is the request the run was created with ([8.7](#87-request)) — the stage's first step restates it, and it is the one input no earlier step produced. Its outputs are a confirmed brief artifact, carrying the router's security-surface reading alongside the class it proposes, and the accepted risk class recorded in run state. That recorded reading is what the conditional security review at R2 is evaluated against ([5.1](#51-the-four-classes)); where it lives in the brief is the intake stage's contract.

## 7. Gates

A gate is where the protocol collects a human decision. Gates come in two transports:

- **Blocking** — the run pauses until the human decides.
- **Inbox** — the decision request is batched; the run continues where safe and the human clears the inbox asynchronously.

Which gates exist and which transport they default to is a property of the risk class ([5.1](#51-the-four-classes)). At R3, transports MAY be configured per gate.

Every gate decision has exactly one outcome: `accept`, `revise`, or `reject`. Unless a stage declares otherwise, outcomes route by default: `accept` proceeds to the next step in composition order; `revise` returns to the step that produced the gated artifact; `reject` ends the run — or the phase, where the workflow declares phases *and* the run has an accepted list to name the next one; before that acceptance there is no phase to advance to and the run ends. Ending only the phase carries a further precondition, because a phase list states which phases must complete before which others: it is sound only where nothing the list places after the rejected phase depends on it, and an executor that cannot establish that MUST end the run. It cannot establish it from run state, which carries the phase number and not the list, nor generally from the list itself, which records its sequencing as prose for a reader rather than as structure. So a rejected phase ends the run wherever these workflows are concerned, and dropping one phase from a run that continues is a `revise` carrying that direction rather than a `reject`. A stage MAY override these defaults with explicit edges.

A gate decision MAY carry the human's direction — what they want changed, or the content of an answer to a question the gate asked. A gate record holds the outcome and never that content: its shape is closed to the fields the instrumentation requirement below names ([10](#10-run-state)) — which gate, which phase where a phase repeats it, how the decision was collected, the outcome, and when — so this is enforced rather than asked for.

Direction that outlives the decision has to be written down, and the executor MUST record it in the gated artifact — in a section reserved for it, never woven into the content — before recording the outcome. Resume is defined entirely by run state and requires no other memory ([8.5](#85-resume)), and an `inbox` transport is asynchronous by construction, so a decision may reach a driver other than the one that requested it: direction held only in the session that collected it survives neither.

The reserved section is what keeps an instruction an instruction. Written into the surrounding content it would pre-apply the change the human asked for, or become indistinguishable from what the artifact already said. The direction therefore needs no input declaration of its own and no lifecycle rule either: the step reads the section, folds what it asks for into the parts of the artifact it is about, and its rewrite returns the section to `None`, the empty-state marker the artifact templates use.

That rests on the destination reading the artifact, which the routing does not otherwise guarantee: the default route names the step that *produced* the gated artifact, and producing it means declaring it as an output, not as an input — an executor materializes only declared inputs ([9.1](#91-step-and-handoff)). Wherever an outcome may carry direction — every `revise`, and the one `accept` scoped below — the gate MUST therefore route it to a step that declares the gated artifact among its inputs, by the default route where the producer also reads it and by an explicit edge where it does not. A route that ends the run or leaves the stage carries no direction and is outside this, which is what an `accept` completing a run or a `reject` ending one does. Routing direction to a step that only writes the artifact hands it something it cannot see. An artifact that leaves its stage with anything other than `None` in that section carries direction nobody applied — which is the check the section buys, and why the empty state is a marker rather than an absence: a section left blank is indistinguishable from one a producer forgot to scaffold.

The ordering also decides which failure a crash produces, wherever the gate fires once run state exists: recording the direction first re-asks a question whose answer is already on disk, where recording the outcome first loses the answer and keeps a decision nothing can act on.

That rests on a resume returning to the gate rather than continuing past it, which the step statuses have to say. A gate has its own `steps` entry — the starter fixture models `plan-approval` that way beside the `plan-create` entry that produced the artifact — and it is that entry, not the producer's, which MUST NOT be marked `done` while the outcome is unrecorded: it stays `blocked` ([10](#10-run-state)). §8.5 resumes at the first step that is neither `done` nor `skipped`, so the resume lands on the gate and asks it again, where blocking the producer instead would re-run the step that wrote the artifact and never reach the gate at all.

Recording the outcome is not the last write, wherever the outcome routes the run onward. Where it does, the outcome and that routing MUST land together, in one write that leaves the run resumable: a gate whose outcome is recorded with nothing un-`done` after it resumes to no step at all, which loses the decision on the far side of the window this ordering closes on the near one. What that write contains is the routing below; the gate's own status within it is the outcome's, stated there rather than assumed here. A `revise` always routes onward, and so does an `accept` a stage sends back to a step rather than forward; an `accept` that proceeds in composition order needs no routing write only where the step it proceeds to already has a record; where the decision is what determines the records — the accepted class deciding which later steps a risk class skips — that gate populates the remaining entries as `pending` or `skipped` before its own becomes `done`, or it resumes to nothing having decided what the rest of the run was going to be. The terminal outcomes are the other case: they end something rather than routing to a step, and the write they make is that ending. Where what ends is the run — a `reject` in a workflow with no phases, an `accept` at the last gate — every record still `pending` or `blocked` becomes `skipped` with the outcome, every one but the deciding gate's own, which is `done`, its decision being what ended the run rather than work the ending skipped. A resume looks for the first record that is neither `done` nor `skipped`, and without the bulk write it would walk into work the rejection ended; without the exemption the gate that decided would read as a step nobody reached.

Where what ends is the phase — which is what a `reject` ends wherever the workflow declares them, the run has an accepted phase list, and the precondition in [7](#7-gates) holds; failing any of those the run ends and the run-bounded write above is the right one — the same write is bounded by the phase instead: the records of the phase being abandoned go `skipped`, the deciding gate is `done`, and the run moves to the next phase by the transition below — or, if that phase was the last, ends as above. Sweeping every remaining record would end the run instead of the phase and take the phases nobody rejected with it. A gate that fires once later steps already have records — and after `intake-approval` they do — leaves exactly that behind if it marks only itself.

Re-entry resets more than the step it re-enters, and by the same write. A step run again — by a `revise` routing back to it, or by a loop iterating — invalidates what its output fed: the validator that must re-check it, the gate that must decide again. Those leave `done` when the step does, or the guarantee holds for exactly one step: the run resumes into the revision, and once that finishes finds nothing un-`done` after it and stops with the revised artifact never re-validated and never re-approved. What a re-entry invalidates is what actually ran on the artifact, which differs by route and MUST be read from the stage rather than assumed: the validator where the stage has one, the classifier that read the artifact at intake, the gate that must decide again. Intake has no validator and re-entering `brief-confirm` invalidates `risk-route`, which is not one; a validator the risk class skipped stays `skipped` and is not resurrected by a rule expecting it. Resetting a fixed shape would both miss a dependent and run a step the overlay excludes.

A gate's own status in that write is its outcome's. On a `revise` it returns to `pending` with the steps it invalidated, ordered so the re-entered step is the first a resume finds: the gate decided that the artifact must change, which is a decision to run this cycle again rather than one the run proceeds past. On an `accept` the run proceeds past, and on a `reject` the run ends, so the entry is `done` — the decision stands and this gate is not asked about this artifact again.

Writes staged for a decision belong to that decision. A gate re-asked after a crash may resolve differently from the one whose writes were already on disk, and those writes are then nobody's: before recording the retried outcome the executor MUST clear or replace what the abandoned one staged. Direction written for a `revise` that comes back `accept` or `reject` would otherwise ride out of the stage inside the artifact, which is exactly the state above calls direction nobody applied — reached not by a step forgetting to clear it but by a decision that never happened. Marked `done` before its outcome exists, the step is skipped on resume and the run continues past a gate nobody answered — which would leave outcome-last ordering buying detection rather than recovery. That holds at every gate, because none of them fires before run state exists: the file is created when the run starts and carries no class until one is accepted ([10](#10-run-state)), so a gate reached during intake has the same state to be resumed from as one reached later. What the reserved section buys at every gate, durable or not, is the separation above — the human's instruction reaches the step as an instruction rather than as content already folded into the artifact.

A `revise` SHOULD carry direction. The protocol cannot judge whether a direction is adequate, so it is not a MUST, but a `revise` carrying none returns the run to a step whose inputs are unchanged, and nothing then distinguishes its next output from the one the gate has just declined.

An `accept` MAY carry direction only where the stage routes it to a step that re-reads the gated artifact, which is the clarifying question ([6.2](#62-intake)): its `accept` returns through the step that restates the brief before the run continues, rather than proceeding past it. That the outcome is `accept` says the answer settled the question, not that nothing is left to apply. Everywhere else `accept` means accepted — the run proceeds to a step that treats the artifact as settled, so a change the human wants there is a `revise`. Direction attached to such an `accept` would be recorded and never applied, and would travel inside the artifact that carries it.

**Instrumentation requirement:** every gate outcome MUST be recorded in run state with its gate id, transport, outcome, and timestamp (the `at` field, [10](#10-run-state)). This record is not optional bookkeeping — accumulated gate outcomes are the evidence for tuning gate placement, and a client that skips recording does not conform.

## 8. Artifacts and runs

### 8.1 Run-scoped directories

Each run owns a directory, `{artifacts}/runs/<run-id>/`, referred to in metadata as `{run}`. `{artifacts}` is the consuming project's artifact root: where it lives is project configuration, and the executor MUST resolve it identically for every step of a run. Concurrent runs and re-runs MUST NOT share a run directory. All step inputs and outputs are addressed relative to `{run}`, in the normalized form a lineage record also carries ([8.6](#86-import)) — anchored at `{run}/`, no absolute form, no `.` or `..` segments, no empty segments, no backslashes, no control characters or Unicode line separators, no reserved device basenames, no trailing dots or spaces, and no colon anywhere — which the step schema encodes. The executor joins a declared path to the run directory, so a shape left open is a declaration naming a file the run does not contain, or a spelling a platform resolves to one it does.

That shape decides a path and not a set, which is the limit worth stating: `{run}/Brief.md` and `{run}/brief.md` are each well-formed under it and are one file wherever a filesystem folds case. Whether two declarations collide is a fact about the pair and about the filesystem being written to, so it is the executor's to detect and not this pattern's to prevent. The one path the protocol reserves by name is excluded by fold rather than by spelling for exactly that reason ([8.7](#87-request)).

Two placeholders name a phase in those paths, and they are not interchangeable. `{N}` is **the phase the step is executing** and resolves to exactly one artifact: the phase `run.phase` names ([10](#10-run-state)), or phase 1 where that field is absent, which is what a single-phase run carries and what a run carries before its first acceptance. It is what a stage a phase repeats uses, for the plan it is writing and the log it is filling. `{P}` is **each phase other than this step's that the run has already produced this artifact for**, and resolves to one path per such phase. What answers the second half is the manifest ([8.2](#82-manifest)), which records what the run has produced and only grows within it, so `{P}` needs no field of its own and no notion of a phase being finished. The first half is what keeps one rule from needing two, and **what settles it is the step's own `output`, never run state**: a step whose output carries `{N}` is executing a phase, and excludes that phase — its own phase's artifact is either what it is about to produce, or, where the phase has been round the loop already, a record of that phase rather than a binding on it. A step whose output carries no phase has none to exclude and reads them all, and so does a block that has no output at all — a loop contract ([9.2](#92-loop-contracts)) belongs to its stage rather than to a phase, so a `{P}` path there excludes nothing. Run state cannot settle this and must not be asked to: `run.phase` still names the last phase while the stages that run after it are running, so reading that field as "this step's phase" would drop the final phase from exactly the sets those stages exist to read whole. The two readers differ in what they exclude, not in what the token means, and which one a step is, is declared rather than inferred. A step that would otherwise have to say in prose that its `{N}` means something other than the phase it is executing is a step whose declaration wanted `{P}`.

A set-valued path does not change what `required` means, only what it counts: a required `{P}` input blocks the step ([9.1](#91-step-and-handoff)) where the manifest records the artifact for no phase at all, and an optional one is read for whichever phases it records and is simply empty where that is none. There is no third case where the set is short a phase: the manifest is what defines the set, so a phase it does not record is not one `{P}` names, and a phase whose artifact exists unrecorded is a manifest [8.2](#82-manifest) already obliges the executor to have kept current. It is the manifest of *this* run, which is what an optional `{P}` input cannot be satisfied from an earlier one: the cache in [8.4](#84-grounding-cache) hands over an artifact, and a phase set is a fact about the run that produced it. A step wanting both wants a different input. A step MUST NOT declare `{P}` in its `output`: a step produces one artifact ([9.1](#91-step-and-handoff)), and a phase-set of outputs is a stage that repeats rather than a step that fans out.

### 8.2 Manifest

The run state carries a manifest listing the artifacts the run has produced, imported ([8.6](#86-import)), or was given at creation ([8.7](#87-request)). The executor maintaining the run state MUST keep the manifest current as outputs land. What it lists are artifacts, which is what each of those three origins produces: the outputs steps declare ([9.1](#91-step-and-handoff)), the copies an import adopts ([8.6](#86-import)), and the request the run was created from ([8.7](#87-request)). A step MAY also write working material into `{run}`: a decision audit, an intermediate it re-reads within its own invocation. It declares that as neither input nor output and the manifest does not list it. A step MUST NOT depend on working material — another step's, or its own from an earlier invocation — because §9.1 obliges it to declare whatever its instructions depend on, and declaring it is exactly what would stop it being working material. So anything a contract needs is an artifact, declared and manifested, whatever a step keeps beside it for a human reader. The manifest records what was produced, imported, or given at creation rather than what is current work, so it only grows within a run: a step record returned to `pending` by a re-entry, or reset when a phase is entered ([10](#10-run-state)), does not unmake the output that step already wrote, and removing it would hide a phase's artifacts from every reader after the phase that produced them.

### 8.3 Templates

Where an output declares a template, the artifact is scaffolded from that template by script — not generated freehand — so structure is guaranteed before content is written. Scaffolding creates and MUST NOT overwrite: a step revising, re-entering, or appending to an artifact is given one that already exists, and re-scaffolding it would discard the content it was given to work from, a gate's recorded direction ([7](#7-gates)) included. Placeholders in templates are contracts: a scaffolded artifact MUST contain every placeholder its template defines until the step fills it.

### 8.4 Grounding cache

Inputs marked optional (`required: false`) MAY be satisfied from a previous run's artifact when the executor judges it fresh — grounding work (codebase analysis, requirement parsing) is expensive and often reusable. Freshness policy belongs to the executor; the protocol only marks which inputs are cacheable. Making another run's artifact this run's own — which is what reaches required inputs — is import ([8.6](#86-import)), instructed rather than judged; the cache hands an artifact over without adopting it.

One shape of optional input is outside this and not by policy: a path carrying `{P}` ([8.1](#81-run-scoped-directories)) resolves against this run's manifest, so there is no earlier run's artifact for the cache to hand over — the set is a fact about the run that produced it rather than a file that could stand in for one. `required: false` there marks the set allowed to be empty, which is what phase 1 has, and nothing about reuse.

### 8.5 Resume

Resuming a run is defined entirely by run state: read it, continue at the `active` record if there is one, and otherwise at the first step whose status is not `done` or `skipped`. No other memory is required. The `active` record takes precedence because it names the step that was running, where position only describes what has not run yet ([10](#10-run-state)).

### 8.6 Import

A run MAY begin from another run's deliverable — producing one for a later run to execute is the entire purpose of the `plan` workflow — and import is the mechanism: when a run is created, the executor MAY be instructed to copy named artifacts from an earlier run's directory into this one's. Instructed is the boundary between this and the cache ([8.4](#84-grounding-cache)): the cache is the executor satisfying an optional input from an earlier run by its own freshness judgment, where an import is a decision made by whoever starts the run, named artifact by artifact, and recorded. An executor MUST NOT import on its own judgment.

The mechanics make each copy this run's artifact. An import copies the artifact to the same `{run}`-relative path, rewrites the copy's run-scoped headers — the `Run` line every artifact template scaffolds to name the run an artifact belongs to, and the `Workflow` line where the artifact carries one ([8.3](#83-templates)) — to the importing run's id and workflow, adds the path to the manifest ([8.2](#82-manifest)), and records the import in run state — the path, the source run's id, and when ([10](#10-run-state)). Both headers rewrite for one reason: a brief authored by a `plan` run and adopted by the `feature` run executing it would otherwise name a workflow this run is not, and every reader of the copy is owed this run's answer. What the copy came from stays legible anyway — `imports` names the source run, and the source run's own state carries its workflow. The rewrite also un-decides: decision-scoped content in a copy — the **Accepted class** and **Accepted rationale** an intake override wrote into the brief's Routing block ([5.3](#53-override-and-reclassification)), and any **Gate direction** section not already at its empty marker ([7](#7-gates)) — returns to its empty state as part of the import, the proposal left standing, because a decision belongs to the run that takes it, no gate here has fired, and an adopted acceptance would otherwise read as a decision nobody in this run took — exactly what the executor transcribing the Routing block into run state must never find already written. The source run is read and never written. Imports happen when the run is created and MUST be recorded, copies landed, before any step runs: the readers include the intake stage, and a copy arriving after some step read the path's absence would put a lie into a manifest that only grows. The named path is a copy instruction, so it is confined the way a record alone need not be: it MUST be the artifact's normalized `{run}`-relative path — anchored at `{run}/`, no absolute form, no `.` or `..` segments — which the run-state schema encodes, and the executor MUST refuse an import whose source or destination resolves through any component that is a link, or otherwise lands outside the two run directories the record names; a path that would read or write elsewhere while recording the requested string is the lie the lineage exists to prevent.

Adoption is what the rewrite means, and it is what reaches `required`: an imported artifact is this run's, listed in this run's manifest, satisfying input declarations — required ones included — exactly as an output some step of this run declared, and joining every set a rule resolves against the manifest. The phase sets `{P}` names ([8.1](#81-run-scoped-directories)) are such a set — that section's "produced" is read through the manifest, which now records the import — so an imported phase artifact is one of the phases `{P}` resolves, deliberately. None of this weakens what `required` guards. The cache stays confined to optional inputs because it is the executor satisfying an input from elsewhere by policy; an import is the human putting the artifact here, and a step that guards same-run identity by checking an artifact's `Run` header is checking exactly what the rewrite makes true. A copy whose header still names the source run is not an import — it is the failure those checks exist to stop, and a run holding one stops at the first step that reads it.

What may be imported at all is bounded first: the request ([8.7](#87-request)) MUST NOT be, whatever else a run adopts, since it has no producing step for the closure rule below to reach and a run executing another's plan is still a run somebody started. The run-state schema excludes that path from a lineage record for the same reason it constrains the rest of them, and excludes every spelling that case-folds to it, since a copy lands at the path its record names and that path is the run's own request wherever a filesystem folds case — the reading this section already applies to a source run id.

What may be imported together is bounded by what the copies mean. All of a run's imports MUST name one source run: a set drawn from several runs holds artifacts that never descended from one another, which no reader can detect once the headers are rewritten. The source run's recorded `protocol` ([10](#10-run-state)) MUST equal the importing run's — during 0.x a minor version may break the artifact contracts ([11](#11-versioning)), so a mismatch is refused rather than silently adopted, and a migration, where one exists, produces a new artifact rather than an import. The set MUST be closed over derivation: every imported artifact has some producing step whose required inputs — those that are themselves step outputs of the composed workflow, phase sets excepted — are all in the set too, because importing a validation report without the artifact it judged adopts a certificate of something the run does not hold, and the fresh artifact a re-run producer writes is not what the imported report certified. And `from` is a plain directory name, like the run id whose directory it names ([8.1](#81-run-scoped-directories)) — the schema encodes the shape, and the executor applies the same path-safety refusals to it as to a run id it is asked to resume. Whether the source is this run is a fact about directories rather than strings, and the executor MUST decide it by canonical directory identity, compared without following links: case-insensitive filesystems and platform normalization make distinct strings one directory, so string equality misses the self-import it exists to refuse. The schema bars the alias shapes a string itself can carry — a trailing dot or space, which Windows strips, included — and everything past that is the filesystem's to answer, not a comparison's.

Import reaches steps and never gates. A step whose declared output is among the run's imports has nothing left to produce, and its record is populated `skipped` ([10](#10-run-state)) — not terminal there, like every `skipped`, so a route that re-enters it, a gate's `revise` included, runs it on the imported copy as it would on any artifact it is given. The skip holds only while the derivation stays imported: a step is populated `skipped` by import only where every composed step before it whose output its contract declares among its inputs — required or optional, phase sets aside — is itself `skipped`, by import or by the class. Where an upstream producer will run — its output not imported, or its step composed by a class the source run's never ran — the downstream step is populated `pending` although its output already sits in the run directory: the copy stands, [8.3](#83-templates)'s no-overwrite rule hands it to the step as content to work from, and what the step then writes has consumed the fresh input. Skipping regardless would let an imported plan silently ignore an ideation this run produced, certified by an imported validation that saw neither. A gate is a human decision ([7](#7-gates)) and a decision belongs to the run that takes it: no gate outcome is satisfied by an import, whatever the source run decided about the same artifact. The gates on the imported artifacts' path still fire, decide on the copies, and record their outcomes in this run's state — which is what executing an imported plan looks like: the steps that produced brief, ideation, and plan are `skipped`, `intake-approval` reads the imported brief's Routing section and accepts a class for *this* run, `plan-approval` decides on the imported plan, and implementation proceeds under an acceptance this run collected. The intake gate is also where an unfit brief is caught. A brief is importable because it describes the change rather than the run that produced it — the `plan` workflow binds its briefs to that reading — so a brief whose constraints or acceptance criteria are the planning exercise's own would put every later stage against the wrong measure, and a human reading one at `intake-approval` has found a defect: the `revise` routes to the skipped `brief-confirm` like any re-entry ([7](#7-gates)), and the derivation rule above returns what descended from the brief to `pending` with it.

### 8.7 Request

A run starts from a request — a typed instruction, a ticket, an issue, a message thread, a specification — and the first step of every workflow restates it as the brief the rest of the run is measured against ([6.2](#62-intake)). That makes the request an input the run has to hold before its first step runs, and holding it is not something a step can do: nothing precedes the first one to produce it, which is why a workflow whose entry step reached for the request without declaring it was reaching for something no surface carried ([9.1](#91-step-and-handoff)).

The executor MUST materialize the request at `{run}/request.md` when the run is created, before any step runs, and MUST add that path to the manifest ([8.2](#82-manifest)). What the file holds is whatever started the run, recorded as it arrived: the instruction's own text, or the reference a step will fetch through the executing harness's connections where the request is a pointer rather than prose. It has no template ([8.3](#83-templates)) — a request is not authored against a structure, it is what the run was given — and no producing step, so nothing scaffolds it and no step's completion is what puts it in the manifest. A run whose creation cannot land it MUST NOT be created: the entry step declares it required, so a run created without one exists only to block at its first step, and refusing at creation is what keeps the id usable.

It is this run's own in a way the other creation-time mechanism is not. It MUST NOT be imported ([8.6](#86-import)): an import adopts an artifact some step of the source run produced, a request has no producing step for that section's derivation-closure rule to reach, and a run executing another run's plan is still a run somebody started for a reason of its own. Nor is it reachable from the cache ([8.4](#84-grounding-cache)), which is confined to optional inputs. And no step MAY declare it as an `output` — the step schema refuses one that does, and refuses every spelling that case-folds to it: `{run}/REQUEST.md` is a different declaration and the same file wherever a filesystem folds case, and `{run}/requeſt.md` is too, `ſ` upper-casing to `S` in the one-to-one way an upcase table expresses. The reservation is deliberately wider than any single filesystem's table, a name wrongly refused failing loudly where one wrongly allowed would overwrite the request in silence, which is the reading [8.6](#86-import) already applies to a run id — so nothing in the run rewrites it: the request stands unchanged for the run's whole life, which is what lets a gate's `revise` return the run to a step that reads it again and find the same words that started it. A step claiming it would overwrite those words mid-run while the manifest went on saying the request was there, which is the one thing every reader of it relies on.

## 9. Orchestration metadata

All orchestration semantics an author declares live under a single `workflow` key inside a `metadata` mapping. The mapping has two carriers, one shape: the `metadata` extension point of Agent Skills frontmatter, where a skill declares, and a fenced `yaml` block at the top level of a workflow or stage file's body, its fence beginning at the first column — never inside a block quote or a list item — where a file that is not a skill declares: a workflow its trigger, a stage its sequence, its steps' contracts, and its loop contracts. Top-level is a rule, not a habit, and the first column is what makes it checkable: a container puts a marker or an indent on every line the fence carries, three spaces of indentation are legal at top level but so is a list item's content indent, and a declaration surface that had to parse containers to tell the two apart would be a markdown implementation rather than a protocol. One file carries both the prose a plain agent reads and the structure a driver executes, whichever carrier holds it.

Every `metadata.workflow` block MUST carry a `protocol` field declaring the protocol version it was authored against (see [Versioning](#11-versioning)).

### 9.1 Step and handoff

A step declares its role, its input contract, its output, and its state-machine edges:

```yaml
metadata:
  workflow:
    protocol: "0.2"
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

- `inputs` is the handoff contract: each entry names an artifact and whether it is required. A required input that is missing blocks the step. The declaration MUST be complete: a step MUST declare every artifact whose content its instructions depend on — judged by, quoted from, checked against, or assembled out of — because an executor materializes only what is declared. A step whose prose reaches for an artifact it does not declare is unexecutable in the general case, however carefully that prose is written. Completeness is a property of the step's instructions, not of what a particular run produced: an input some risk class skips is declared `required: false`, never omitted. Because an optional input MAY be satisfied from an earlier run ([8.4](#84-grounding-cache)), a step that depends on same-run identity MUST either declare the input required or state the freshness check its prose applies; silence on that point is a defect, not a default. An optional input whose path carries `{P}` is the one exception, and needs no such statement: the cache cannot reach it ([8.4](#84-grounding-cache)), so same-run identity is what resolving it already means.
- `output` names the artifact the step produces and, optionally, the template it is scaffolded from ([8.3](#83-templates)).
- `on` maps each verdict to the next step or gate id. The verdict that routes a step is produced by the validation of that step's output — a `validator` step or machine checks ([3.3](#33-verdicts)) — never by the producing role grading its own work; declaring `on` does not make the step emit verdicts itself. A step MAY omit `on` when its output has no validation, or when a loop contract's exit criteria consume its validation verdict ([9.2](#92-loop-contracts)); it then proceeds to the next step in composition order, the same default that routes a gate's `accept` ([7](#7-gates)). A target is normally a step or gate id; a stage id MAY also stand as a target, resolving to that stage's first step, past any content the run's risk class skips ([6.1](#61-composition)). A declared `on` MUST route at least `PASS` and `FAIL` — machine checks produce only those two — and every verdict its validation can actually produce MUST have an edge (`PASS_WITH_CONDITIONS` wherever a validator is the source); an executor encountering a verdict with neither an edge nor a consuming loop contract MUST stop and escalate rather than guess.

### 9.2 Loop contracts

A looping step or stage declares when it is allowed to exit and what to do when it spins:

```yaml
metadata:
  workflow:
    protocol: "0.2"
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
- `scope` binds the loop to the file scope its plan declared. Where `declared_from` carries `{P}` ([8.1](#81-run-scoped-directories)) it resolves to a plan per phase and the bound scope is their **union**: a loop in a stage that runs after the last phase is bound by every phase it is reviewing, and a file any one of those plans declared is in scope for the whole loop. Intersection would put a file no single phase owned outside the scope of the change that contains it. On drift, `flag` records the signal; `escalate` stops for a human. Either way the signal feeds mid-run reclassification ([5.3](#53-override-and-reclassification)).

### 9.3 Triggers

A workflow entry point declares how it starts:

```yaml
metadata:
  workflow:
    protocol: "0.2"
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

### 9.4 Stage sequence

A stage declares its members — steps and gates — in record order:

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: plan-create
        - step: plan-revise
          conditional: true
        - step: plan-validate
        - gate: plan-approval
```

- `sequence` is **record order, not execution order**: the populated `steps` list ([10](#10-run-state)) follows it verbatim, and resume ([8.5](#85-resume)) is defined over that list, so the ordering obligations [10](#10-run-state) states — a gate-`revise` destination preceding every record the revise invalidates — are authoring obligations on this declaration. That is why `plan-revise` precedes the validator that runs before it. Execution order needs no declaration of its own: statuses and edges carry it — a conditional member is `skipped` until a route reaches it, so a resume passes over its record and lands on the validator's, whatever the record order says.
- Each entry names exactly one member, a `step` or a `gate`, and the sequence MUST name every step and gate the stage declares, each exactly once: an executor populates only what is declared, so a member missing here is a record no run can carry, and one named twice is the duplicate [10](#10-run-state) forbids. Member ids MUST also be unique across all stages, whichever kind each wears where: a workflow concatenates its stages' sequences into one record list ([10](#10-run-state)), any two stages may be composed, and an id two stages share duplicates a record the moment they are. And a member id MUST be distinct from every stage id: a target in [9.1](#91-step-and-handoff) is an untyped string that may name a member or a stage, so a member wearing a stage's id would make every edge naming it ambiguous.
- `conditional: true` marks a member populated `skipped` at entry — reached only when a condition fires or a route returns to it ([10](#10-run-state)): a loop's revising member before a verdict fails, a gate that fires on ambiguity. What a risk class excludes is the overlays' to say, never this declaration's: the sequence is class-independent, and a class's exclusions are applied to it at population.

### 9.5 Degradation

`metadata.workflow` is a degradation-tolerant hint layer:

- A client that does not understand `metadata.workflow` MUST be able to use the skill by ignoring the block entirely and running the body as prose, with the human as executor.
- A client that understands the block partially SHOULD honor what it understands and ignore the rest; unknown top-level keys under `workflow` — siblings of the declared structures — MUST NOT be treated as errors during 0.x. Inside a declared structure (`step`, `loop`, `trigger`, `stage`), unknown keys are authoring errors, and the schemas reject them.
- Degradation works in both directions: a human or harness can replace a driver at any step, and a driver can pick up a run a human advanced, because all state is in artifacts and run state.

## 10. Run state

Runtime state lives in `{run}/workflow-state.yaml`. It has exactly one writer — the executor, which MAY be a human acting as executor ([2](#2-conformance-language-and-terms)) — and MUST NOT be edited by anything else while a run is live. It is runtime state the executor maintains, never a hand-authored source document.

```yaml
run:
  id: 2026-08-03-feature-slug
  workflow: feature
  risk: R2
  risk_rationale: "single module, no security surface, one phase"
  protocol: "0.2" # single-phase run, so no `phase` field
steps: # one record per step and gate of the composed workflow; `intake-approval` populated them (§7)
  - id: brief-confirm
    status: done # pending | active | blocked | done | skipped
  - id: clarifying-question # conditional; it never fired
    status: skipped
  - id: risk-route
    status: done
  - id: intake-approval
    status: done
  - id: ground
    status: done
  - id: ideate
    status: done
  - id: ideate-validate
    status: done
    iterations: 1
    stall_flags: []
  - id: ideate-revise # the loop exited on the first verdict
    status: skipped
  - id: plan-create
    status: done # outside the revise loop, so no iterations
  - id: plan-revise # the revise outcome's destination, and the first entry a resume finds
    status: pending
    iterations: 1 # one revision already run; the cap is the loop's (spec 9.2)
    stall_flags: []
  - id: plan-validate # must re-check what the revision changes
    status: pending
    iterations: 2 # it validated the created plan and the first revision
  - id: plan-approval # decides again; a gate is `done` only where its decision stands
    status: pending
  - id: implement
    status: pending
  - id: implement-validate
    status: pending
  - id: review-code
    status: pending
  - id: review-security # conditional at R2, and the brief records no security surface
    status: skipped
  - id: review-validate
    status: pending
  - id: review-arbitrate # at R2 only on reviewer/validator disagreement
    status: skipped
  - id: review-fix # conditional, like every revising member: the verdict routes to it
    status: skipped
  - id: deliver-prepare
    status: pending
  - id: deliver-validate
    status: pending
  - id: delivery-approval
    status: pending
gates: # every decided gate, not only the latest (§5.3, §7)
  - gate: intake-approval # the decision that accepted the class `run.risk` holds
    transport: inbox
    outcome: accept
    at: 2026-08-03T13:40:00Z
  - gate: plan-approval
    transport: blocking # blocking | inbox
    outcome: revise # accept | revise | reject
    at: 2026-08-03T14:12:00Z
instrumentation: # optional enrichment (tokens, duration) per step
artifacts: # run manifest, see §8.2 — `plan-revise` and `plan-validate` read
  # `pending` above and their outputs are still here: a reset record does not
  # unmake what the step already wrote
  - "{run}/request.md" # what the run was created with, not what a step wrote (§8.7)
  - "{run}/brief.md"
  - "{run}/grounding.md"
  - "{run}/ideation.md"
  - "{run}/ideation-validation.md"
  - "{run}/phase-1-plan.md"
  - "{run}/phase-1-plan-validation.md"
```

- `run` identifies the run: id, workflow, risk class with rationale ([5](#5-risk-classes)), and the protocol version the run executes under.
- `run.risk` and `risk_rationale` MUST be absent before the intake gate accepts a class and present from then on, and they move together. The schema enforces the pairing and not the timing: whether that gate has decided is not visible in this document — gate ids are workflow vocabulary rather than protocol vocabulary, and a clarifying question also records `accept` while no class exists — so the timing is one of the semantics this prose carries for a structure the schema defines. Run state exists before either field: it is created when the run starts, which is what gives a gate reached during intake something to resume from.
- `steps` holds at most one record per step *and per gate*, not one per invocation. A gate is not a Step in the sense [2](#2-conformance-language-and-terms) defines — no role, no skill, no declared output — and it takes an entry here because resume is defined over this list and a gate is something a run stops at ([7](#7-gates)). The field is named for what mostly fills it, not for a claim that everything in it is a step. What follows holds for both: a step that runs again reuses its record and `iterations` counts how many times it has run in the current loop instance — invocations, not re-entries, so a step that has run once carries 1 and the cap in [9.2](#92-loop-contracts) counts the same units it is written in. The list is complete from the intake gate's acceptance onward, and not before: the class that gate accepts is what decides which steps the risk-class overlays skip ([6.1](#61-composition)), so until it has decided, a record for every composed step could not say what its `status` is. Until then the list holds the intake steps alone — the starter fixture models exactly that — and that acceptance is the write that populates the rest, each record entering `pending` or `skipped` by the same reading: `pending` where the run's path reaches the step, `skipped` where the class excludes it, where a condition has yet to fire, or where the run imported the step's declared output with its derivation intact ([8.6](#86-import)) and left it nothing to produce. The list is ordered so that the first entry which is neither `done` nor `skipped` is the next step to run — that is what makes resume ([8.5](#85-resume)) mean anything, and a transition that re-enters steps keeps it true. The order itself is declared, not derived: each stage's sequence ([9.4](#94-stage-sequence)) states its members in exactly this record order, and the populated list is those sequences in stage-composition order. Two things make that ordering well-defined rather than a guess, because more than one record can be neither `done` nor `skipped` at once. `active` is the record of the step currently running, a run has at most one, and a resume returns to it ahead of position: a re-entry invalidates what its output fed by the same write that starts it, so the step running and the validator waiting on it are both un-`done` together, and without that rule the order alone would decide which a resume picked. Position settles what is left, which is a route that makes several records `pending` and starts none of them — a gate `revise` returns the run to one step and invalidates the others in the same write, so its destination MUST precede every record it invalidates. That constraint is not the order a stage introduces its steps in: `plan-approval`'s `revise` returns to `plan-revise` and invalidates `plan-validate`, so the record for the revision comes first, the reverse of the order the planning stage reads in. Each record carries an `id` and a `status` (`pending` | `active` | `blocked` | `done` | `skipped`), and those two are all a record must have. `iterations` appears where the step is inside a loop and has a cap to count against; `stall_flags` where signals have accumulated. A step that has run once outside a loop carries neither, which is why the schema requires neither. Reusing one record per step leaves the run needing to say which phase it is in, and `run.phase` is that: step ids repeat across phases, so a resume reads it to know which `{N}` an artifact path resolves to and which phase's loop an `iterations` count belongs to. It follows the accepted phase list, and every phase-1 `plan-approval` acceptance sets it: to 1 where the accepted list carries more than one phase, since the phase being executed is the one whose plan was just approved, and absent where it carries one. That is a rule about each acceptance rather than only the first, because a phase-1 list can be re-cut after approval where the human authorizes it, and a run accepted as single-phase may become multi-phase or the reverse — a field fixed at the first acceptance would leave `{N}` unresolvable after the second. Before any acceptance nothing knows whether the run has phases, and `{N}` resolves to 1 either way.

Advancing it is a write over the records the new phase repeats, not a counter on its own. The steps a phase runs are `done` from the phase before, and §8.5 skips what is `done` — so a run that only incremented `run.phase` would step over its own planning and implementation and resume in a later stage. Entering a phase therefore returns the steps that phase runs to the status each carries at its stage's entry — `pending` for the ones the path reaches, `skipped` for a conditional member whose condition has not fired in this phase — clears the `iterations` and `stall_flags` they accumulated in the phase before, and sets `run.phase`, in one write: the count is against this phase's loop, and a phase inheriting the last one's would start part-spent. `iterations` counts against the cap of the loop instance it is in, not across the run: a multi-phase workflow repeats a stage per phase ([6.1](#61-composition)), each repetition is its own loop with its own cap ([9.2](#92-loop-contracts)), and the count starts at zero when a phase enters one. Carrying it forward would let a phase that revised twice spend the next phase's allowance, and the caps are per loop precisely so one phase's difficulty is not another's. `blocked` is what a *gate's own* entry wears while it waits on a human — not the entry of the step that produced the artifact, which is `done` by then: it is not `done`, so a resume returns to the gate rather than past it, and blocking the producer instead would re-run the step and never reach the gate ([7](#7-gates), [8.5](#85-resume)). It becomes `done` when its decision stands: an `accept` the run proceeds past, or a `reject` that ends the run. A `revise` is the decision that does not stand — the cycle runs again and this gate decides again — so its entry returns to `pending` with the rest of what the revision invalidates.

`skipped` says the step is not on the run's path as the list currently stands, which covers three cases and is not terminal in any of them. One is a step the accepted risk class excludes, and nothing will route to it. Another is a step whose declared output the run imported with its derivation intact ([8.6](#86-import)): the skip holds only while every upstream producer the step's contract draws on is itself `skipped` — a producer that will run leaves the step `pending` with the copy as working content — and nothing is left to produce, though a route that revises the artifact still reaches it. The third is a step reached only on a condition that has not fired — a loop's revising member before a verdict fails, a gate's conditional branch — and a transition MAY route to such a record, which makes it `active` like any other start. That is what lets the ordering rule above hold: a revising member ordered ahead of the validator whose failure reaches it must not be `pending` before that validator has run, or a resume would return to the revision first and revise an artifact nothing had yet judged. It is `skipped` until the verdict routes to it, which is also how the starter fixtures already read.
- `gates` is the instrumentation record required by [section 7](#7-gates). It is appended in decision order and a gate decided more than once has an entry per decision, so the last entry naming a gate is its latest: a `revise` recorded there is a decision that did not stand, and what says whether one does now is the entry after it, not the presence of any entry at all. A gate a phase repeats decides once per phase, and a decision taken while the run carries `run.phase` MUST name the `phase` it was taken in — without it the entries for that gate are indistinguishable, and a phase's approval could not be told from the phase before's. A decision taken before the run had phases carries none and belongs to no phase, which is not a gap to backfill: a re-cut may turn a single-phase run into a multi-phase one, and it does not reach back into what was already decided. Such an entry stands for no phase's approval, so nothing is lost by leaving it as it was recorded. Which gates those are is a fact about the stage that declares them, not about what its records happen to carry: a stage a phase repeats is one whose steps write per-phase outputs, and reading the requirement off the records instead would let an omitted `phase` decide the field was never required. A gate that decides once per run records none.
- `instrumentation` MAY carry per-step enrichment such as token counts and durations.
- `artifacts` is the run manifest ([8.2](#82-manifest)).
- `imports` is the lineage record [8.6](#86-import) requires: one entry per imported artifact — its `{run}`-relative path (`artifact`), the source run's id (`from`), and when the copy landed (`at`). Present exactly where the run imported and absent otherwise. Every path it names is also in `artifacts`, because the manifest is what readers resolve against — this list says where a copy came from, never whether it counts.

## 11. Versioning

The protocol version is `<major>.<minor>`, declared in every `metadata.workflow` block and in each run's state.

- During `0.x`, any minor version MAY contain breaking changes; that is what the `0` major signals. Breaking changes are recorded in the repository changelog.
- A client SHOULD warn when it encounters a `protocol` value newer than the version it implements, and MUST NOT silently misinterpret structures from a newer major version.
- From protocol version `1.0`, minor versions are backward-compatible additions; breaking changes require a major version.

The repository's release tags use full semantic versioning (`0.1.0`, `1.0.0`, …) and version the whole surface — this specification, the schemas, roles, and workflows — together; the `protocol` field tracks the major and minor components of that release line.
