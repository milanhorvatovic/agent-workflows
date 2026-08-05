---
name: awf-deliver-prepare
description: Assembles the run's delivery artifact from its own evidence — what changed and why, the verification actually performed with the evidence behind it, and a ready-to-use change description in the project's PR or change-note format — as the one document the delivery gate and the shipping channel both read. Triggers as the delivery stage's deliver-prepare step once the run's earlier stages have exited, again on a delivery-gate revise outcome, and at R1 where it is the stage's only step and writes minimal change-note content. It describes what shipped and never ships it — pushing the change through the forge stays the consumer's channel, sketched in references/shipping.md — and it renders no verdict, the judgement on this artifact being awf-deliver-validate's.
license: MIT
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
      output:
        artifact: "{run}/delivery.md"
        template: references/delivery.template.md
      on:
        PASS: delivery-approval
        PASS_WITH_CONDITIONS: delivery-approval
        FAIL: delivery-approval
---

# Skill: awf-deliver-prepare

Closes the run's account of itself: what was asked, what changed, how it was verified, and the change description the project's shipping channel needs. The artifact serves two readers at once — the human at the delivery gate, deciding with it in view, and whoever opens the change downstream — so it must stand alone, without the run's other artifacts at hand.

## Role

The step runs as the analyst assembling a final deliverable from evidence: precise, complete, and honest about what was not done. It synthesizes the run's record; it does not re-review the change, re-run its verification, or improve on it. Nothing is claimed here that the run's evidence does not support — an unverified acceptance criterion is reported as unverified, never quietly summarized as met.

## Inputs

- `{run}/brief.md` (required) — the intent and the acceptance criteria the delivery is described against; the "why" every change is traced back to.
- `{run}/phase-{N}-impl-log.md` (required) — the implementer's record for every phase of the run: steps, decisions, declared deviations, commits, and machine-check evidence. Implementation runs wherever this step does, so this input always exists; a multi-phase run has one log per phase and all of them are read.
- `{run}/phase-{N}-impl-validation.md` (optional) — the implementation verdicts, absent at R1 where the validator is skipped. Optional here means possibly skipped, never satisfied from an earlier run: the grounding cache of spec §8.4 does not apply to a record of this run.
- `{run}/review-validation.md` (optional) — the review verdict and the conditions attached to it, absent where the review stage's validator did not run.
- The change itself, read directly — the diff is what the artifact describes, and it settles any disagreement with the logs: a change the diff carries and no log mentions still shipped and still belongs in the summary.
- The project's rendered PR or change-note standard, where one exists — it fixes the shape of the change description this step writes, over any ordering suggested here.

## Method

Read the brief first, then every phase log, then the diff as a whole; the artifact is written from the diff with the logs as the account of how it got there.

Describe changes by what they do for the brief, not by file: group related edits into the change they add up to, name the user- or system-visible effect, and give the reason from the brief or from a decision the log records. Mechanical restatement of the diff is not a summary. Deviations the logs declare are reported as part of what shipped, with their rationale — the gate reads this artifact to decide, and a deviation it learns about later is a surprise the artifact was supposed to prevent.

Report verification as evidence, not assertion: which machine checks ran and their result, which tests cover the new behavior, and what the validators of this change concluded — the implementation validation per phase, and the review validation where that stage ran — including conditions attached to a PASS_WITH_CONDITIONS and any finding left open by an accepted verdict. Where a validation artifact is absent because its step was skipped for the risk class, say so — an absent verdict is a fact about the run, not a gap to paper over.

Then write the change description in the project's format: the rendered PR or change-note standard fixes the title convention, the section shape, and the checklist, so follow it rather than this skill's ordering; where the project has no such standard, use the artifact's own change-description section as-is. Load `references/shipping.md` when the change must actually reach the project's channel — how the description is used, and what stays the consumer's decision.

At R1 the artifact is a minimal change note per the risk-class overlays — summary, what changed, the verification that ran, and the change description. The sections the template marks as omitted at R1 are left out entirely rather than filled with placeholders.

## Output

Write the artifact to `{run}/delivery.md`, scaffolded from `references/delivery.template.md` (spec §8.3; load it before assembling, since it fixes the section order and the evidence tables). Every claim in it traces to the brief, a log entry, a validation verdict, or the diff.

No verdict is rendered here — `deliver-validate` judges this artifact against the brief, and the `delivery-approval` gate collects the human decision with that verdict in view. A `revise` outcome at the gate returns here with the human's direction.
