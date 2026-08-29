---
name: plan
description: Planning only — intake, ideation, planning. Ends with a validated, human-approved plan; execution is a separate decision. Risk-class overlays decide depth.
---

# Workflow: plan

`intake` → `ideation` → `planning`

Stages by reference (spec §6.1) — each owns its steps, loop contracts, and gates:

1. [stages/intake.md](stages/intake.md) — confirm the brief, classify risk
2. [stages/ideation.md](stages/ideation.md) — ground, explore, and validate approaches
3. [stages/planning.md](stages/planning.md) — phase plan, validated and human-approved

Planning is the final stage, so `accept` at `plan-approval` completes the run. Where the phase-1 plan authored a list with phases after it, those are not planned here, and the reason is the one this workflow is defined by: what makes a later phase's plan sound is the phase before it having been built. Its decisions reach the next planner as code rather than as a document — `plan-create` reads the relevant tree directly wherever grounding does not cover it, and `plan-validate` checks feasibility against that same tree, so phase 2's technical decisions and file contracts are present by the time phase 3 is planned. As a document they do not travel: `implement-validate` records what the work binds for the phases after it, and nothing declares that report into the next phase's planning, `{N}` naming the phase being planned rather than the one before it. This workflow builds nothing, so the carrier that does work is absent too. Planning phase 3 from the phase-1 boundary list alone would miss phase 2's technical decisions, file scope, and resolved open questions, and `plan-validate` reads the same inputs — so two later plans could contradict each other and both pass. The list is what this run delivers for those phases; the `feature` or `bugfix` run that executes them plans each as it reaches it. What each risk class skips or batches is encoded once in [overlays.md](overlays.md), never here.

```yaml
metadata:
  workflow:
    protocol: "0.3"
    trigger:
      kind: manual
```

Deliverable: the validated, approved `{run}/phase-1-plan.md` and the phase list it authors — ready for a later `feature` or `bugfix` run to execute. The handover is import (spec §8.6): the executing run is created importing this run's artifacts — copies adopted under its own id, the steps that produced them populated `skipped`, its own gates still deciding on the copies — and it plans each later phase as it reaches it. What makes the brief part of that handover is its subject: this workflow's brief describes the change to be built — the goal, constraints, and acceptance criteria are the change's own, producing this plan being the run's scope rather than the brief's subject — so the executing run adopts it unchanged, and plan-shaped criteria in a brief are a defect its intake gates `revise`, here or there.
