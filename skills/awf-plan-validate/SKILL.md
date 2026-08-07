---
name: awf-plan-validate
description: Adversarially validates a phase plan against the brief — requirements coverage, internal consistency, technical feasibility verified against the actual codebase, file-scope accuracy, test adequacy, implementer readiness — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report. Triggers as the planning stage's plan-validate step, fresh-context in every mode, after awf-plan-create or awf-plan-revise produces a plan. It identifies issues and asks questions, never fixes them — revising the plan against its findings is awf-plan-revise.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/phase-1-plan.md"
          required: false
      output:
        artifact: "{run}/phase-{N}-plan-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-plan-validate

Renders the verdict on a phase plan: is it complete against the brief, internally consistent, technically feasible, and specific enough for the implementer to execute without guessing? The verdict routes the planning loop (spec §9.2) and nothing proceeds to implementation past a plan this step has not passed — so the job is to find what is wrong, missing, or ambiguous, not to confirm the plan is good.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never fix, never rewrite, never add scope beyond the brief.

## Inputs

- `{run}/phase-{N}-plan.md` (required) — the plan under validation, read in its entirety before judging.
- `{run}/brief.md` (required) — the requirements source: its goal, constraints, and acceptance criteria are the bar. Requirements coverage is checked line by line — a plan that misses requirements is fundamentally flawed regardless of its other qualities.
- `{run}/phase-1-plan.md` (optional) — the fixed phase list, when validating a later phase whose own plan marks it "fixed by phase-1 plan". It is what says which phase owns which requirement, so without it this step cannot tell work assigned elsewhere from work this phase dropped. Optional because a single-phase run has no later phase and a phase-1 validation already holds the list in the plan under validation; never satisfied from another run, since a phase list belongs to the run that fixed it — and because the input is optional, spec §8.4 would otherwise admit a cached one, so check the plan's `Run` header against this run and treat a mismatch as absent, the same guard the delivery steps apply to theirs. Coverage computed from another run's phase list would assign this run's requirements by a decomposition nobody made for it.
- The project's coding, architecture, and testing standards, where they exist — the other bar, and what makes the report's Standards checklist row mean something. A plan whose steps, file scope, or test requirements contradict a standard without saying why is a finding; an argued departure is judged on the argument, not on the departure.

## Method

Check completeness first: walk the brief's requirements and acceptance criteria one by one, tracing each to the plan step(s) addressing it; track covered, partially covered, and uncovered. Then scope in the other direction — plan content that traces to no requirement is scope creep, flagged unless justified.

Verify feasibility against the codebase, not against plausibility. Files the plan claims exist are checked to exist, along with the functions and sections it references inside them; described changes are checked as technically sound for the stack and consistent with the project's patterns; steps are checked in sequence for ordering errors, missing intermediate steps, and unstated dependencies.

Check the file scope for accuracy in both directions: every file the steps touch is declared (a step touching an undeclared file breaks the contract the implementation loop binds to, spec §9.2), and everything declared is actually used by some step. An inaccurate scope section is a critical finding — downstream drift detection depends on it.

Judge test adequacy per step — scenarios comprehensive enough to catch regressions, edge cases and error conditions included, paths matching the project's test structure — and flag steps that should carry tests but do not. Check the rollback strategy would actually restore a consistent system, and that error handling, security implications, and data-integrity concerns of the planned changes are addressed.

Assess implementer readiness last, reading each step as the implementer will — cold: flag every step that needs a design decision the plan does not make, an assumption it does not state, or context it does not provide. Every ambiguity becomes an explicit question with possible answers — never resolved by assuming the likely interpretation.

For a plan whose Phase list section fixes the run's phase list, load `references/phase-decomposition.md` — the phase-sequencing and coverage checks that section must additionally survive. For a bugfix plan, load `references/bugfix.md` — the root-cause and regression-test checks that decide whether the fix targets cause or symptom.

## Output

Write the report to `{run}/phase-{N}-plan-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; questions are separated from findings, blocking from non-blocking.

Append one section, **Coverage**, above the findings: the requirement-by-requirement mapping from the brief's requirements and acceptance criteria to the plan step or steps addressing each, marked covered, partially covered, uncovered, or owned by another phase. A phase-1 plan of multi-phase work carries the phase list itself, so a row may point at the phase-list entry that owns the requirement — demanding a phase-1 step for work a later phase owns would read as uncovered or push the plan to invent steps it has no business fixing yet. Validating a later phase, the fixed list comes from `{run}/phase-1-plan.md`: a requirement it assigns to this phase and the plan does not address is **uncovered** and a finding like any other, and one it assigns elsewhere is **owned by another phase**, which is a fact about the run rather than a gap in this plan. Where that input is genuinely absent the row is **not assessable**, recorded with the reason and carried as a non-blocking question: the step cannot establish ownership, and a state it cannot resolve must not be one the plan can never clear, since the planning loop exits only on a passing verdict. The completeness walk above produces the section, and it belongs in the artifact for the same reason `validate-tickets` gives its own coverage table — the check's result is not a boolean. The core **Completeness** and **Scope** rows record whether coverage holds; this records how that was established, and a partially covered requirement is the finding most easily lost when there is nowhere to write down that it is only half addressed.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3) — with unresolved critical findings or blocking questions forcing FAIL. The verdict is consumed by the planning loop's exit criteria and routes the plan to the plan-approval gate or back to `plan-revise`.
