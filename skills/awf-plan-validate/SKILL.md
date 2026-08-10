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
          required: true
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
- `{run}/phase-1-plan.md` (required) — the phase list: what says which phase owns which requirement. Validating the phase-1 plan it is provisional, this step being one of the two things that can still re-cut it before `plan-approval` fixes it; validating any later phase it is fixed and binds. Without it this step cannot tell work another phase owns from work this plan dropped, so a later phase's plan could pass with its coverage unchecked. Required rather than optional because it always exists wherever this step runs: validating phase 1 or a single-phase run, `{N}` is 1 and this resolves to the plan already under validation; validating a later phase, phase 1 was planned before that phase could exist. Never satisfied from another run — spec §8.4's cache does not reach a decomposition made for a different run — so check the plan's `Run` header and stop rather than validate coverage against the wrong list.
- The project's coding, architecture, and testing standards, where they exist — the other bar, and what makes the report's Standards checklist row mean something. A plan whose steps, file scope, or test requirements contradict a standard without saying why is a finding; an argued departure is judged on the argument, not on the departure.

## Method

Check completeness first: walk the brief's requirements and acceptance criteria one by one, tracing each to the plan step(s) addressing it; track covered, partially covered, and uncovered. Then scope in the other direction — plan content that traces to no requirement is scope creep, flagged unless justified.

Verify feasibility against the codebase, not against plausibility. Files the plan claims exist are checked to exist, along with the functions and sections it references inside them; described changes are checked as technically sound for the stack and consistent with the project's patterns; steps are checked in sequence for ordering errors, missing intermediate steps, and unstated dependencies.

Check the file scope for accuracy in both directions: every file the steps touch is declared (a step touching an undeclared file breaks the contract the implementation loop binds to, spec §9.2), and everything declared is actually used by some step. An inaccurate scope section is a critical finding — downstream drift detection depends on it.

Judge test adequacy per step — scenarios comprehensive enough to catch regressions, edge cases and error conditions included, paths matching the project's test structure — and flag steps that should carry tests but do not. Check the rollback strategy would actually restore a consistent system, and that error handling, security implications, and data-integrity concerns of the planned changes are addressed.

Assess implementer readiness last, reading each step as the implementer will — cold: flag every step that needs a design decision the plan does not make, an assumption it does not state, or context it does not provide. Every ambiguity becomes an explicit question with possible answers — never resolved by assuming the likely interpretation.

For a plan whose Phase list section authors the run's phase list, load `references/phase-decomposition.md` — the phase-sequencing and coverage checks that section must additionally survive. For a bugfix plan, load `references/bugfix.md` — the root-cause and regression-test checks that decide whether the fix targets cause or symptom.

## Output

Write the report to `{run}/phase-{N}-plan-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; questions are separated from findings, blocking from non-blocking.

Append one section, **Coverage**, above the findings: the requirement-by-requirement mapping from the brief's requirements and acceptance criteria to the plan step or steps addressing each, marked covered, partially covered, uncovered, owned by another phase, or owner unresolved. The fixed list decides which of the last two applies: a requirement it assigns to this phase and the plan does not address is **uncovered** and a finding like any other, and one it assigns elsewhere is **owned by another phase** — a fact about the run's decomposition rather than a gap in this plan, and not a finding. A phase-1 plan carries that list in the artifact under validation; a later phase's plan reads it from the phase-1 plan. Availability is not conclusiveness. A list that exists can still fail to assign an owner — `references/phase-decomposition.md` names boundary ambiguity as where multi-phase plans fail, so a requirement may plausibly belong to two phases or to none of them. That row is **owner unresolved**, and it always blocks — but which route clears it depends on whose artifact is at fault. Validating a **phase-1** plan, the list is not yet fixed: it lives in the artifact under validation, `plan-revise` writes that same artifact, and an ambiguous boundary is a defect in the plan being judged. Raise it as a blocking finding and the revise loop corrects it, which is the one chance to fix a decomposition before approval freezes it. Validating a **later** phase, no step in the loop can re-cut a list already fixed, so the blocking finding names the cross-phase re-cut it needs and the loop's stall signal escalates it — the plan must not reach approval carrying coverage nobody could establish, and a non-blocking question would let exactly that happen. Guessing between the two states above stays wrong whichever way it falls. The completeness walk above produces the section, and it belongs in the artifact for the same reason `validate-tickets` gives its own coverage table — the check's result is not a boolean. The core **Completeness** and **Scope** rows record whether coverage holds; this records how that was established, and a partially covered requirement is the finding most easily lost when there is nowhere to write down that it is only half addressed.

Fill **Cross-phase impact** where the list places phases after this one, and leave it out otherwise — the shared section names the validators that report there and this is one of the two. What belongs in it is what this plan commits the rest of the run to: a technical decision the later phases inherit, a boundary this plan moves work across, a dependency it creates for work nobody has planned yet. Validating the phase-1 plan, the list reported against is the one the artifact under validation fixes; validating a later phase, it is read from `{run}/phase-1-plan.md`, the same input the coverage walk uses. The two sections answer different questions off that one list, which is why filling one does not fill the other: Coverage says which phase owns a requirement, and this says what this phase's approach does to the phases that own the rest.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3) — with unresolved critical findings or blocking questions forcing FAIL. The verdict is consumed by the planning loop's exit criteria and routes the plan to the plan-approval gate or back to `plan-revise`.
