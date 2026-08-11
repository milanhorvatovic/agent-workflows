---
name: feature
description: End-to-end feature development — intake, ideation, planning, implementation, review, delivery. Composes the six stages by reference; risk-class overlays decide depth.
---

# Workflow: feature

`intake` → `ideation` → `planning` → `implementation` → `review` → `delivery`

Stages by reference (spec §6.1) — each owns its steps, loop contracts, and gates:

1. [stages/intake.md](stages/intake.md) — confirm the brief, classify risk
2. [stages/ideation.md](stages/ideation.md) — ground, explore, and validate approaches
3. [stages/planning.md](stages/planning.md) — phase plan, validated and human-approved
4. [stages/implementation.md](stages/implementation.md) — build within the plan's declared scope
5. [stages/review.md](stages/review.md) — fresh-context findings, verdict, fixes
6. [stages/delivery.md](stages/delivery.md) — delivery artifact, final validation, delivery gate

A multi-phase run repeats planning → implementation per phase, the phase list authored by the phase-1 plan and fixed for the run by `plan-approval`; review and delivery run once, after the final phase. What each risk class skips or batches is encoded once in [overlays.md](overlays.md), never here.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    trigger:
      kind: manual
```

Deliverable: the implemented change, accepted at `delivery-approval` with `{run}/delivery.md` as its ready description.
