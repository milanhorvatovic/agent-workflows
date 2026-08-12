---
name: planning
description: Produces the phase plan — planner creates from brief, grounding, ideation, and the phase list the phase-1 plan authored and plan-approval fixed; validator renders the verdict; a capped revise loop converges; the blocking plan-approval gate collects the human decision. Every plan declares its file scope, the contract implementation loops bind to.
---

# Stage: planning

Turns the brief (and, where ideation ran, the recommended approach) into a validated, human-approved plan for the current phase. `{N}` is the current phase number, starting at 1; the phase-1 plan authors the phase list and `plan-approval` fixes it for the run, and a multi-phase run repeats planning → implementation per phase.

All three steps declare that phase-1 plan as an input, because all three are bound by the list it authors: `plan-create` optionally, since at phase 1 the artifact is the step's own output and cannot precede it, and `plan-validate` and `plan-revise` as required, since wherever they run it already exists — at phase 1 as the artifact they are working on, later as the plan that made a later phase possible.

Every plan MUST declare its file scope — the files and modules the phase may touch. That section is the contract the implementation loop binds to (spec §9.2).

## Steps

### plan-create (planner)

Create the phase plan: steps, dependencies, acceptance criteria, file scope, risks, and open questions. Where ideation ran, the recommended approach is the plan's starting point, not a suggestion to re-litigate. At phase 1 this step authors the phase list — `plan-approval` is what fixes it, so direction at that gate can still move it and a revision afterwards cannot; after phase 1 the list bounds what this plan may own, and a phase-1 plan that cannot be read is an escalation rather than a decomposition to invent again.

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
          required: false
        - artifact: "{run}/ideation.md"
          required: false
        - artifact: "{run}/phase-1-plan.md"
          required: false
        - artifact: "{run}/phase-{P}-impl-validation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-plan.md"
      on:
        PASS: plan-approval
        PASS_WITH_CONDITIONS: plan-revise
        FAIL: plan-revise
```

### plan-validate (validator)

Runs with fresh context in every mode (spec §4). Adversarial validation of the plan against the brief: completeness, internal consistency, feasibility, file-scope accuracy, cross-phase impact. Renders the verdict that routes `plan-create`.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/phase-1-plan.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-validation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-plan-validation.md"
```

### plan-revise (planner)

Addresses the validation findings — and any structured feedback escalated from implementation — then rewrites the plan; re-validated by `plan-validate` under the loop contract. The phase list is provisional until `plan-approval` fixes it: before then a validation finding this loop accepts, or the human's direction at that gate, may move it — which is what lets the loop correct a decomposition the validator found wrong. Once it is fixed, a revision that cannot stay inside it escalates to the human instead of quietly rewriting the run's shape, and so does direction blocked by anything other than the list itself.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-plan-validation.md"
          required: true
        - artifact: "{run}/phase-1-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: false
        - artifact: "{run}/phase-{P}-impl-validation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-plan.md"
      on:
        PASS: plan-approval
        PASS_WITH_CONDITIONS: plan-revise
        FAIL: plan-revise
```

## Loop

The revise loop (`plan-validate` → `plan-revise`) exits only on a passing validation; the cap is an instrumented default.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    loop:
      exit_criteria:
        - artifact: "{run}/phase-{N}-plan-validation.md"
          verdict: PASS
      max_iterations: 4
      stall:
        signal: no-artifact-delta
        action: escalate
```

## Gates

- **plan-approval** — after a passing validation. Transport per risk class ([overlays](../overlays.md)); blocking wherever planning runs. Outcomes: `accept` proceeds to the next stage in composition order, and where the accepted list places phases after this one the run enters the next phase and this stage repeats, `run.phase` advancing with it (spec §10) — after the phases before it were implemented, and their decisions reach it as code rather than as a document, `plan-create` reading the tree those phases left. What carries them is declared: all three steps of this stage take `{run}/phase-{P}-impl-validation.md`, one report per earlier phase (spec §8.1), so a binding an earlier phase set — a rollout order, a migration step — reaches the plan and the validation that checks it rather than only the tree. The earlier phase's *plan* still travels no further than the phase-1 list, which is the decomposition rather than the decisions. In the `plan` workflow planning is the final stage and nothing is built between phases, so that carrier is absent too and `accept` completes the run with the phase-1 plan and the list it authored, later phases being planned by the run that executes them; `revise` returns to `plan-revise` — an explicit edge overriding the spec §7 default of returning to the step that produced the artifact, because a plan that passed validation on its first pass was produced by `plan-create`, and sending a human's direction there returns an existing plan to the step that writes one from scratch; revision is surgery on the plan the gate read, which is `plan-revise`'s whole contract, and it already declares every input this route needs — carrying the human's decisions and answers, recorded in the plan's **Gate direction** section before the outcome rather than in the gate record (spec §7), and carried from there into the revised plan, with the revision's feedback audit repeating it as working detail; `reject` ends the run, at every phase and whether or not this gate has accepted a list. Before acceptance there is nothing else it could do — the list is provisional, nothing names a next phase, and there is no `run.phase` to advance (spec §10). After acceptance the phase branch spec §7 allows would need what an executor here cannot establish: the list states which phases must complete before which others, so ending only the rejected phase is sound only where nothing after it depends on that phase, and the list records its sequencing as prose rather than as structure. Dropping a phase from a run that continues is direction on a `revise`, which the phase-1 plan can act on, rather than a `reject`.
