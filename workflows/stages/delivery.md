---
name: delivery
description: Closes the run — analyst assembles the delivery artifact from the run's evidence, validator renders the final verdict against the brief's acceptance criteria, and the delivery gate collects the human decision. Every verdict routes to the gate; the human decides with it in view.
---

# Stage: delivery

Closes the run: assemble what shipped, validate it against the brief one last time, and collect the human decision. Where the delivery gate fires it is the run's last checkpoint, and the only one this stage's verdict reaches — wherever `deliver-validate` runs, the gate sees what it rendered. Where the risk class skips the validator there is no verdict to see: at R1 the gate reads the artifact alone, and at R0 neither step nor gate fires ([overlays](../overlays.md)).

## Steps

### deliver-prepare (analyst)

Synthesize the delivery artifact from the run's evidence — brief, implementation logs, the review loop's own fix record, validations — into a summary of what changed and why, verification evidence, and a ready-to-use change description for the project's normal shipping channel (for example, a pull request). The implementation logs are required — implementation runs in every class where this step does, one log per completed phase; the validation artifacts stay optional, validator steps being skipped at R1. `{run}/review-fixes.md` is optional too, and this step states the §9.1 freshness check that optional makes necessary: its `Run` header must match this run and its **Iteration** be the loop's last, since where a review loop ran it holds the current machine-check result and commit list while the logs hold the state as of implementation. The step also declares `{run}/gate-direction.md` for what a returning human asked, and its own output optionally: a `delivery-approval` `revise` returns here, and rewriting the artifact against the human's direction is an instruction that depends on it (spec §9.1), absent only on the first pass where nothing precedes the step that writes it.

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
          required: true
        - artifact: "{run}/phase-{N}-impl-validation.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
        - artifact: "{run}/review-fixes.md"
          required: false
        - artifact: "{run}/phase-{N}-plan.md"
          required: false
        - artifact: "{run}/delivery.md"
          required: false
        - artifact: "{run}/gate-direction.md"
          required: false
      output:
        artifact: "{run}/delivery.md"
      on:
        PASS: delivery-approval
        PASS_WITH_CONDITIONS: delivery-approval
        FAIL: delivery-approval
```

### deliver-validate (validator)

Runs with fresh context in every mode (spec §4). The run's final validation: are the brief's acceptance criteria met, is the delivery artifact accurate about what shipped, is any claimed verification actually evidenced? Both steps declare `{run}/review-fixes.md`, optional on two counts — the review stage is skipped at R0 and R1, and `review-fix` runs only on an iteration the loop has not exited, so a review passing first time writes no fix record either: where it did, that artifact holds the loop's commits and its current machine-check result, and the implementation logs hold the state as of implementation — so a verification claim checked against the logs alone is checked against evidence predating every fix the review forced. Both state the §9.1 freshness check that optional makes necessary: the `Run` header must match this run, and the **Iteration** must be the loop's last. Renders the verdict presented at the gate. The implementation logs are required — delivery composes only into workflows that implement, so the logs the artifact's evidence claims come from always exist, one per completed phase. The validation artifacts stay optional, though not for `deliver-prepare`'s reason — this step does not run at R1 at all. They are optional because reclassification applies the new class's defaults to subsequent steps only (spec §5.3): a run bumped upward during implementation arrives here with no implementation validation behind it, and one bumped after the review stage was skipped with no review validation either. Where they exist they are the sources the artifact's quoted verdicts and conditions are checked against, which the step cannot do on the artifact's own word.

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
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{N}-impl-validation.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
        - artifact: "{run}/review-fixes.md"
          required: false
        - artifact: "{run}/phase-{N}-plan.md"
          required: false
      output:
        artifact: "{run}/delivery-validation.md"
```

## Gates

- **delivery-approval** — every verdict routes here: the gate fires as the run's last checkpoint regardless, and the human decides with the verdict in view. Transport per risk class ([overlays](../overlays.md)). Outcomes: `accept` completes the run — the change ships by the project's normal channel, with `{run}/delivery.md` as the ready description; `revise` returns to `deliver-prepare`, carrying what the human wants changed about the description — written to `{run}/gate-direction.md` before the outcome is recorded and never into the gate record (spec §7), for `deliver-prepare` to rewrite against rather than to copy into the artifact; `reject` ends the run — a rejection of the change itself, not just its description, and the human MAY re-enter an earlier stage in a new phase or run.

## Notes

- `{N}` ranges over every completed phase in this stage's inputs, rather than naming the current phase as it does in the per-phase stages ([planning](planning.md)): delivery closes the run, so a multi-phase run's artifact and its validation cover every phase's log and verdicts, not just the last one's.
- Risk-class reductions of the delivery artifact — R1's minimal change-note content, R0's free-form exit note — are encoded once in [overlays](../overlays.md), never here.
- At R1 `deliver-validate` is skipped and no verdict exists: `deliver-prepare`'s `on` edges are waived per the skip-resolution rules ([overlays](../overlays.md)), and the gate still fires in composition order.
