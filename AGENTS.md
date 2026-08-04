# agent-workflows — agent entry point

A protocol, not a platform. Three tiers: **roles** (WHO), **skills** (WHAT), **workflows** (HOW). Markdown artifacts carry state between steps; any agent that can read a prompt can execute the protocol.

This file is the discovery surface: one line per role, skill, workflow, and stage. Load a linked file only when the current step needs it.

## Protocol

- `protocol/spec.md` — the versioned protocol surface: roles, execution modes, risk classes, gates, artifacts, orchestration metadata, versioning
- `protocol/schemas/` — JSON Schemas: step/handoff, loop contract, trigger, run state; commented starter fixtures in `examples/`

## Roles

- `roles/analyst.md` — grounding: codebase analysis and requirement parsing, evidence-backed, read-only
- `roles/planner.md` — plans (high-level, detailed, bugfix) and their revisions; phases, dependencies, acceptance criteria
- `roles/implementer.md` — code changes within the scope a plan declares; plan issues become structured feedback
- `roles/reviewer.md` — code, security, and performance review of implementations; findings with severities and fixes
- `roles/validator.md` — artifact validation with categorical verdicts (PASS / PASS_WITH_CONDITIONS / FAIL)
- `roles/arbiter.md` — synthesis between review/validation and planning: dedupes, triages, resolves findings; refutation before acceptance

## Skills

_Not yet populated — one line per skill._

## Workflows

- `workflows/feature.md` — end-to-end feature development: intake → ideation → planning → implementation → review → delivery
- `workflows/bugfix.md` — bugfix without ideation: intake → planning → implementation → review → delivery
- `workflows/plan.md` — planning only: intake → ideation → planning; ends with an approved plan
- `workflows/overlays.md` — risk-class overlays R0–R3: what each class skips, batches, or substitutes, encoded once

### Stages

- `workflows/stages/intake.md` — entry stage of every workflow: clarifying question, risk router, intake gate; outputs brief + risk class
- `workflows/stages/ideation.md` — grounding, distinct approaches with a recommendation, validated under a revise loop
- `workflows/stages/planning.md` — phase plan created, validated, revised; blocking plan-approval gate
- `workflows/stages/implementation.md` — build within the plan's declared scope; validation verdict + machine checks gate the loop
- `workflows/stages/review.md` — fresh-context findings and verdict, arbiter on disagreement, fixes under a capped loop
- `workflows/stages/delivery.md` — delivery artifact, final validation, delivery gate

## Routing

- Pick the workflow by intent: a change to build → `feature`; a known bug to fix → `bugfix`; a plan without execution → `plan`.
- Risk is not picked — the `intake` stage classifies every run (spec §5.2 rubric: blast radius, reversibility, security surface, decomposability, novelty, ambiguity) and the human confirms or overrides at the intake gate.
- The class, not the workflow, decides depth: `workflows/overlays.md` says what R0–R3 skip, batch, or substitute.
