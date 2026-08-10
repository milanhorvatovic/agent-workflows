# Delivery: [subject]

> **Run:** [run id]
> **Brief:** [path of the brief this delivers against]
> **Risk class:** [R1 | R2 | R3]
> **Phases:** [phase numbers covered by this delivery, and their state]

## Summary

[2–4 sentences a reader with no run context can act on: what was asked, what shipped, and whether it meets the brief. Names anything the reader must know before deciding — a deviation, an unmet criterion, a condition attached to a verdict.]

## What changed and why

[Grouped by the change it adds up to, never file by file. Each entry names the visible effect and its reason from the brief or from a decision the log records.]

- **[change]** — [what it does] · [why, traced to the brief or a recorded decision] · [where: paths or modules]

### Deviations from the plan

[Deviations the implementation logs declared, each with its rationale and its effect on the brief's criteria. "None" where the plans were followed as written. Omitted at R1, where the artifact is the minimal change note.]

## Acceptance criteria

[Every criterion from the brief, with its state and the evidence behind it. Unverified is a state, not an omission — never report a criterion as met without evidence. Omitted at R1, where the artifact is the minimal change note.]

| # | Criterion | State | Evidence |
| --- | --- | --- | --- |
| 1 | [criterion from the brief] | met / partially met / not met / unverified | [test, check, or artifact that shows it] |

## Verification

### Machine checks

[The project's verification command, when it last ran, and its result. A stale or absent run is stated as such.]

### Tests

[What covers the new behavior — suites, notable cases added, and anything deliberately left uncovered with the reason.]

### Validation verdicts

[The verdicts on this change — implementation validation per phase, and the review validation where the review stage ran — each with any conditions or findings left open under an accepted verdict. A step skipped for the risk class is listed as skipped: an absent verdict is a fact about the run, not a gap. Verdicts on upstream artifacts (the plan, the ideation) are not verdicts on the change and do not belong here.]

| Step | Verdict | Conditions / open findings |
| --- | --- | --- |
| [implement-validate / review-validate] | [PASS / PASS_WITH_CONDITIONS / FAIL / skipped (risk class)] | [conditions, open finding ids, or "none"] |

## Change description

[Ready to use in the project's shipping channel, in the project's rendered PR or change-note standard — that standard fixes the title convention, sections, and checklist; this block is the fallback shape where the project declares none. Written for the reviewer, not for the run.]

**Title:** [per the project's convention]

**Body:**

[Summary, changes, testing, and any links the standard requires.]

## Risks and rollback

[What could go wrong once the change is live, what signals would show it, and how to undo it — the revert path, migrations that need reversing, flags to flip. Omitted at R1, where the artifact is the minimal change note.]

## Follow-ups

[Work this run deliberately left, from the sources this step reads: findings-for-planning the implementation logs raised, findings left open under an accepted validation verdict, and gaps the logs record — each with its id and where it is recorded. "None" when nothing was deferred. Omitted at R1, where the artifact is the minimal change note.]

## Gate direction

[What the human asked for at a gate that sent this artifact back, recorded before the outcome so it survives the decision (spec §7). One entry per item, quoted or restated. The step that revises this artifact folds each into the sections it is about and leaves this one empty — a non-empty section in an artifact that has left its stage is direction nobody applied. "None" until a gate sends something back. It is never part of what ships: the change description is written from the artifact's own sections, so direction left here would ship the request alongside the change it was about.]
