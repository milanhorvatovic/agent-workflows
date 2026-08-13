---
name: awf-review-validate
description: Adversarially validates the implemented change in light of the review findings — does it meet the brief and plan it descends from, and do open findings block? — verifying the findings' claims against the diff, weighing a previous iteration's disputed findings as the open findings they still are, hunting what the passes missed, and rendering exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report the review loop consumes. Triggers as the review stage's review-validate step, fresh-context in every mode, after the review passes write their findings. It renders the verdict and never fixes anything; disagreement between its verdict and the findings is awf-review-arbitrate's to resolve, and the step-by-step check of implementation against plan was awf-implement-validate.
license: MIT
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
        template: references/validation-report.template.md
---

# Skill: awf-review-validate

Renders the verdict on the reviewed change: is it fit to leave the review stage? The reviewers reported findings without concluding; this step concludes. The verdict weighs the change and the findings together — a change can fail on what the reviewers found, on what they missed, or on evidence the log cannot produce — and it gates the review loop (spec §9.2), so it must be earned, not assumed from a quiet findings table.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Independent judgment is the mandate — the reviewer's findings are input, not instruction — but identify and report only: never fix, never re-plan, and never turn this into a second full review pass; the dimensions were the reviewers' sweep, the verdict is this step's.

## Inputs

- `{run}/review-findings.md` (required) — the code review's findings, `R-…` ids.
- `{run}/security-findings.md` (optional) — the security pass's findings, `S-…` ids, present in the classes and conditions where that step runs. Usable only when its `Run` and `Iteration` headers both match this pass: the path is run-scoped while the security step is conditional, so a skipped iteration leaves the previous one's report in place, and being optional it may also be cache-satisfied from another run entirely (spec §8.4). A report failing either check is treated as absent, the same guard the arbiter's resolution carries.
- `{run}/phase-{P}-impl-log.md` (required) — the implementer's account: machine-check evidence, commits, deviations declared. This stage runs once after the final phase, so the path takes `{P}` — one artifact per completed phase (spec §8.1) — rather than the `{N}` of a stage that names the phase it is executing: one log per phase, every one read.
- `{run}/phase-{P}-plan.md` (required) — the acceptance criteria and file-scope declaration the change is judged against, and through its brief link the run's intent. `{P}` again, and it has to: a verdict on the change is a verdict on the sum of the phases, so criteria owned by an earlier phase are part of the bar.
- `{run}/review-fixes.md` (optional) — the previous iteration's fixes and, decisively, its disputes, plus the loop's current machine-check result and commits, refreshed in place there rather than in a phase's log. Optional because it does not exist on the first iteration. Optional makes it reachable by §8.4's cache, so the freshness half of the same rule binds: usable only where its `Run` header matches this run, a fix record from another run describing another change entirely, and its **Iteration** read to confirm it is the previous iteration's record rather than one left behind by an earlier run's loop. A finding the fixer disputed rather than applied is still open, and a verdict rendered without seeing the dispute passes over an unresolved finding while believing it was fixed — the one failure this input exists to prevent.
- The change itself, read directly — the diff is ground truth for every claim weighed here, the findings' claims included.
- The project's coding, architecture, and testing standards, and its review checklist where one exists — what the report's Standards checklist row is checked against, and what separates a real standards violation from a reviewer's stylistic preference when weighing a finding's claim. An argued departure is judged on the argument; a silent one stands as a violation.

## Method

Establish what the change claims to be from the log and its plan, then judge whether it holds: acceptance criteria met by the code as it stands, the log's claims supported by the diff, machine-check evidence present, current, and green — absent, stale, or failing evidence blocks PASS regardless of what else is true.

Then disposition every open finding: for each critical and major, verify its claim against the diff and decide whether it blocks. A finding the diff does not support is marked contested with the evidence, never silently dropped — a passing verdict over unresolved criticals, or a contested failure, is exactly the disagreement that triggers `review-arbitrate`. Verified criticals force FAIL; verified majors force at least PASS_WITH_CONDITIONS with each one a named condition.

Last, hunt omissions: gaps the passes left — an uncovered dimension, an unreviewed file, an obvious defect in plain sight. What surfaces becomes the validator's own findings under `F-…` ids in this report; it does not get injected back into the reviewers' artifacts.

The checklist appends rows for findings disposition and machine-check evidence below the core eight.

## Output

Write the report to `{run}/review-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every own finding carries its `F-…` id, its severity — the section it sits under, and what the verdict turns on — and the shared block's location, issue, impact, and recommendation, citing its evidence inside those rather than in a field of its own — the block defines none, and inventing one here is the defect this step reports in others; questions are separated from findings, blocking from non-blocking.

Append one section, **Dispositions**, above the findings: one row per open `R-…` and `S-…` finding, whatever its severity — the source id, whether the diff upheld or contested it, the evidence either way, and whether it blocks. Every open finding gets a row, so the arbiter inventorying them by id finds none missing. The verification effort is graded, not the coverage, so the status has three values rather than two: a critical or major is checked against the diff and comes back **upheld** or **contested**, with the evidence either way, and can block; a minor or suggestion comes back **recorded**, carried at the severity its source gave it, never blocking, its evidence cell saying that this pass did not adjudicate it. A row is never left without a status it can truthfully take. It is a table rather than a checklist row because a disposition is a per-finding result and not a boolean: the appended disposition row records that the pass happened, this records what it concluded. `review-arbitrate` declares this artifact as its input for exactly these dispositions and contested findings, so a contest recorded only in prose is one the arbiter has no reliable place to read — and a contested critical is precisely the disagreement that fires that step.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3). The loop contract consumes it together with green machine checks: both green exits the stage toward delivery, anything else routes through `review-arbitrate` where the disagreement conditions hold, and into `review-fix` within the iteration cap.
