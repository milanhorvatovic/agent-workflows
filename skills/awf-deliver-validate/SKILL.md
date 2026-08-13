---
name: awf-deliver-validate
description: Adversarially validates the run's delivery artifact against the brief — are the acceptance criteria actually met by the shipped change, is the artifact accurate about what shipped and honest about what did not, is every claimed verification evidenced rather than asserted? — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, as the run's last, in a structured validation report. Triggers as the delivery stage's deliver-validate step, fresh-context in every mode, after awf-deliver-prepare writes the artifact; the risk-class overlays skip it at R1, where machine checks and the gate stand in, and at R0, where the stage is a free-form exit note with no gate at all. It identifies issues and never fixes them — correcting the artifact is awf-deliver-prepare's on a gate revise outcome — and its verdict does not gate the run, every verdict routing instead to the delivery-approval gate where the human decides with it in view.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: validator
      inputs:
        - artifact: "{run}/delivery.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-validation.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
        - artifact: "{run}/review-fixes.md"
          required: false
        - artifact: "{run}/phase-{P}-plan.md"
          required: false
      output:
        artifact: "{run}/delivery-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-deliver-validate

The run's final check, and the last chance to catch a change that does not do what was asked. Two questions decide the verdict: does the shipped change meet the brief, and does the delivery artifact tell the truth about it? An artifact that reads well over a change that misses a criterion is the failure mode this step exists to catch — so the artifact is the subject, never the authority.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never fix the artifact, never edit the change, never ship anything. Unlike the verdicts of the stage validators before it, this one routes nowhere but the gate: it does not block delivery on its own, which makes accuracy the whole job. A FAIL that a human overrides at the gate has still done its work; a PASS that flattered the artifact has not.

## Inputs

- `{run}/delivery.md` (required) — the artifact under validation, read in full before judging: its summary, change list, acceptance-criteria table, verification evidence, and change description.
- `{run}/brief.md` (required) — the bar. Its goal, constraints, and acceptance criteria are what "delivered" means; criteria are walked one by one, never sampled.
- `{run}/phase-{P}-impl-log.md` (required) — where the artifact's evidence claims come from: machine-check results, commits, declared deviations. A multi-phase run has one log per phase and every one is read; a claim sourced from a log is checked against that log and then against the diff.
- `{run}/review-fixes.md` (optional) — the same evidence for the review loop, which `review-fix` refreshes in place there: the commits that loop produced and its current machine-check result. Optional on two counts: the review stage is skipped at R0 and R1, and even where it runs, `review-fix` only runs on an iteration the loop has not exited — so a review that passes on its first pass produces no fix record at all. Optional makes it reachable by §8.4's cache, so the freshness check binds here too: usable only where its `Run` header matches this run, and its **Iteration** is the loop's last — an earlier run's fix record would supply commits and a check result belonging to a different change. It matters most to this step of all of them: stale machine-check evidence is one of the things a delivery verdict must call out, and where a review loop ran, the implementation logs *are* the stale copy — checking a "checks pass" claim against them alone would confirm it from evidence predating every fix the review forced.
- `{run}/phase-{P}-impl-validation.md` and `{run}/review-validation.md` (optional) — the verdicts the artifact quotes. Optional not because this step ever runs without a validator upstream by design, but because reclassification applies the new class's defaults to subsequent steps only (spec §5.3): a run bumped upward mid-implementation reaches this step with no implementation validation behind it. Absent is therefore a fact to check the artifact against, and never satisfied from another run — the grounding cache of spec §8.4 does not apply to a record of this run. Where they exist, they are what the artifact's verdict claims and conditions are checked against; the artifact's own word is never the source.
- `{run}/phase-{P}-plan.md` (optional) — the same plans `deliver-prepare` reads, and for the same reason: the rollback path it reports is worked out in each plan's **Rollback** section, so without them a truthfully assembled rollback claim would trace to nothing this step holds and be reported unsupported. Optional on the same terms, planning being skipped at R0 and R1. Never satisfied from another run — a plan whose `Run` header names a different one is treated as absent, since the grounding cache of spec §8.4 does not apply to a record of this run.
- The change itself, read directly — the diff, its tests, and the machine-check evidence are ground truth for every claim the artifact makes. Where the diff and the artifact disagree, the diff wins and the disagreement is a finding.
- The project's rendered PR or change-note standard, where one exists — the shape the change description is held to, and what the report's Standards checklist row is checked against; the same standard `deliver-prepare` wrote against.

## Method

Walk the brief's acceptance criteria one at a time and verify each against the change, not against the artifact's table: find the code that satisfies it and the test or check that demonstrates it. A criterion the artifact marks met without evidence is a finding, and so is one it quietly omits. Constraints the brief states — compatibility, performance, dependency limits, out-of-scope boundaries — are checked the same way.

Then check the artifact for accuracy in both directions. Every claim it makes is traced to the diff, a log, a verdict, or a plan; anything unsupported is a finding. In the other direction, read the diff for what the artifact does not mention — an undeclared change, a dropped requirement, a deviation left out of its section — because a delivery record is judged on what it hides as much as on what it states.

Take verification claims as claims. A named test must exist and cover what it is credited with; machine-check evidence must be current for the final state of the change, not a run from three commits ago; a validator verdict quoted here must match the artifact it came from, conditions included. An accepted PASS_WITH_CONDITIONS with unmet conditions is a finding, not a footnote. Where a step was skipped for the risk class, confirm the artifact says so rather than implying verification that never happened.

Last, judge the change description as its reader will: enough context to review the change without the run, in the project's format, with the links the standard requires. Weaknesses here are usually minor findings — an inaccurate description is a major one.

The checklist appends rows for acceptance-criteria coverage, artifact accuracy against the diff, and verification evidence below the core eight.

## Output

Write the report to `{run}/delivery-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; questions are separated from findings, blocking from non-blocking.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3). The line runs on evidence strength: a criterion the evidence cannot confirm, or a verification claim nothing supports, forces at least PASS_WITH_CONDITIONS with each one a named condition; a criterion the change demonstrably fails forces FAIL. Every verdict routes to the `delivery-approval` gate: `accept` completes the run, `revise` returns to `deliver-prepare` with the human's direction, `reject` ends it.
