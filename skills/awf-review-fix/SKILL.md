---
name: awf-review-fix
description: Applies the review's resolved findings within the plan's declared file scope — the arbiter's resolution list where one exists, both review passes' findings otherwise — fixing finding by finding with tests where a finding exposed a gap, keeping machine checks green, and recording each fix in the phase's implementation log for the next iteration to re-review. Triggers as the review stage's review-fix step on every loop iteration that has not exited. A finding whose fix would touch undeclared files becomes a structured finding-for-planning escalated toward awf-plan-revise, never silent scope expansion; executing the plan's own steps is awf-implement, and addressing implementation-validation findings belongs to that stage's loop, not this skill.
license: MIT
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
        - artifact: "{run}/security-findings.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-impl-log.md"
---

# Skill: awf-review-fix

Closes the review loop's iteration: the findings the review settled on, applied to the code. The fix list is already decided — the arbiter's resolution where one exists, both review passes' findings otherwise — so implementer judgment goes into fixing well, not into re-litigating what the review concluded.

## Role

The step runs as the implementer: minimal, focused changes that fix what the finding names, in the codebase's existing patterns, without drive-by improvements the findings never asked for. The reviewer suggested the fix; the implementer owns its final shape — but owning the shape is not owning the scope, and a finding is never silently skipped.

## Inputs

- `{run}/review-resolution.md` (optional) — the arbiter's resolved list; where present it is authoritative, refutation and triage having already happened.
- `{run}/review-findings.md` (required) — the code review's findings: part of the working list when no resolution exists, the traceability behind it when one does.
- `{run}/security-findings.md` (optional) — the security pass's findings, where that step ran: the rest of the working list when no resolution folded them in.
- `{run}/review-validation.md` (optional) — the validator's own `F-…` findings, for the same reason and by the same route: the verdict can fail on what both passes missed, arbitration runs only on disagreement and at R3, and a working list blind to those findings would iterate without ever clearing the one that blocked. Where a resolution exists it has already folded them in.
- `{run}/phase-{N}-plan.md` (required) — the file-scope declaration every fix is bound to (spec §9.2).
- `{run}/phase-{N}-impl-log.md` (required) — the log this step appends its record to.
- The project's coding and testing standards, where they exist — the same rules the implementation followed, applied to every fix and every test a finding forces. A fix written outside them trades one finding for another on the next iteration.

## Method

Work the list in severity order, criticals first. For each finding: read the code it names in context, apply the fix — the suggested one where it holds up, a better-shaped equivalent where the suggestion meets reality poorly — and add or strengthen tests where the finding exposed an untested path; a fixed bug without a covering test is the same bug waiting to return. Run the affected tests as each fix lands and the project's verification command (`{machine-checks}`, spec §9.2) at checkpoints; commit in the project's format, each commit leaving the tree working.

The plan's file scope binds this step exactly as it bound `implement`. A finding whose fix requires touching an undeclared file is not fixed partially into scope and not expanded into silently: it is recorded as a structured finding-for-planning in the log (stable `P-…` id — step affected, issue, impact, proposed alternatives) for escalation toward `plan-revise`, and the rest of the list proceeds.

A finding that cannot be applied as resolved — the fix breaks something the review did not see, or the finding misreads code the resolution did not check — is recorded in the log as disputed, with the evidence, and left for the next iteration's review to see with fresh eyes. Deciding the dispute is the review's job, not this step's; the one wrong move is dropping it quietly.

## Output

The primary output is the fixed change: code and tests in the working tree, committed. The secondary output is the updated `{run}/phase-{N}-impl-log.md` — this iteration's record written to the log's **Review fixes** section, which the log's template defines for this step: each finding id with what changed in response and the tests that came with it, and disputed findings with the evidence for the dispute. Machine-check evidence and commits are refreshed in the log's own sections for them rather than restated under the fixes, so the next iteration reads one current answer to "do the checks pass" instead of one per loop. The log stays the honest account the next review iteration re-reads.

The loop contract consumes what follows: the next iteration re-reviews the updated change, and the stage exits on a PASS verdict with green machine checks or escalates at the cap (spec §9.2).
