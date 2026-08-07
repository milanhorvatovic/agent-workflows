# Review Fixes: [subject]

> **Run:** [run id]
> **Phases covered:** [the completed phases whose plans bound this stage's scope — "1" for a single-phase run]
> **Iteration:** [review loop iteration this artifact was last written by, 1-based]

## Fixes

[One subsection per iteration this step runs, the first included, so iterations stay separable without a reader inferring where one ended. Findings are listed in the order they were worked — severity order, criticals first.]

### Iteration 1

- **[R-001]** — [what changed in response, and the tests added or strengthened with it]
- **[S-002]** — [what changed in response, and the tests added or strengthened with it]

## Disputed

[Findings not applied as resolved, with the evidence: the fix breaks something the review did not see, or the finding misreads code the resolution did not check. Deciding the dispute belongs to the next review pass, not to this step — so a dispute stays listed here until a later iteration resolves it, rather than being dropped once raised. "None" if every finding was applied.]

- **[R-003]** (iteration 1) — [why the fix was not applied, with the evidence]

## Findings for planning

[Findings whose fix would touch a file no phase plan declares. Escalated toward `plan-revise` rather than fixed: the scope is not expanded here. "None" if the list is empty.]

- **[P-001]** — [step affected] · [issue] · [impact] · [proposed alternatives]

## Machine checks

[Refreshed in place each iteration, not appended: the current answer to "do the checks pass", so the next iteration reads one result rather than one per loop. Command, exit status, and what ran. This section and Commits below change every iteration by construction — the loop's stall signal reads Fixes and Disputed, not these.]

## Commits

[Refreshed in place: the commits this review loop has produced, newest last. Hash and subject.]
