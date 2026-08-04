---
name: ideation
description: Explores the solution space before planning — analyst grounding, three to five distinct approaches with a recommendation, adversarial validation, and a capped revise loop. Outputs grounding and ideation artifacts; the validation verdict routes into planning.
---

# Stage: ideation

Explores the solution space before committing to a plan: ground the problem in the codebase, generate distinct approaches, recommend one, validate the exploration. Composed by `feature` and `plan`; risk-class participation per [overlays](../overlays.md).

## Steps

### ground (analyst)

Analyze the codebase areas the brief touches: structure, patterns, dependencies, and constraints relevant to the problem. This artifact is the run's grounding; later steps declare it as a cacheable input (spec §8.4).

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/grounding.md"
```

### ideate (planner)

Generate three to five genuinely distinct approaches — advantages, risks, codebase impact — and recommend one with rationale. Distinct means different shapes of solution, not variations on one idea.

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
      output:
        artifact: "{run}/ideation.md"
      on:
        PASS: planning
        PASS_WITH_CONDITIONS: ideate-revise
        FAIL: ideate-revise
```

### ideate-validate (validator)

Runs with fresh context in every mode (spec §4). Validates the ideation against the brief: are the approaches distinct and feasible, the risks honest, the recommendation grounded in the evidence? Renders the verdict that routes `ideate`.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/ideation.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/ideation-validation.md"
```

### ideate-revise (planner)

Addresses the validation findings and rewrites the ideation artifact; re-validated by `ideate-validate` under the loop contract.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/ideation.md"
          required: true
        - artifact: "{run}/ideation-validation.md"
          required: true
      output:
        artifact: "{run}/ideation.md"
      on:
        PASS: planning
        PASS_WITH_CONDITIONS: ideate-revise
        FAIL: ideate-revise
```

## Loop

The revise loop (`ideate-validate` → `ideate-revise`) exits only on a passing validation; the cap is an instrumented default, not doctrine.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    loop:
      exit_criteria:
        - artifact: "{run}/ideation-validation.md"
          verdict: PASS
      max_iterations: 3
      stall:
        signal: no-artifact-delta
        action: escalate
```

## Notes

- `PASS: planning` targets the next stage: a stage id as an edge target resolves to that stage's first step, past any overlay-skipped content ([overlays](../overlays.md)).
- No gate: the exploration is validated, not approved — the human's directional decision arrives at `plan-approval` (spec §5.1).
