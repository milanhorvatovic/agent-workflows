# agent-workflows — agent entry point

A protocol, not a platform. Three tiers: **roles** (WHO), **skills** (WHAT), **workflows** (HOW). Markdown artifacts carry state between steps; any agent that can read a prompt can execute the protocol.

This file is the discovery surface: one line per role, skill, workflow, and stage. Load a linked file only when the current step needs it.

## Protocol

- `protocol/spec.md` — the versioned protocol surface: roles, execution modes, risk classes, gates _(pending)_
- `protocol/schemas/` — JSON Schemas: step/handoff, loop contract, trigger, run state _(pending)_

## Roles

_Not yet populated — one line per role._

## Skills

_Not yet populated — one line per skill._

## Workflows

_Not yet populated — one line per workflow and per stage._

## Routing

_How to pick a workflow and classify risk — lands with the `intake` stage._
