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

Planning is the final stage, so `accept` at `plan-approval` completes the run. Where the phase-1 plan authored a list with phases after it, those are not planned here, and the reason is the one this workflow is defined by: what makes a later phase's plan sound is the phase before it having been built, with `implement-validate` reporting what that work binds for the phases the list places after it. This workflow has no implementation and so no such carrier. Planning phase 3 from the phase-1 boundary list alone would miss phase 2's technical decisions, file scope, and resolved open questions, and `plan-validate` reads the same inputs — so two later plans could contradict each other and both pass. The list is what this run delivers for those phases; the `feature` or `bugfix` run that executes them plans each as it reaches it. What each risk class skips or batches is encoded once in [overlays.md](overlays.md), never here.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    trigger:
      kind: manual
```

Deliverable: the validated, approved `{run}/phase-1-plan.md` and the phase list it authors — ready for a later `feature` or `bugfix` run to execute, which plans each later phase as it reaches it.
