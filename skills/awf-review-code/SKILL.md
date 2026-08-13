---
name: awf-review-code
description: Reviews the implemented change with fresh eyes against the plan — correctness, error handling, edge cases, performance, maintainability, standards adherence — producing severity-graded findings with concrete fixes, and no verdict, in the run's review findings report. Triggers as the review stage's review-code step once implementation has passed its validation, and on every review loop iteration re-reviewing the fixed change; reviewing an external contribution loads references/contributor.md for the PR-input and tone differences. The dedicated adversarial security pass is awf-review-security, the verdict on the change is awf-review-validate's, and applying the findings is awf-review-fix.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{P}-plan.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/review-fixes.md"
          required: false
      output:
        artifact: "{run}/review-findings.md"
        template: references/review-report.template.md
---

# Skill: awf-review-code

Fresh scrutiny of the implemented change: the full diff, judged as a whole in codebase context, against the plan that produced it. The reviewer reports findings — specific, severity-graded, each with a concrete fix the author can act on directly — and renders no verdict: `review-validate` weighs the findings into the verdict, so this report's job is to be complete and actionable, not to conclude.

## Role

The step runs as the reviewer, always with fresh context (spec §4) — fresh eyes are the point, so nothing from the implementation session is assumed. Read the full change before commenting; order concerns correctness, then security, then performance, then style; block on objective criteria, never preference; never rewrite the code, and never nitpick what linters and formatters already enforce.

## Inputs

- `{run}/phase-{P}-plan.md` (required) — what was supposed to be built: the steps, the acceptance criteria, and the file-scope declaration the change is bound to. This stage runs once after the final phase, so the path takes `{P}` — one artifact per completed phase (spec §8.1) — rather than the `{N}` of a stage that names the phase it is executing: a multi-phase run has a plan per phase and every one is read, since the change under review is their sum and a step reviewed against the wrong phase's plan is reviewed against nothing.
- `{run}/phase-{P}-impl-log.md` (required) — the implementer's account: deviations declared, issues hit, machine-check evidence, commits. `{P}` again — one log per phase, all of them read.
- `{run}/review-fixes.md` (optional) — what the previous iteration fixed, what it disputed rather than fixed, and the loop's current machine-check result and commits, which `review-fix` refreshes in place there. Optional because it does not exist on the first iteration, which is availability rather than caution. Optional makes it reachable by §8.4's cache, so the freshness half of the same rule binds: usable only where its `Run` header matches this run, a fix record from another run describing another change entirely, and its **Iteration** read to confirm it is the previous iteration's record rather than one left behind by an earlier run's loop. From the second it is what stops this pass re-raising a finding already answered, and what puts an open dispute in front of the fresh eyes meant to decide it — a dispute this pass never sees is one the loop can iterate past.
- The change itself, read directly — the whole diff under review and its tests, which in a multi-phase run is the sum of every completed phase rather than one phase's work. The diff is the subject; the plans and logs are the context it is judged in.
- The project's coding, architecture, and testing standards, and its review checklist where one exists — the rules the review enforces, read before reviewing any code. The architecture standard is what makes a structural finding more than a matter of taste: a change that crosses a boundary the project has declared is a finding against the standard, not against the reviewer's preference.

## Method

Read the plan and log first for intent, then the full diff before forming any opinion. For each changed file, read the surrounding code it lives in — callers, callees, the contracts it must honor — because a diff reviewed in isolation hides exactly the class of defect fresh eyes are here to catch.

Work the dimensions in priority order: correctness (logic errors, wrong conditions, off-by-one, null access, type mismatches), error handling at every boundary the change touches, edge cases (empty, boundary, concurrent, large, malformed), performance, maintainability (readability, duplication, structure), and standards adherence. Verify tests exist for new behavior and edge cases, assert meaningfully, and hold test code to the same bar as the code under test. Security basics on changed surfaces are findings too (category security): the adversarial pass is `review-security`'s and runs per the risk class, but a visible vulnerability is never left for a step that may be skipped.

When the change touches hot paths, data access, caching, concurrency, or large data volumes, load `references/performance.md` — the catalog of performance anti-patterns to check systematically. When the subject is an external contribution — a PR or branch from outside the run rather than the run's own diff — load `references/contributor.md` for the input handling, tone, and compatibility attention that context adds.

Cross-check the change against the plan: steps reflected in the diff, acceptance criteria actually met, files within the declared scope. Deviations the log declares are reviewed as implemented; differences the log does not declare are findings.

## Output

Write the report to `{run}/review-findings.md`, scaffolded from `references/review-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Findings carry stable `R-…` ids, a severity (critical, major, minor, suggestion), a category, an exact location, and a concrete suggested fix; good decisions are acknowledged in the positive observations. No verdict anywhere — `review-validate` renders it, `review-arbitrate` resolves disagreement, and `review-fix` acts on what survives.
