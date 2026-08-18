---
name: review
description: Fresh-context review of the implemented change — reviewer findings (code, performance, conditional security), independent validator verdict, arbiter synthesis on disagreement, implementer fixes under a capped loop bound to the plan's scope.
---

# Stage: review

Independent scrutiny of the implemented change. Reviewer and validator always run with fresh context (spec §4) — fresh eyes are the point. The reviewer reports findings and renders no verdict; the validator renders the verdict; the arbiter resolves disagreement between them. The loop contract routes the stage (spec §9.2).

This stage runs **once, after the final phase** ([feature](../feature.md)), so it has no current phase to name. Its step blocks read the phases behind it with `{P}` (spec §8.1), which resolves to one artifact per completed phase: a multi-phase run has a plan and a log per phase, the change under review is their sum, and every one is read — the same token the other after-the-last-phase stage uses. The loop's declared scope is the union of what those plans declare. For the same reason nothing this stage writes is phase-indexed: `review-fix` records its iterations in the run-scoped `{run}/review-fixes.md`, alongside the four stage outputs that were already run-scoped.

The sequence (spec §9.4) declares the members in record order — the conditional members sit where composition reads them, their conditions being the loop, the disagreement between reviewer and validator, and the security reading the brief records; what the overlays make mandatory at R3 they make mandatory at population, never here:

```yaml
metadata:
  workflow:
    protocol: "0.2"
    stage:
      sequence:
        - step: review-code
        - step: review-security
          conditional: true
        - step: review-validate
        - step: review-arbitrate
          conditional: true
        - step: review-fix
          conditional: true
```

## Steps

### review-code (reviewer)

Review the full change — the diff, against the plan — for correctness, error handling, edge cases, performance, and standards adherence. Findings with severities and concrete fixes; no verdict. The plan and log are required: review only runs in classes where planning and implementation have produced them. `{run}/review-fixes.md` is optional because it does not exist on the first iteration — from the second it carries what the previous pass fixed and, more importantly, what it disputed rather than fixed, which this pass is meant to decide with fresh eyes. Optional puts it in reach of §8.4's cache, so both steps that take it state the freshness check spec §9.1 requires: its `Run` header must match this run, and its **Iteration** says which iteration wrote it.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{P}-plan.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/review-fixes.md"
          required: false
      output:
        artifact: "{run}/review-findings.md"
```

### review-security (reviewer)

Security-focused pass: auth, crypto, input handling, dependency changes, data exposure, error paths. Participation per risk class ([overlays](../overlays.md)); recorded `skipped` where it does not run. The brief is a declared input because this step also settles the security-surface reading `risk-route` recorded there: spec §5.2 makes any such signal propose at least R2 *and* enable security review, and this is the step that holds that reading against the code rather than against the brief it was made from.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/security-findings.md"
```

### review-validate (validator)

Independent verdict on the change in light of the findings: does it meet the brief and plan, and do any open findings block? Renders the verdict the loop contract consumes. The plan is a declared input because the verdict judges against its acceptance criteria and file scope — an executor materializing only declared inputs must still provide it. `{run}/review-fixes.md` is optional for the same reason it is on `review-code`, and needed for the same one: a finding the previous iteration disputed rather than fixed is still open, and a verdict that cannot see the dispute passes over it.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: validator
      inputs:
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/security-findings.md"
          required: false
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{P}-plan.md"
          required: true
        - artifact: "{run}/review-fixes.md"
          required: false
      output:
        artifact: "{run}/review-validation.md"
```

### review-arbitrate (arbiter)

Runs when the reviewer's findings and the validator's verdict disagree — a passing verdict over unresolved critical findings, or a contested failure — and always at R3. Dedupes, triages, refutes before accepting, and resolves each finding into a single actionable list; otherwise recorded `skipped`.

```yaml
metadata:
  workflow:
    protocol: "0.2"
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

Runs when the loop has not exited: applies the resolved findings (the arbiter's list where one exists for this run and iteration, otherwise both review passes' findings — the security pass's where it ran — together with the validator's own) within the plan's declared scope, records what it did in `{run}/review-fixes.md`, and keeps machine checks green; otherwise recorded `skipped`. The next iteration re-reviews the updated change. It writes a run-scoped artifact of its own rather than appending to a phase's implementation log: this stage has no current phase, so a phase-indexed output has no defined target once the run has more than one phase — and it no longer declares that log as an input either, appending to it having been the only thing its instructions used it for. The security report is usable only where its `Run` and `Iteration` headers match this pass — its path is run-scoped while the security step is conditional, so a skipped iteration leaves the previous report behind, and an optional input may also be cache-satisfied from another run (spec §8.4). The validation report is required rather than optional: it carries the validator's own findings, which reach this step no other way when arbitration is skipped, and an optional input MAY be satisfied from an earlier run (spec §8.4) — a stale verdict standing in for this iteration's is the failure the declaration exists to prevent.

```yaml
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: implementer
      inputs:
        - artifact: "{run}/review-resolution.md"
          required: false
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/security-findings.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: true
        - artifact: "{run}/phase-{P}-plan.md"
          required: true
      output:
        artifact: "{run}/review-fixes.md"
```

## Loop

Each iteration runs the steps above in composition order, skipping what its conditions do not trigger.

```yaml
metadata:
  workflow:
    protocol: "0.2"
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
        declared_from: "{run}/phase-{P}-plan.md"
        on_drift: flag
```

## Notes

- No gate: review converges by verdict, and the human decision arrives at `delivery-approval`. Escalation paths are the loop's cap and stall action.
- No step declares `on`: the stage's verdict is consumed by the loop contract's exit criteria (spec §9.2); on exit the run proceeds in composition order.
