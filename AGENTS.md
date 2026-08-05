# agent-workflows — agent entry point

A protocol, not a platform. Three tiers: **roles** (WHO), **skills** (WHAT), **workflows** (HOW). Markdown artifacts carry state between steps; any agent that can read a prompt can execute the protocol.

This file is the discovery surface: one line per role, skill, workflow, and stage. Load a linked file only when the current step needs it. The lines between `generated:` markers are produced from each file's frontmatter `description` by `scripts/generate_index.py` — edit descriptions at their source, then regenerate; never edit those lines here.

## Protocol

- `protocol/spec.md` — the versioned protocol surface: roles, execution modes, risk classes, gates, artifacts, orchestration metadata, versioning
- `protocol/schemas/` — JSON Schemas: step/handoff, loop contract, trigger, run state; commented starter fixtures in `examples/`

## Roles

<!-- generated:roles -->
- `roles/analyst.md` — Grounding role — investigates the codebase and parses requirements, producing structured, evidence-backed analysis that downstream steps consume. Reads and verifies before concluding; never modifies code.
- `roles/planner.md` — Decomposes confirmed requirements into ordered, verifiable phases with explicit dependencies, risks, and acceptance criteria. Produces and revises plans (high-level, detailed, bugfix) specific enough to implement without guessing.
- `roles/implementer.md` — Executes an approved plan faithfully — clean, production-quality code and tests within the plan's declared scope. Plan issues and deviations become structured feedback for the planner, never silent workarounds.
- `roles/reviewer.md` — Reviews implementations for correctness, security, performance, and maintainability against project standards. Produces specific, actionable findings with severities and suggested fixes; never rewrites the code.
- `roles/validator.md` — Adversarially validates artifacts against their stated requirements — completeness, consistency, feasibility — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL. Identifies issues; never fixes them.
- `roles/arbiter.md` — Synthesis layer between reviewers/validators and the planner — dedupes, triages, and resolves findings into one consolidated report. Institutionalizes disagreement, attempting refutation before accepting any finding and arguing the opposing case when sources agree.
<!-- /generated:roles -->

## Skills

<!-- generated:skills -->
- `skills/awf-analyze-report/SKILL.md` — Distills an existing grounding artifact into a polished, prioritized codebase report for humans — executive summary, architecture and module map, dependency and testing health, technical debt ranked by impact, actionable recommendations, and a developer quick reference — optionally answering specific questions with evidence. Standalone (no stage binds it); triggers when a completed grounding needs a readable deliverable, such as onboarding material, an architecture review, or a codebase health check. It does not explore the codebase itself — producing the grounding first is awf-ground.
- `skills/awf-ground/SKILL.md` — Analyzes the codebase areas a brief touches — structure, patterns, dependencies, constraints — into the run's evidence-backed grounding artifact, which downstream steps consume and may reuse across runs as a cached input. Triggers as the ideation stage's ground step, and whenever a task needs verified codebase context before approaches are explored or a plan is written. Produces the raw grounding, not a human deliverable — distilling an existing grounding into a polished report is awf-analyze-report.
<!-- /generated:skills -->

## Workflows

<!-- generated:workflows -->
- `workflows/feature.md` — End-to-end feature development — intake, ideation, planning, implementation, review, delivery. Composes the six stages by reference; risk-class overlays decide depth.
- `workflows/bugfix.md` — Bugfix without ideation — intake, planning, implementation, review, delivery. The problem is known; the fix wants a validated plan, not solution-space exploration. Risk-class overlays decide depth.
- `workflows/plan.md` — Planning only — intake, ideation, planning. Ends with a validated, human-approved plan; execution is a separate decision. Risk-class overlays decide depth.
- `workflows/overlays.md` — Risk-class overlays R0–R3 — what each class skips, batches, or substitutes across the six stages, encoded once for every workflow. Includes the skip-resolution rules for edges and loop exit criteria that reference skipped content.
<!-- /generated:workflows -->

### Stages

<!-- generated:stages -->
- `workflows/stages/intake.md` — Entry stage of every workflow — confirms the brief through at most one clarifying question, classifies risk with the spec §5.2 rubric, and collects the human's decision at the intake gate. Outputs a confirmed brief artifact and a risk class recorded in run state.
- `workflows/stages/ideation.md` — Explores the solution space before planning — analyst grounding, three to five distinct approaches with a recommendation, adversarial validation, and a capped revise loop. Outputs grounding and ideation artifacts; the validation verdict routes into planning.
- `workflows/stages/planning.md` — Produces the phase plan — planner creates from brief, grounding, and ideation; validator renders the verdict; a capped revise loop converges; the blocking plan-approval gate collects the human decision. Every plan declares its file scope, the contract implementation loops bind to.
- `workflows/stages/implementation.md` — Builds the change within the file scope the plan declares — implementer works from the plan, validator and machine checks gate the loop, scope drift feeds reclassification. Plan defects become structured feedback for plan-revise, never silent scope expansion.
- `workflows/stages/review.md` — Fresh-context review of the implemented change — reviewer findings (code, performance, conditional security), independent validator verdict, arbiter synthesis on disagreement, implementer fixes under a capped loop bound to the plan's scope.
- `workflows/stages/delivery.md` — Closes the run — analyst assembles the delivery artifact from the run's evidence, validator renders the final verdict against the brief's acceptance criteria, and the delivery gate collects the human decision. Every verdict routes to the gate; the human decides with it in view.
<!-- /generated:stages -->

## Routing

- Pick the workflow by intent: a change to build → `feature`; a known bug to fix → `bugfix`; a plan without execution → `plan`.
- Risk is not picked — the `intake` stage classifies every run (spec §5.2 rubric: blast radius, reversibility, security surface, decomposability, novelty, ambiguity) and the human confirms or overrides at the intake gate.
- The class, not the workflow, decides depth: `workflows/overlays.md` says what R0–R3 skip, batch, or substitute.
