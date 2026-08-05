---
name: awf-plan-create
description: Creates the phase plan from the brief, grounding, and ideation — ordered atomic implementation steps with files, changes, tests, and acceptance criteria, the mandatory file-scope declaration the implementation loop binds to, risks, technical decisions, and open questions. Triggers as the planning stage's plan-create step in every workflow, whenever a confirmed brief needs an implementable, validatable plan. Multi-phase decomposition and bugfix root-cause planning load as references; revising an existing plan against findings is awf-plan-revise, not this skill.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/grounding.md"
          required: false
        - artifact: "{run}/ideation.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-plan.md"
        template: references/plan.template.md
      on:
        PASS: plan-approval
        PASS_WITH_CONDITIONS: plan-revise
        FAIL: plan-revise
---

# Skill: awf-plan-create

Produces the plan for the current phase: what to build, in what order, touching which files, verified how. The plan is the contract downstream steps bind to — the implementer executes it faithfully, the validator judges the work against it, and the implementation loop polices the file scope it declares (spec §9.2) — so specificity is the quality bar: every step implementable without guessing, every criterion testable, every ambiguity surfaced instead of resolved by silent default.

## Role

The step runs as the planner: decompose into ordered, verifiable work, sequence by explicit dependencies, state assumptions and risks instead of burying them. Never implement — the output is the plan.

## Inputs

- `{run}/brief.md` (required) — the confirmed brief: its goal, constraints, and acceptance criteria are the requirements the plan must fully cover, and the bar `plan-validate` will hold it to.
- `{run}/grounding.md` (optional, cacheable) — the verified codebase analysis; its constraints-on-the-solution-space section is the planning input. When absent, read the relevant code directly before planning — a plan referencing unverified paths or patterns will fail validation.
- `{run}/ideation.md` (optional) — where ideation ran, the recommended approach is the plan's starting point, not a suggestion to re-litigate; the plan turns it into steps.

## Method

Restate the requirements in the overview before decomposing — the restatement is the shared understanding the plan is built on.

Fix the phase boundary first. A run whose work fits one phase plans it all as phase 1. When the brief's work exceeds one deliverable increment, the phase-1 plan fixes the run's phase list — load `references/phase-decomposition.md` for how to cut phases, draw their boundaries, sequence their dependencies, and place cross-cutting concerns. Later phases inherit that list; their plans detail one phase and leave the list alone.

For a bugfix run (the `bugfix` workflow, or a brief that is a defect report), load `references/bugfix.md` — it adds the reproduction, root-cause, and regression-test sections the plan must carry and the discipline for validating a cause hypothesis before planning the fix.

Decompose into atomic steps: one logical change each, implementable and verifiable in isolation, fine-grained enough that no step forces a significant design decision on the implementer. Each step names its files (exact paths), its changes (specific enough to implement without guessing, citing existing patterns to follow), its test requirements, and its acceptance criteria. Order steps by dependency and state any dependency the ordering does not make obvious.

Declare the file scope — the files and modules the phase may create or modify. This section is mandatory: it is the contract the implementation loop binds to, so it must be complete (a step touching an undeclared file is scope drift) and honest (no padding with files the plan has no reason to touch).

Define the phase's testing approach, rollback strategy, and any configuration, migration, or infrastructure work beyond code. Record technical decisions the requirements left open with a recommendation and reasoning; anything not confidently decidable becomes an open question with proposed alternatives — the planner never resolves ambiguity by picking a default silently.

## Output

Write the plan to `{run}/phase-{N}-plan.md`, scaffolded from `references/plan.template.md` (spec §8.3 — the executor scaffolds it by script; the step fills every placeholder, marking sections that do not apply with why not; the changelog stays empty at creation — `awf-plan-revise` owns it).

The plan is validated adversarially by `plan-validate`; its verdict routes the plan onward to the plan-approval gate or back through revision.
