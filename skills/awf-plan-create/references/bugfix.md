# Bugfix planning — reproduction, root cause, regression test

What a bugfix plan carries beyond the standard template. Loaded for `bugfix`-workflow runs and any brief that is a defect report. A bugfix plan is single-phase (phase 1) unless the root cause reveals work large enough to reclassify.

## Extra plan sections

Insert after the Overview, in this order:

### Bug overview

Expected behavior, actual behavior, impact, and scope (who or what is affected) — restated from the brief, confirming the reproduction conditions are understood.

### Reproduction and verification

- A reliable reproduction, preferably automated: an existing failing test, or a planned regression test that fails before the fix and passes after.
- When automation is impractical (third-party outage, timing-dependent behavior), a deterministic manual verification checklist — and why automation is impractical.
- The verification steps that prove the fix after implementation.

### Root cause analysis

- The cause hypothesis, argued from the code actually read — name the files and functions on the failing path, not the symptom's location.
- When multiple causes are plausible, list each and state how the plan distinguishes between them before committing to a fix; evidence too weak to pick one is an open question, not a guess.
- The distinction between cause and symptom is the plan's foundation: a fix planned against a symptom fails validation.

## Discipline

- **Regression test first.** The plan's test requirements lead with the regression test that pins the bug: fails pre-fix, passes post-fix. An exception must be explicit and justified in the plan.
- **Fix the cause, not the site.** The fix targets the root cause; suppressing the symptom where it surfaces is planning debt the review stage will flag.
- **Check the blast radius.** Related surfaces that share the faulty code path are inspected and either covered by the plan or explicitly declared out of scope with a reason.
- **Edge cases around the fix.** Error paths and boundary conditions adjacent to the change get test coverage — a bugfix that introduces a neighboring bug is the classic failure mode.
- **Scope stays tight.** The file scope declares only what the fix and its tests touch; refactoring temptations discovered en route are recorded as open questions or follow-up recommendations, never folded in.
