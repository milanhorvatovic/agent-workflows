---
name: bugfix
description: Bugfix without ideation — intake, planning, implementation, review, delivery. The problem is known; the fix wants a validated plan, not solution-space exploration. Risk-class overlays decide depth.
---

# Workflow: bugfix

`intake` → `planning` → `implementation` → `review` → `delivery`

Stages by reference (spec §6.1) — each owns its steps, loop contracts, and gates:

1. [stages/intake.md](stages/intake.md) — confirm the brief, classify risk
2. [stages/planning.md](stages/planning.md) — fix plan, validated and human-approved
3. [stages/implementation.md](stages/implementation.md) — fix within the plan's declared scope
4. [stages/review.md](stages/review.md) — fresh-context findings, verdict, fixes
5. [stages/delivery.md](stages/delivery.md) — delivery artifact, final validation, delivery gate

No `ideation` stage, so no dedicated grounding step: `plan-create`'s grounding input is optional (spec §8.4) and MAY be satisfied from a fresh previous run's artifact. Security review is a risk consequence, not a workflow property — the intake rubric bumps any security-surface signal to at least R2 with security review enabled ([overlays.md](overlays.md)).

```yaml
metadata:
  workflow:
    protocol: "0.3"
    trigger:
      kind: manual
```

Deliverable: the fix, accepted at `delivery-approval` — at R1, `{run}/delivery.md` reduced to a minimal change note.
