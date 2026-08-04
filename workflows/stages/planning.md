---
name: planning
description: Produces the phase plan — planner creates from brief, grounding, and ideation; validator renders the verdict; a capped revise loop converges; the blocking plan-approval gate collects the human decision. Every plan declares its file scope, the contract implementation loops bind to.
---

# Stage: planning

Turns the brief (and, where ideation ran, the recommended approach) into a validated, human-approved plan for the current phase. `{N}` is the current phase number, starting at 1; the phase-1 plan fixes the phase list, and a multi-phase run repeats planning → implementation per phase.

Every plan MUST declare its file scope — the files and modules the phase may touch. That section is the contract the implementation loop binds to (spec §9.2).

## Steps

### plan-create (planner)

Create the phase plan: steps, dependencies, acceptance criteria, file scope, risks, and open questions. Where ideation ran, the recommended approach is the plan's starting point, not a suggestion to re-litigate.

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
      output:
        artifact: "{run}/phase-{N}-plan-validation.md"
```

### plan-revise (planner)

Addresses the validation findings — and any structured feedback escalated from implementation — then rewrites the plan; re-validated by `plan-validate` under the loop contract.

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

- **plan-approval** — after a passing validation. Transport per risk class ([overlays](../overlays.md)); blocking wherever planning runs. Outcomes route by the spec §7 defaults: `accept` proceeds to the next stage in composition order (in the `plan` workflow, planning is the final stage, so `accept` completes the run); `revise` returns to the step that produced the gated artifact — `plan-create`, or `plan-revise` once revisions have run; `reject` ends the run — or the phase, in multi-phase runs.
