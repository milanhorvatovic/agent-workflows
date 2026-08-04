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

Planning is the final stage, so `accept` at `plan-approval` completes the run. What each risk class skips or batches is encoded once in [overlays.md](overlays.md), never here.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    trigger:
      kind: manual
```

Deliverable: the validated, approved plan set — `{run}/phase-{N}-plan.md` per phase — ready for a later `feature` or `bugfix` run to execute.
