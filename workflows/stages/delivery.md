---
name: delivery
description: Closes the run — analyst assembles the delivery artifact from the run's evidence, validator renders the final verdict against the brief's acceptance criteria, and the delivery gate collects the human decision. Every verdict routes to the gate; the human decides with it in view.
---

# Stage: delivery

Closes the run: assemble what shipped, validate it against the brief one last time, and collect the human decision. The delivery gate is the run's last checkpoint and always sees the final validation verdict.

## Steps

### deliver-prepare (analyst)

Synthesize the delivery artifact from the run's evidence — brief, implementation log, validations — into a summary of what changed and why, verification evidence, and a ready-to-use change description for the project's normal shipping channel (for example, a pull request).

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
      output:
        artifact: "{run}/delivery.md"
      on:
        PASS: delivery-approval
        PASS_WITH_CONDITIONS: delivery-approval
        FAIL: delivery-approval
```

### deliver-validate (validator)

Runs with fresh context in every mode (spec §4). The run's final validation: are the brief's acceptance criteria met, is the delivery artifact accurate about what shipped, is any claimed verification actually evidenced? Renders the verdict presented at the gate.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: validator
      inputs:
        - artifact: "{run}/delivery.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/delivery-validation.md"
```

## Gates

- **delivery-approval** — every verdict routes here: the gate fires as the run's last checkpoint regardless, and the human decides with the verdict in view. Transport per risk class ([overlays](../overlays.md)). Outcomes: `accept` completes the run — the change ships by the project's normal channel, with `{run}/delivery.md` as the ready description; `revise` returns to `deliver-prepare`; `reject` ends the run — a rejection of the change itself, not just its description, and the human MAY re-enter an earlier stage in a new phase or run.

## Notes

- Risk-class substitutions for the delivery artifact — R1's minimal change note, R0's exit note — are encoded once in [overlays](../overlays.md), never here.
