---
name: awf-implement-validate
description: Adversarially validates an implementation against its phase plan — every step done as specified with the diff as ground truth over the log's claims, acceptance criteria met, tests present, meaningful, and passing, no undeclared scope, machine-check evidence green — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report that also carries what the work just done binds for the phases the list places after it. Triggers as the implementation stage's implement-validate step, fresh-context in every mode, after awf-implement writes the implementation log. It identifies issues and asks questions, never fixes them; validating the plan itself is awf-plan-validate, and the fresh-context review of the finished change belongs to the review stage.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-1-plan.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-impl-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-implement-validate

Renders the verdict on an implementation: does the work actually done match the plan that was approved? The verdict gates the implementation loop (spec §9.2) and nothing leaves the stage past an implementation this step has not passed — so the job is to find what is missing, wrong, or undeclared, not to confirm the work looks done. Where the run has phases after this one, the report also carries what this phase's work binds for them — the last point in the loop where that is cheap to say and the phase after it is still unplanned.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never fix, never improve the code, and never re-litigate the plan: plan quality was `plan-validate`'s question, and here the plan is the bar, not the subject.

## Inputs

- `{run}/phase-{N}-impl-log.md` (required) — the implementer's account of what was done.
- `{run}/phase-{N}-plan.md` (required) — the approved plan: what should have been done.
- `{run}/phase-1-plan.md` (required) — the fixed phase list, for the cross-phase impact this step reports: which phases follow this one and what they are down to do, so a deviation this phase made can be named against the work it lands on rather than left for a later planner to discover from the diff. Required rather than optional because it always exists wherever this step runs, the availability argument `plan-validate` and `plan-revise` both make for the same artifact — this step already requires `{run}/phase-{N}-plan.md`, and wherever that exists so does phase 1's: at `{N}` 1 they are the same file, and after it phase 1 was planned before this phase could exist. Never satisfied from another run, the guard the planning steps state for the same artifact: §8.4's cache does not reach a required input, and a decomposition made for a different run would be the wrong list even if it did — so check the plan's `Run` header.
- The change itself, read directly — the diff of this phase's work and the tests it added. The diff is ground truth: the plan says what should happen, the log says what the implementer claims happened, and where either disagrees with the code, the code decides.
- The project's coding and testing standards, where they exist — what the report's Standards checklist row is checked against, alongside the plan's own requirements.

## Method

Walk the plan step by step and verify each against the diff: the named files created or modified as specified, the changes achieving the step's goal by the plan's approach rather than a different one, the acceptance criteria met by the actual code. Cross-reference in all three directions — plan steps with no supporting changes in the diff, log entries claiming Done that the diff does not support, and diff content no plan step explains.

Check scope against the plan's file-scope declaration: every file the diff touches must be declared, and a change outside the declaration is scope drift the loop contract flags (spec §9.2) — a critical finding regardless of how reasonable the change looks, because the downstream contract depends on the declaration being exact.

Verify tests per step: present at the specified paths, covering the specified scenarios including edge cases and error conditions, asserting meaningfully rather than trivially, and passing. Verify machine-check evidence: the log records the project's verification command actually run with a green result — evidence that is absent, stale, or failing blocks PASS no matter what the log claims elsewhere.

Check the quality of the changes against the project's coding and testing standards, security basics on every changed surface (input validation, injection, secrets and sensitive-data exposure, unsafe defaults), unintended side effects — existing behavior modified without a step requiring it, tests removed or weakened, public interfaces changed — and commits following the project's commit format.

Attribute every finding: an implementation defect is fixable by iterating the loop; a plan defect surfaced by the work — a step that was wrong or incomplete before anyone executed it — is labeled as such, because iterating cannot fix it and the loop escalates it toward `plan-revise` instead. The distinction routes the run, so it is part of the finding, not commentary.

Where the phase list places phases after this one, ask last what the work just done changes for them: an interface built differently from the plan's approach, a declared deviation the later phases inherit, a file the list reserved for later work touched early, a dependency this phase created that the next one has to plan around. The phase list is what makes that answerable — it says which phases follow and what each owns — and this is the reading that otherwise gets made from a diff, by a planner, after a later phase has already been planned against the assumption this phase broke.

## Output

Write the report to `{run}/phase-{N}-impl-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; the checklist appends rows for scope adherence and machine-check evidence below the core eight; questions are separated from findings, blocking from non-blocking.

Every finding also carries an **Attribution** field the shared block does not define — `implementation defect` or `plan defect` — written as one more bullet in the finding's own list, in the block's `- **Attribution:** …` form and immediately after **Recommendation**, so the extension lands in one predictable place rather than wherever the writer puts it. The shared source gains nothing for it: five other skills consume that block and none of them attribute findings this way, so the extension stays with the consumer that needs it, the same reason a task-specific section is appended rather than added upstream. What does go upstream is a rule the other consumers have to read — which is why the conditionality on **Cross-phase impact** below lives in the shared source and this field does not. It is part of the finding rather than commentary because it routes the run: an implementation defect is fixable by iterating this loop, a plan defect is not, and the loop escalates that one toward `plan-revise` instead. A finding whose attribution can only be inferred from its prose is one the loop has to guess at, which is the guess this field exists to remove.

Fill **Cross-phase impact** where the phase list places phases after this one, and leave it out otherwise — the shared section names the validators that report there and this is one of the two. Report what this phase's implementation binds for the phases that follow, taken from the diff rather than from the log's account of it, since a consequence the implementer did not notice is exactly the one worth writing down. A cross-phase consequence is not a finding by itself: where the plan permitted the deviation the section is a note and nothing more — for the human who reads this report, and for the delivery artifact, whose two steps declare it with `{N}` ranging over every completed phase. It reaches the next phase's planning as a declared input: `plan-create` and `plan-validate` both take `{run}/phase-{P}-impl-validation.md`, one report per completed phase (spec §8.1), so a binding the next phase must act on — a rollout order, a migration step, a compatibility guarantee, the kind that leaves no trace in the tree the next planner reads — arrives with the plan rather than with whoever remembered it. That is what this section is for and why it is worth the diff-reading: what is written here is the whole of what the later phases are planned and validated against. Write it so a planner who was not here can act on it and a validator can check a plan against it: what is bound, for which phase, and why, and where it did not, the finding already exists with `plan defect` attribution and the section names it rather than restating it.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3). The loop contract consumes it together with green machine checks: both green exits the stage, anything else iterates within the cap or escalates per the stage contract.
