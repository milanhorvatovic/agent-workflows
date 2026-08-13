---
name: awf-deliver-prepare
description: Assembles the run's delivery artifact from its own evidence — what changed and why, the verification actually performed with the evidence behind it, and a ready-to-use change description in the project's PR or change-note format — as the one document the delivery gate and the shipping channel both read. Triggers as the delivery stage's deliver-prepare step once the run's earlier stages have exited, again on a delivery-gate revise outcome, and at R1 where it is the stage's only step and writes minimal change-note content. It describes what shipped and never ships it — pushing the change through the forge stays the consumer's channel, sketched in references/shipping.md — and it renders no verdict, the judgment on this artifact being awf-deliver-validate's.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-log.md"
          required: true
        - artifact: "{run}/phase-{P}-impl-validation.md"
          required: false
        - artifact: "{run}/review-validation.md"
          required: false
        - artifact: "{run}/review-fixes.md"
          required: false
        - artifact: "{run}/phase-{P}-plan.md"
          required: false
        - artifact: "{run}/delivery.md"
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
- `{run}/phase-{P}-impl-log.md` (required) — the implementer's record for every phase of the run: steps, decisions, declared deviations, commits, and machine-check evidence. Implementation runs wherever this step does, so this input always exists; a multi-phase run has one log per phase and all of them are read.
- `{run}/review-fixes.md` (optional) — where a review loop's own commits and its current machine-check result live, `review-fix` refreshing both in place there. Optional on two counts: the review stage is skipped at R0 and R1, and even where it runs, `review-fix` only runs on an iteration the loop has not exited — so a review that passes on its first pass produces no fix record at all. Optional makes it reachable by §8.4's cache, so the freshness check binds here too: usable only where its `Run` header matches this run, and its **Iteration** is the loop's last — an earlier run's fix record would supply commits and a check result belonging to a different change. Where it did run, this is the current evidence and the implementation logs hold the state as of implementation, so a verification claim assembled from the logs alone would describe the change as it stood before the review fixed anything.
- `{run}/phase-{P}-impl-validation.md` (optional) — the implementation verdicts, absent at R1 where the validator is skipped. Optional here means possibly skipped, never satisfied from an earlier run: the grounding cache of spec §8.4 does not apply to a record of this run.
- `{run}/review-validation.md` (optional) — the review verdict and the conditions attached to it, absent where the review stage's validator did not run.
- `{run}/phase-{P}-plan.md` (optional) — each phase's validated **Rollback** section, which is where the reverse migrations, the configuration to restore, and the integrations to disconnect were actually worked out; the logs do not carry them, and an executor materializing only declared inputs would otherwise leave this step inventing a rollback path or omitting one. Optional because planning is skipped at R0 and R1, where the artifact is an exit note or a minimal change note and omits the rollback section entirely. Never satisfied from another run: because the input is optional, spec §8.4 would otherwise admit a cached plan, and a rollback path copied from a different change is worse than none — check the plan's `Run` header against this run and treat a mismatch as absent, the same guard `review-fix` applies to the arbiter's resolution. Where it is absent at R2 or R3, the path back is only what the diff and the logs support, said as much rather than filled in from assumption.
- The change itself, read directly — the diff is what the artifact describes, and it settles any disagreement with the logs: a change the diff carries and no log mentions still shipped and still belongs in the summary.
- The project's rendered PR or change-note standard, where one exists — it fixes the shape of the change description this step writes, over any ordering suggested here.
- `{run}/delivery.md` (optional) — this step's own prior output, which a `revise` rewrites rather than replaces, and where the human's direction is waiting: what they want said differently is recorded in its **Gate direction** section before the outcome is (spec §7), so no separate input carries it. Fold each item into the sections it is about and return that one to `None` — direction left there would ship alongside the change it was about. Optional on availability: on a first pass the artifact cannot precede the step that writes it, and its absence is what says this is the first pass. Optional here means not yet written, never satisfied from an earlier run: the spec §8.4 cache does not apply to a record of this run.

## Method

Read the brief first, then every phase log, then the diff as a whole; the artifact is written from the diff with the logs as the account of how it got there.

Describe changes by what they do for the brief, not by file: group related edits into the change they add up to, name the user- or system-visible effect, and give the reason from the brief or from a decision the log records. Mechanical restatement of the diff is not a summary. Deviations the logs declare are reported as part of what shipped, with their rationale — the gate reads this artifact to decide, and a deviation it learns about later is a surprise the artifact was supposed to prevent.

Report verification as evidence, not assertion: which machine checks ran and their result, which tests cover the new behavior, and what the validators of this change concluded — the implementation validation per phase, and the review validation where that stage ran — including conditions attached to a PASS_WITH_CONDITIONS and any finding left open by an accepted verdict. Where a validation artifact is absent because its step was skipped for the risk class, say so — an absent verdict is a fact about the run, not a gap to paper over.

Then write the change description in the project's format: the rendered PR or change-note standard fixes the title convention, the section shape, and the checklist, so follow it rather than this skill's ordering; where the project has no such standard, use the artifact's own change-description section as-is. Load `references/shipping.md` when the change must actually reach the project's channel — how the description is used, and what stays the consumer's decision.

Close on what the change carries forward once it is live, filling the template's last two sections by name. **Risks and rollback** takes the risks worth naming, the signals that would show them, and the path back — the revert, the migrations that need reversing, the flags to flip. **Follow-ups** takes what this run deliberately left: the findings-for-planning the logs raised, the findings left open under an accepted verdict, and the gaps the logs record, each with its id and where it is recorded. Both draw only on the sources this step already reads, and neither is an invitation to invent work the run never considered. "None" is a legitimate answer for **Follow-ups** — a run can genuinely leave nothing behind. It is not one for **Risks and rollback**: a change that shipped can be undone, so that section states the path back or says why there is none for this change, which is a fact worth knowing rather than a blank.

At R1 the artifact is a minimal change note per the risk-class overlays — summary, what changed, the verification that ran, and the change description. The sections the template marks as omitted at R1 are left out entirely rather than filled with placeholders.

On a `delivery-approval` `revise`, rewrite the artifact against the human's direction rather than regenerating it from the evidence: the run's evidence has not changed, so a regeneration reproduces the document the gate just declined. Their direction lands in the sections it is about, and where it disputes a claim this artifact makes — a verification reported as performed, a criterion tabled as met — the claim is re-checked against the evidence rather than restated more confidently, since the honest answer may be that the criterion is unmet and the table says so.

## Output

Write the artifact to `{run}/delivery.md`, scaffolded from `references/delivery.template.md` (spec §8.3; load it before assembling, since it fixes the section order and the evidence tables). Every claim in it traces to the brief, a log entry, a validation verdict, a plan, or the diff.

No verdict is rendered here — `deliver-validate` judges this artifact against the brief where the risk class runs it, and the `delivery-approval` gate collects the human decision with that verdict in view, or with the artifact alone at R1, where the validator is skipped. A `revise` outcome at the gate returns here with the human's direction.
