---
name: awf-ideate
description: Explores the solution space a brief opens — three to five genuinely distinct approaches, each with its core idea, advantages, honest risks, codebase impact, and complexity, plus the approaches considered and discarded, and exactly one recommendation with the reasoning and the conditions that would overturn it — into the run's ideation artifact that planning builds on. Triggers as the ideation stage's ideate step once the brief is confirmed and any grounding is in hand, whenever a problem admits more than one shape of solution and the choice deserves to be made deliberately rather than by whichever idea arrived first. Distinct means a different shape of solution, not a variation on one idea; carrying the recommended approach to planning-ready detail loads references/refine.md. It explores and never plans — turning the recommendation into ordered steps is awf-plan-create — and it renders no verdict, the judgment on this artifact being awf-ideate-validate's.
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
      output:
        artifact: "{run}/ideation.md"
        template: references/ideation.template.md
      on:
        PASS: planning
        PASS_WITH_CONDITIONS: ideate-revise
        FAIL: ideate-revise
---

# Skill: awf-ideate

Maps the solution space before anything commits to a shape: what could be built, how the candidates genuinely differ, what each would cost and risk, and which one this brief should take. The artifact is what planning starts from — `plan-create` treats the recommendation as its starting point rather than a suggestion to re-litigate — so the exploration has to be real. A set of approaches that are one idea in three costumes, or a recommendation that reads as the only option ever considered, is the failure mode this step exists to prevent.

## Role

The step runs as the planner: explore breadth before depth, state risks and assumptions rather than burying them, and recommend with reasoning that survives being argued with. Never implement, never decompose into steps — the output is the exploration and its recommendation.

## Inputs

- `{run}/brief.md` (required) — the confirmed brief: its goal, constraints, and acceptance criteria bound the space. An approach that cannot satisfy a stated criterion belongs in the discarded set with that reason, not in the candidate set.
- `{run}/grounding.md` (optional, cacheable) — the verified codebase analysis: its patterns, dependencies, and constraints-on-the-solution-space are what make impact claims concrete. When absent, read the relevant code directly before claiming impact — an approach resting on a module, extension point, or dependency that does not exist is a fabrication `ideate-validate` verifies against the codebase and fails.
- The project's architecture standard, where one exists — the boundaries, layering, and technology direction every approach must respect, read before generating them. An approach that departs from it is legitimate but must say so and argue the departure; an approach that departs from it silently is the one that dies at `plan-approval`.

## Method

Restate the problem first, with the brief's constraints and acceptance criteria carried into the artifact. The ideation must stand on its own: `ideate-revise` works from it without re-reading the brief, and a reader arriving at `plan-approval` sees the problem the approaches answer.

Generate three to five approaches that differ in shape. The distinctness test is structural, not rhetorical: two approaches that touch the same modules and move data the same way are one approach with two names, however different their prose. Reach for genuinely different axes — where the work lives (existing module, new component, external service), when it happens (request time, background, build time), what absorbs the complexity (the data model, the interface, the caller), and how much is bought versus built.

Give every approach the same treatment, so the comparison is fair: core idea, how it works, its advantages, its risks and drawbacks, its codebase impact in named modules and components, its complexity relative to this project, and the key technical decisions it would force. An approach with no stated risks is under-analyzed, not risk-free — say what would go wrong, including the operational and migration costs that only appear after it ships.

Record what was considered and discarded, with the reason. The discarded set is evidence of the space actually explored, and it stops a revision loop from re-proposing an option already ruled out.

Recommend exactly one approach — or one explicit combination, named as such — and make the reasoning traceable to the brief's constraints rather than to taste. State what would overturn it: the condition under which the runner-up wins is what makes a recommendation reviewable instead of merely assertive. Where the recommendation must reach planning-ready detail — components, integration points, data flow, risk mitigation, readiness — load `references/refine.md` and expand the recommendation section per its structure.

Ambiguity that survives the exploration becomes an open question with its alternatives, never a silently chosen default. The human's directional decision arrives later, at `plan-approval`: this stage has no gate, so an open question left in the artifact is how a genuine fork reaches the person who owns it.

## Output

Write the artifact to `{run}/ideation.md`, scaffolded from `references/ideation.template.md` (spec §8.3; the revision log stays empty at creation — `awf-ideate-revise` owns it).

No verdict is rendered here — `ideate-validate` judges this artifact against the brief, and its verdict routes the exploration onward to planning or back through revision.
