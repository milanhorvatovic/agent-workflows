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

_Not yet populated — one line per workflow and per stage._

## Routing

_How to pick a workflow and classify risk — lands with the `intake` stage._
