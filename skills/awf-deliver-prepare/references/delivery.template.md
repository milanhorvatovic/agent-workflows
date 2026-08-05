# Delivery: [subject]

> **Run:** [run id]
> **Brief:** [path of the brief this delivers against]
> **Risk class:** [R0 | R1 | R2 | R3]
> **Phases:** [phase numbers covered by this delivery, and their state]

[Sections marked *(R2+)* are omitted at R1, where the artifact is the minimal change note — summary, what changed, the verification that ran, and the change description the shipping channel needs.]

## Summary

[2–4 sentences a reader with no run context can act on: what was asked, what shipped, and whether it meets the brief. Names anything the reader must know before deciding — a deviation, an unmet criterion, a condition attached to a verdict.]

## What changed and why

[Grouped by the change it adds up to, never file by file. Each entry names the visible effect and its reason from the brief or from a decision the log records.]

- **[change]** — [what it does] · [why, traced to the brief or a recorded decision] · [where: paths or modules]

### Deviations from the plan *(R2+)*

[Deviations the implementation logs declared, each with its rationale and its effect on the brief's criteria. "None" where the plans were followed as written.]

## Acceptance criteria *(R2+)*

[Every criterion from the brief, with its state and the evidence behind it. Unverified is a state, not an omission — never report a criterion as met without evidence.]

| # | Criterion | State | Evidence |
| --- | --- | --- | --- |
| 1 | [criterion from the brief] | met / partially met / not met / unverified | [test, check, or artifact that shows it] |

## Verification

### Machine checks

[The project's verification command, when it last ran, and its result. A stale or absent run is stated as such.]

### Tests

[What covers the new behavior — suites, notable cases added, and anything deliberately left uncovered with the reason.]

### Validation verdicts

[Each validator that ran, its verdict, and any conditions or findings left open under an accepted verdict. A step skipped for the risk class is listed as skipped — an absent verdict is a fact about the run, not a gap.]

| Step | Verdict | Conditions / open findings |
| --- | --- | --- |
| [implement-validate / review-validate] | [PASS / PASS_WITH_CONDITIONS / FAIL / skipped (risk class)] | [conditions, open finding ids, or "none"] |

## Change description

[Ready to use in the project's shipping channel, in the project's rendered PR or change-note standard — that standard fixes the title convention, sections, and checklist; this block is the fallback shape where the project declares none. Written for the reviewer, not for the run.]

**Title:** [per the project's convention]

**Body:**

[Summary, changes, testing, and any links the standard requires.]

## Risks and rollback *(R2+)*

[What could go wrong after this ships, what signals would show it, and how to undo it — the revert path, migrations that need reversing, flags to flip.]

## Follow-ups *(R2+)*

[Work this run deliberately left: deferred findings with their ids, open questions, known gaps, and where each is recorded. "None" when nothing was deferred.]
