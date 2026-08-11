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

Planning is the final stage, so `accept` at `plan-approval` completes the run — once there is nothing left to plan. Where the phase-1 plan authored a list with phases after it, `accept` enters the next phase and planning repeats, and only the last phase's acceptance ends the run; the deliverable below is the whole set, so stopping at phase 1 would ship a list of phases with a plan for one of them. What repeats here is planning alone: this workflow has no implementation, so each later plan is written against the phase-1 list and the plans before it rather than against work already done, which is what makes the set producible without executing any of it. What each risk class skips or batches is encoded once in [overlays.md](overlays.md), never here.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    trigger:
      kind: manual
```

Deliverable: the validated, approved plan set — `{run}/phase-{N}-plan.md` per phase — ready for a later `feature` or `bugfix` run to execute.
