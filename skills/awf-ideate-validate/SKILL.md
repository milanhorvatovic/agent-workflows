---
name: awf-ideate-validate
description: Adversarially validates the run's ideation artifact against the brief — do the approaches actually cover what the brief asks, are they genuinely distinct rather than one idea renamed, are their feasibility and impact claims true of the real codebase, are the risks honest, does the recommendation follow from the artifact's own evidence? — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report the ideation loop consumes. Triggers as the ideation stage's ideate-validate step, fresh-context in every mode, after awf-ideate or awf-ideate-revise writes the artifact. The scoring matrix in references/evaluation-matrix.md is its working method, never its output — a total never outranks a critical finding. It identifies issues and asks questions, never fixes them — rewriting the ideation against these findings is awf-ideate-revise, and the verdict on the plan that later descends from it is awf-plan-validate's.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/ideation.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/ideation-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-ideate-validate

Renders the verdict on the exploration: does this artifact justify committing the run to one approach? The verdict routes the ideation loop (spec §9.2) and nothing reaches planning past an exploration this step has not passed — so the job is to find where the space is under-explored, where a claim is unverified, and where the recommendation rests on something the artifact never established.

## Role

The step runs as the validator, always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never fix, never rewrite the recommendation, never contribute the sixth approach. An approach the artifact missed is a finding that the space is under-explored, not a contribution to it.

## Inputs

- `{run}/ideation.md` (required) — the artifact under validation, read in full before judging.
- `{run}/brief.md` (required) — the requirements source: its goal, constraints, and acceptance criteria are the bar the approach set is measured against.

The grounding is deliberately not an input. Feasibility and impact claims are verified against the codebase itself, which is stronger than checking them against a sibling artifact: the question is whether a claim is true, not whether it was faithfully copied.

## Method

Check coverage first: walk the brief's requirements, constraints, and acceptance criteria, and establish that the recommended approach can satisfy each one. A criterion no candidate approach addresses is a critical finding regardless of how elegant the candidates are — an exploration that solved a different problem is the most expensive failure to discover downstream.

Test distinctness structurally. Approaches touching the same modules with the same data flow, differing only in naming or parameters, are one approach counted twice; say which ones collapse into which. A set of five with three duplicates does not meet the stage's three-to-five distinct approaches, and reporting it as a distinctness finding is what keeps the revision from renaming its way out.

Verify feasibility against the codebase, not against plausibility. Modules, extension points, interfaces, and dependencies an approach relies on are checked to exist and to work as claimed; library and platform capabilities asserted in passing are checked. Complexity ratings are checked against the impact the approach actually describes — a "low complexity" approach touching a dozen modules is a finding.

Interrogate the risks. An approach whose risks are absent, cosmetic, or all conveniently minor is under-analyzed: name the risks the artifact omitted — migration, backwards compatibility, operational burden, security surface, performance under real load, lock-in, and the cost of reversing the choice later. Do the same for the discarded set: an option ruled out for a reason that does not hold is a finding, because it narrowed the space wrongly.

Then test the recommendation against the artifact's own evidence. It must follow from the advantages and risks recorded above it; a recommendation that contradicts its own risk table, that rests on a criterion the brief never states, or whose "what would overturn it" is absent or unfalsifiable is a finding. Where refinement was done, check that every recorded risk has a mitigation, acceptance, or deferral, and that no plan has quietly formed inside the ideation.

Score the candidates with `references/evaluation-matrix.md` — load it before comparing — to make the comparison explicit and repeatable. The matrix is working method: it structures the findings and explains the verdict, and it never substitutes for either. A high total never outranks a critical finding, and the report renders a verdict, not a ranking (spec §3.3).

## Output

Write the report to `{run}/ideation-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`). Every finding carries a stable id, severity, location, issue, impact, and recommendation; questions are separated from findings, blocking from non-blocking. Append the stage's own rows to the checklist: **Distinctness** — the candidates differ in shape, not in naming; **Recommendation grounding** — the recommendation follows from the artifact's stated advantages, risks, and the brief's constraints.

Exactly one verdict — PASS, PASS_WITH_CONDITIONS, or FAIL (spec §3.3) — with unresolved critical findings or blocking questions forcing FAIL. The verdict is consumed by the ideation loop's exit criteria and routes the exploration onward to planning or back to `ideate-revise`.
