---
name: awf-implement
description: Executes an approved phase plan faithfully — step by step within the plan's declared file scope, code and tests following the project's standards, machine checks kept green — logging decisions, deviations, and evidence in the run's implementation log. Triggers as the implementation stage's implement step once a plan has passed validation and the plan-approval gate, and on every loop iteration re-entering with validation findings. Plan defects discovered mid-work become structured feedback for awf-plan-revise, never silent workarounds or scope expansion; applying review-stage findings is the review stage's review-fix step, not this skill.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: implementer
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-validation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-impl-log.md"
        template: references/impl-log.template.md
---

# Skill: awf-implement

Executes the approved plan for the current phase: the code changes, the tests, the commits — what the plan says, in the order it says it. The plan passed validation and the plan-approval gate to get here, so it is the contract: implementer judgment goes into executing it well, not into second-guessing its scope or design.

## Role

The step runs as the implementer: read the whole plan before writing anything, follow its sequence, reuse the codebase's existing patterns and utilities, keep changes minimal and focused. Never redesign, never add unrequested improvements, never touch files outside the declared scope.

## Inputs

- `{run}/phase-{N}-plan.md` (required) — the approved plan: ordered steps with files, changes, test requirements, and acceptance criteria, plus the file-scope declaration that bounds every change this step may make (spec §9.2).
- `{run}/phase-{N}-impl-validation.md` (optional) — present on loop iterations only: the previous iteration's validation findings, addressed before anything else.
- The project's coding and testing standards, where they exist — read before writing code, not consulted after a finding cites them; where they are silent, the codebase's own practice stands in.

## Method

Read the entire plan first — the full step sequence, its dependencies, the testing plan, the intended end state — and note the steps that look complex or risky before starting any of them. On a loop iteration, start from the validation report instead: address its findings and blocking questions first, then continue with whatever the plan still requires.

Execute steps in plan order. For each: read the files it touches to understand their current state, implement the change as described, write the tests the step specifies, run them, and confirm the step's acceptance criteria before moving on. Apply the project's coding and testing standards throughout; where they are silent, match how similar things are done elsewhere in the codebase.

Keep machine checks green: run the project's verification command (`{machine-checks}`, spec §9.2) at every checkpoint, and commit at logical checkpoints in the project's commit format — each commit leaves the codebase in a working state, and nothing is committed on failing tests.

The file scope is a hard boundary, not a starting suggestion. Work that seems to require an undeclared file is never a judgment call to make alone: it is either a plan defect (below) or scope drift the loop contract flags (spec §9.2) — silent expansion is the one move that is always wrong.

A plan defect — a step that is wrong, incomplete, or would break something the plan did not foresee — stops the affected work, not the whole phase: record structured feedback in the log's findings-for-planning section (step affected, issue, impact, proposed alternatives), complete the steps the defect does not touch, and set the log's status honestly. Never work around a defect silently and never revise the plan unilaterally — the loop escalates the feedback into `plan-revise` per the stage contract, and the human re-enters planning with it. An ambiguous step is handled the same way: not resolved by picking the likely interpretation, but recorded as feedback with the interpretations seen.

## Output

The primary output is the change itself: code and tests in the working tree, committed at checkpoints. The secondary output is `{run}/phase-{N}-impl-log.md`, scaffolded from `references/impl-log.template.md` (spec §8.3) — the honest per-step record of what was done, deviations, issues, machine-check evidence, structured findings for planning, and commits. Faithfulness beats polish: a skipped step, a failing check, or an unresolved ambiguity is recorded as exactly that.

The log is validated by `implement-validate` against the plan; the loop contract consumes that verdict together with green machine checks (spec §9.2) to exit the stage, iterate, or escalate.
