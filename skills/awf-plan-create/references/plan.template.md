# Phase {N} Plan: [title]

> **Run:** [run id]
> **Brief:** [{run}/brief.md — one-line restatement of the goal]
> **Phase:** [N of total, with the phase's name from the phase list; "1 of 1" for a single-phase run]
> **Complexity:** [low | medium | high — relative to the project, never absolute time]

## Overview

[Restate what this phase accomplishes and why, in the planner's own words — the shared understanding the plan is built on. Where ideation ran, name the recommended approach this plan implements.]

## Phase list

[Phase-1 plans only — this section fixes the run's phase list; later phases' plans mark it "fixed by phase-1 plan". A single-phase run states that here. Per phase: name, scope, out of scope, key deliverables, dependencies on other phases, and relative complexity — see the phase-decomposition reference.]

## Prerequisites

[What must hold before this phase starts: completed prior phases, required codebase or environment state. "None" when the phase starts clean.]

## File scope

[Mandatory — the contract the implementation loop binds to (spec §9.2). Every file or module this phase may create or modify, with create/modify per path. Complete: a step touching an undeclared file is scope drift. Honest: nothing the plan has no reason to touch.]

- `path/to/file` — [create | modify: one-line reason]

## Implementation steps

### Step 1: [what this step accomplishes]

- **Files:** [exact paths, create or modify, which section or function when modifying]
- **Changes:** [what to add, modify, or remove — specific enough to implement without guessing; cite existing patterns to follow]
- **Tests:** [test file path, scenarios to cover, what the assertions verify]
- **Acceptance criteria:**
  - [ ] [concrete, testable criterion]
- **Depends on:** [step numbers, only when the ordering does not make it obvious]

[Continue for all steps, ordered by dependency.]

## Testing plan

[The phase's testing approach: what needs unit tests, what needs integration tests, the key behaviors, edge cases, and error conditions the suite must cover, and any test utilities or fixtures to create.]

## Rollback

[How to undo this phase's changes and leave the system consistent: revertability of the commits, reverse migrations, configuration to restore, external integrations to disconnect.]

## Configuration and infrastructure

[Work beyond code, or "None": environment variables, migrations, new dependencies, infrastructure changes, CI/CD changes.]

## Technical decisions

[Choices the requirements left open, decided or recommended here.]

| Decision | Recommendation | Reasoning | Status |
| --- | --- | --- | --- |
| [what needs deciding] | [recommendation] | [why] | [decided \| open] |

## Risks and assumptions

[Risks specific to this plan — what could go wrong, likelihood, impact, mitigation. Every assumption the plan rests on, with what changes if it proves false.]

## Changelog

[Empty at creation — plan-revise appends one row per revision.]

| Iteration | Date | Changes | Trigger |
| --- | --- | --- | --- |

## Open questions

[Ambiguities the planner could not confidently resolve, each specific and answerable, with proposed alternatives. "None" when everything is decided.]

## Gate direction

[What the human asked for at a gate that sent this artifact back, recorded before the outcome so it survives the decision (spec §7). One entry per item, quoted or restated. The step that revises this artifact folds each into the sections it is about and returns this one to "None" — anything other than "None" in an artifact that has left its stage is direction nobody applied. "None" until a gate sends something back, and "None" again once it has been applied.]
