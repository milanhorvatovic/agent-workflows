---
name: awf-review-fix
description: Applies the review's resolved findings within the plan's declared file scope — the arbiter's resolution list where one exists for this run and iteration, the two review passes' findings and the validator's own otherwise — fixing finding by finding with tests where a finding exposed a gap, keeping machine checks green, and recording each fix, dispute, and escalation in the run's review-fixes artifact for the next iteration to re-review. Triggers as the review stage's review-fix step on every loop iteration that has not exited. A finding whose fix would touch undeclared files becomes a structured finding-for-planning escalated toward awf-plan-revise, never silent scope expansion; executing the plan's own steps is awf-implement, and addressing implementation-validation findings belongs to that stage's loop, not this skill.
license: MIT
metadata:
  workflow:
    protocol: "0.3"
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
        template: references/review-fixes.template.md
---

# Skill: awf-review-fix

Closes the review loop's iteration: the findings the review settled on, applied to the code. The fix list is already decided — the arbiter's resolution where one exists for this run and iteration, the two review passes' findings and the validator's own otherwise — so implementer judgment goes into fixing well, not into re-litigating what the review concluded. The record goes to `{run}/review-fixes.md`, run-scoped like the rest of this stage's outputs, because review runs once after the final phase and has no current phase to index by.

## Role

The step runs as the implementer: minimal, focused changes that fix what the finding names, in the codebase's existing patterns, without drive-by improvements the findings never asked for. The reviewer suggested the fix; the implementer owns its final shape — but owning the shape is not owning the scope, and a finding is never silently skipped.

## Inputs

- `{run}/review-resolution.md` (optional) — the arbiter's resolved list; authoritative only where both the run and the iteration it records match the current ones, refutation and triage having already happened. Two ways a wrong one reaches this step: its path is run-scoped while arbitration is conditional per iteration, so an earlier iteration's file survives into this one; and because the input is optional, spec §8.4 admits a cached resolution from a different run entirely. The template records both identifiers so both can be checked, and a resolution failing either check is not this pass's fix list — taking it as authoritative silently drops everything the current review raised.
- `{run}/review-findings.md` (required) — the code review's findings: part of the working list when no resolution exists, the traceability behind it when one does.
- `{run}/security-findings.md` (optional) — the security pass's findings, where that step ran: the rest of the working list when no resolution folded them in. Usable only when its `Run` and `Iteration` headers both match this pass: the path is run-scoped while the security step is conditional, so a skipped iteration leaves the previous one's report in place, and being optional it may also be cache-satisfied from another run entirely (spec §8.4). A report failing either check is treated as absent, the same guard the arbiter's resolution carries.
- `{run}/review-validation.md` (required) — the verdict and the validator's own `F-…` findings, which are part of the working list whenever no current-iteration resolution folded them in: the verdict can fail on what both passes missed, and a list blind to those findings would iterate to the cap without ever clearing the one that blocked. Required rather than optional for two reasons — `review-validate` runs immediately before this step in every class where the review stage runs at all, so the artifact always exists; and an optional input MAY be satisfied from an earlier run (spec §8.4), which would let a stale verdict stand in for this iteration's and recreate exactly the blindness this input closes.
- `{run}/phase-{P}-plan.md` (required) — the file-scope declaration every fix is bound to (spec §9.2). The review stage runs once after the final phase, so the path takes `{P}`, one artifact per completed phase (spec §8.1): the change under review is the sum of them, and the scope binding this step is the union of what their plans declare. A fix inside phase 2's scope is in scope even when phase 4 was the last one planned.
- The project's coding and testing standards, where they exist — the same rules the implementation followed, applied to every fix and every test a finding forces. A fix written outside them trades one finding for another on the next iteration.

## Method

Work the list in severity order, criticals first. For each finding: read the code it names in context, apply the fix — the suggested one where it holds up, a better-shaped equivalent where the suggestion meets reality poorly — and add or strengthen tests where the finding exposed an untested path; a fixed bug without a covering test is the same bug waiting to return. Run the affected tests as each fix lands and the project's verification command (`{machine-checks}`, spec §9.2) at checkpoints; commit in the project's format, each commit leaving the tree working.

The plan's file scope binds this step exactly as it bound `implement`. A finding whose fix requires touching an undeclared file is not fixed partially into scope and not expanded into silently: it is recorded as a structured finding-for-planning (stable `P-…` id — step affected, issue, impact, proposed alternatives) for escalation toward `plan-revise`, and the rest of the list proceeds.

A finding that cannot be applied as resolved — the fix breaks something the review did not see, or the finding misreads code the resolution did not check — is recorded as disputed, with the evidence, and left for the next iteration's review to see with fresh eyes. Deciding the dispute is the review's job, not this step's; the one wrong move is dropping it quietly.

## Output

The primary output is the fixed change: code and tests in the working tree, committed. The secondary output is `{run}/review-fixes.md`, scaffolded from `references/review-fixes.template.md` (spec §8.3): one subheading per iteration this step runs, the first included, so iterations stay separable without a reader inferring where one ended. Per finding, the id and what changed in response with the tests that came with it; disputed findings with the evidence for the dispute; findings-for-planning under their `P-…` ids.

The header carries three fields, all refreshed on every iteration rather than written once. **Run** identifies the run, as every artifact's does. **Phases covered** lists the completed phases whose plans bound this stage's scope, which is what makes the union this step worked inside checkable by a reader rather than reconstructable only from the plans. **Iteration** is the loop iteration that last wrote the artifact, and it is what the next pass reads to know whether the fixes below are this iteration's or the previous one's — the same run-and-iteration guard the security report and the arbiter's resolution carry, stated here because this artifact is now the one the loop's other steps read across iterations.

The artifact is run-scoped rather than phase-indexed because this stage is. Review runs once after the final phase, so there is no current phase for a `phase-{N}-` path to name, and the run's other four review artifacts are already run-scoped. This step therefore does not append to any phase's implementation log, and no longer declares one: appending was the only thing its instructions used it for.

Machine-check evidence and the commits this loop produced are refreshed in place in their own sections of this artifact rather than restated under each iteration's fixes, so the next iteration reads one current answer to "do the checks pass" instead of one per loop. That is the property the implementation log used to provide for this step, kept by moving it rather than dropped. One consequence of refreshing them belongs with the loop rather than with this step: the stage's stall signal is `no-artifact-delta`, which spec §9.2 defines as no *meaningful* output change between iterations, and these two sections change on every iteration whether or not anything was fixed. The meaningful delta is in **Fixes** and **Disputed** — an iteration that adds no fix and resolves no dispute has stalled, however many commits it produced.

The loop contract consumes what follows: the next iteration re-reviews the updated change, and the stage exits on a PASS verdict with green machine checks or escalates at the cap (spec §9.2).
