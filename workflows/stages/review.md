---
name: review
description: Fresh-context review of the implemented change — reviewer findings (code, performance, conditional security), independent validator verdict, arbiter synthesis on disagreement, implementer fixes under a capped loop bound to the plan's scope.
---

# Stage: review

Independent scrutiny of the implemented change. Reviewer and validator always run with fresh context (spec §4) — fresh eyes are the point. The reviewer reports findings and renders no verdict; the validator renders the verdict; the arbiter resolves disagreement between them. The loop contract routes the stage (spec §9.2).

## Steps

### review-code (reviewer)

Review the full change — the diff, against the plan — for correctness, error handling, edge cases, performance, and standards adherence. Findings with severities and concrete fixes; no verdict. Both inputs are required: review only runs in classes where planning and implementation have produced them.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/review-findings.md"
```

### review-security (reviewer)

Security-focused pass: auth, crypto, input handling, dependency changes, data exposure, error paths. Participation per risk class ([overlays](../overlays.md)); recorded `skipped` where it does not run.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/security-findings.md"
```

### review-validate (validator)

Independent verdict on the change in light of the findings: does it meet the brief and plan, and do any open findings block? Renders the verdict the loop contract consumes.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/security-findings.md"
          required: false
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/review-validation.md"
```

### review-arbitrate (arbiter)

Runs when the reviewer's findings and the validator's verdict disagree — a passing verdict over unresolved critical findings, or a contested failure — and always at R3. Dedupes, triages, refutes before accepting, and resolves each finding into a single actionable list; otherwise recorded `skipped`.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: arbiter
      inputs:
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/review-validation.md"
          required: true
        - artifact: "{run}/security-findings.md"
          required: false
      output:
        artifact: "{run}/review-resolution.md"
```

### review-fix (implementer)

Runs when the loop has not exited: applies the resolved findings (the arbiter's list where one exists, the reviewer's otherwise) within the plan's declared scope, updates the implementation log, and keeps machine checks green; otherwise recorded `skipped`. The next iteration re-reviews the updated change.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: implementer
      inputs:
        - artifact: "{run}/review-resolution.md"
          required: false
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-impl-log.md"
```

## Loop

Each iteration runs the steps above in composition order, skipping what its conditions do not trigger.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    loop:
      exit_criteria:
        - artifact: "{run}/review-validation.md"
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

- No gate: review converges by verdict, and the human decision arrives at `delivery-approval`. Escalation paths are the loop's cap and stall action.
- No step declares `on`: the stage's verdict is consumed by the loop contract's exit criteria (spec §9.2); on exit the run proceeds in composition order.
