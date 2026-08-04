---
name: implementation
description: Builds the change within the file scope the plan declares — implementer works from the plan, validator and machine checks gate the loop, scope drift feeds reclassification. Plan defects become structured feedback for plan-revise, never silent scope expansion.
---

# Stage: implementation

Builds the current phase within the scope its plan declares. The loop contract — not step edges — routes this stage: the validation verdict and the machine checks are its exit criteria (spec §9.2), and on exit the run proceeds in composition order.

## Steps

### implement (implementer)

Execute the plan: make the code changes, keep machine checks green, and log what was done — decisions, deviations, evidence — in the implementation log. A plan defect discovered mid-work is structured feedback for `plan-revise` (what is wrong, where, suggested correction), never a license to improvise beyond the declared scope. A loop iteration re-enters this step with the validation findings — declared as an optional input, absent on the first pass.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: implementer
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-validation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-impl-log.md"
```

### implement-validate (validator)

Runs with fresh context in every mode (spec §4). Validates the implementation against the plan: every plan step done, acceptance criteria met, no undeclared scope, machine-check evidence present. Renders the verdict the loop contract consumes.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-impl-validation.md"
```

## Loop

Exit requires both the validation verdict and green machine checks. `{machine-checks}` stands for the project's own verification command — tests, linters, build (spec §5.1) — bound by project configuration, not by this stage.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    loop:
      exit_criteria:
        - artifact: "{run}/phase-{N}-impl-validation.md"
          verdict: PASS
        - command: "{machine-checks}"
      max_iterations: 3
      stall:
        signal: no-artifact-delta
        action: escalate
      scope:
        declared_from: "{run}/phase-{N}-plan.md"
        on_drift: flag
```

## Notes

- `implement` declares no `on`: its verdict is consumed by the loop contract's exit criteria (spec §9.2). In a multi-phase run, exit advances to the next phase's planning until the phase list is exhausted, then to the next stage in composition order.
- A `FAIL` whose findings are plan defects, not implementation defects, is not fixable by iterating: the implementer records the structured feedback in the log, and the loop ends by escalation — stall once the feedback stops producing meaningful deltas, or the cap — putting the human in charge of re-entering planning at `plan-revise` with that feedback.
- Scope drift is flagged, not fatal: the signal feeds mid-run reclassification upward (spec §5.3).
