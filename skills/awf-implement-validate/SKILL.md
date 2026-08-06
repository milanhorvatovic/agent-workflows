---
name: awf-implement-validate
description: Adversarially validates an implementation against its phase plan — every step done as specified with the diff as ground truth over the log's claims, acceptance criteria met, tests present, meaningful, and passing, no undeclared scope, machine-check evidence green — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report. Triggers as the implementation stage's implement-validate step, fresh-context in every mode, after awf-implement writes the implementation log. It identifies issues and asks questions, never fixes them; validating the plan itself is awf-plan-validate, and the fresh-context review of the finished change belongs to the review stage.
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
      output:
        artifact: "{run}/phase-{N}-impl-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-implement-validate

Renders the verdict on an implementation: does the work actually done match the plan that was approved? The verdict gates the implementation loop (spec §9.2) and nothing leaves the stage past an implementation this step has not passed — so the job is to find what is missing, wrong, or undeclared, not to confirm the work looks done.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never fix, never improve the code, and never re-litigate the plan: plan quality was `plan-validate`'s question, and here the plan is the bar, not the subject.

## Inputs

- `{run}/phase-{N}-impl-log.md` (required) — the implementer's account of what was done.
- `{run}/phase-{N}-plan.md` (required) — the approved plan: what should have been done.
- The change itself, read directly — the diff of this phase's work and the tests it added. The diff is ground truth: the plan says what should happen, the log says what the implementer claims happened, and where either disagrees with the code, the code decides.
- The project's coding and testing standards, where they exist — what the report's Standards checklist row is checked against, alongside the plan's own requirements.

## Method

Walk the plan step by step and verify each against the diff: the named files created or modified as specified, the changes achieving the step's goal by the plan's approach rather than a different one, the acceptance criteria met by the actual code. Cross-reference in all three directions — plan steps with no supporting changes in the diff, log entries claiming Done that the diff does not support, and diff content no plan step explains.

Check scope against the plan's file-scope declaration: every file the diff touches must be declared, and a change outside the declaration is scope drift the loop contract flags (spec §9.2) — a critical finding regardless of how reasonable the change looks, because the downstream contract depends on the declaration being exact.

Verify tests per step: present at the specified paths, covering the specified scenarios including edge cases and error conditions, asserting meaningfully rather than trivially, and passing. Verify machine-check evidence: the log records the project's verification command actually run with a green result — evidence that is absent, stale, or failing blocks PASS no matter what the log claims elsewhere.

Check the quality of the changes against the project's coding and testing standards, security basics on every changed surface (input validation, injection, secrets and sensitive-data exposure, unsafe defaults), unintended side effects — existing behavior modified without a step requiring it, tests removed or weakened, public interfaces changed — and commits following the project's commit format.

Attribute every finding: an implementation defect is fixable by iterating the loop; a plan defect surfaced by the work — a step that was wrong or incomplete before anyone executed it — is labeled as such, because iterating cannot fix it and the loop escalates it toward `plan-revise` instead. The distinction routes the run, so it is part of the finding, not commentary.

## Output

Write the report to `{run}/phase-{N}-impl-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; the checklist appends rows for scope adherence and machine-check evidence below the core eight; questions are separated from findings, blocking from non-blocking.

Every finding also carries an **Attribution** field the shared block does not define — `implementation defect` or `plan defect` — appended to its other fields. It is part of the finding rather than commentary because it routes the run: an implementation defect is fixable by iterating this loop, a plan defect is not, and the loop escalates that one toward `plan-revise` instead. A finding whose attribution can only be inferred from its prose is one the loop has to guess at, which is the guess this field exists to remove.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3). The loop contract consumes it together with green machine checks: both green exits the stage, anything else iterates within the cap or escalates per the stage contract.
