# Phase {N} Implementation Log

> **Run:** [run id]
> **Plan:** [phase-{N}-plan.md]
> **Iteration:** [loop iteration, 1-based]
> **Status:** [Done | Partial | Blocked]

## Summary

[1–2 paragraphs: what was implemented, the overall outcome, notable events. States plainly whether the phase is done, partially done, or blocked.]

## Validation findings addressed

[Loop iterations only — omit on the first pass. One entry per finding from phase-{N}-impl-validation.md: the finding id and what changed in response. A finding disputed rather than fixed states why.]

## Step log

[One entry per plan step, in plan order. Steps not reached state why not.]

### Step 1: [step title from the plan]

- **Status:** [Done | Partial | Blocked | Skipped — with why for anything but Done]
- **Files changed:** [`path` — created/modified, one-line description; every path inside the plan's declared file scope]
- **Tests:** [`path` — what the tests cover]
- **Checks:** [pass | fail at this step's checkpoint]
- **Notes:** [decisions made, observations; omit when empty]

## Machine checks

[The evidence the loop's exit criterion consumes: the project's verification command as actually run and its final result. A failing run is recorded as failing, never omitted.]

## Deviations from plan

["None — implementation followed the plan exactly", or one entry per deviation: what differed, why, knock-on effects. A deviation that would touch undeclared files is not a deviation to record here — it is a finding for planning, below.]

## Issues encountered

["None", or per issue: what happened, how it was resolved, implications for later steps or phases.]

## Findings for planning

[Plan defects that need plan-revise; empty states "None". Stable ids P-001, P-002, … — downstream decisions reference them. Unresolved ambiguities are findings too: state the interpretations seen instead of picking one.]

- **[P-001] [title]**
  - **Step affected:** [plan step number and title]
  - **Issue:** [what is wrong, missing, or ambiguous in the plan]
  - **Impact:** [what happens if unaddressed]
  - **Proposed alternatives:** [1–3 options]

## Commits

[One line per commit made during this phase: short sha, subject.]

## Notes for next phase

[Multi-phase runs only — omit otherwise. What the next phase's planner or implementer should know: things learned, warnings, recommendations.]
