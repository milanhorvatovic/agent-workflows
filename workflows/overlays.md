---
name: overlays
description: Risk-class overlays R0–R3 — what each class skips, batches, or substitutes across the six stages, encoded once for every workflow. Includes the skip-resolution rules for edges and loop exit criteria that reference skipped content.
---

# Risk-class overlays

Overlays decide how much of a workflow runs; workflow files never do (spec §6.1). The class is proposed at intake, overridable at the intake gate, and reclassifiable upward mid-run (spec §5.3). The normative class definitions live in spec §5.1; this file maps them onto the stages and gates by id.

## Stage participation

| Stage | R0 exploratory | R1 trivial | R2 standard | R3 high |
| --- | --- | --- | --- | --- |
| `intake` | runs | runs | runs | runs |
| `ideation` | skipped | skipped | runs | runs |
| `planning` | skipped | skipped | runs | runs |
| `implementation` | free work, no role split | `implement` only | all steps | all steps |
| `review` | skipped | skipped | runs; `review-security` conditional | runs; `review-security` and `review-arbitrate` mandatory |
| `delivery` | exit note only | `deliver-prepare` only | runs | runs |

- **Intake precedes the class:** its analyst steps run for every run — classification happens there. The Roles row of spec §5.1 names each class's substantive pipeline roles; a stage that runs still executes its steps under their declared roles, an `inline` session persona-switching as needed (spec §4).
- **Mode:** `inline` at R0–R2, `isolated` per role at R3; `reviewer` and `validator` steps run fresh-context in every mode (spec §4).
- **Machine checks:** optional at R0; required at R1–R3.
- **Arbiter:** at R2 only on reviewer/validator disagreement; at R3 mandatory.
- **Security review:** never at R0/R1; at R2 when the change touches auth, crypto, input handling, or dependencies; at R3 always.

## Gate transports

| Gate | R0 | R1 | R2 | R3 |
| --- | --- | --- | --- | --- |
| `clarifying-question` | blocking when it fires | blocking when it fires | blocking when it fires | blocking when it fires |
| `intake-approval` | inbox | inbox | inbox | blocking |
| `plan-approval` | — | — | blocking | blocking |
| `delivery-approval` | — | inbox | inbox | blocking |

`—` means the gate never fires because its stage is skipped. At R3, transports MAY be configured per gate (spec §7).

## Skip resolution

- A skipped stage's steps are recorded `status: skipped` in run state; skipped conditional steps likewise.
- An edge or stage id targeting skipped content resolves to the next non-skipped point in composition order.
- A loop exit criterion naming a skipped step's output artifact is waived; the remaining criteria still bind. At R1 the implementation loop therefore exits on machine checks alone.
- A step whose validating step is skipped produces no verdict: its `on` edges are waived and it proceeds in composition order. At R1, `deliver-prepare` reaches `delivery-approval` this way — `deliver-validate` is skipped, so no verdict fires the edges.

## Substitutions

- **R0 delivery:** the deliverable is `{run}/exit-note.md` — what was tried, what was learned — written free-form by the agent, not by any declared step: R0 runs no structured steps after intake. All other artifacts live in a scratch directory and are discardable; no `delivery-approval` gate fires.
- **R1 delivery:** `deliver-prepare` runs as declared — in `inline` mode the run's single session persona-switches into the step's analyst role (spec §4) — and writes `{run}/delivery.md` with minimal change-note content; `deliver-validate` is skipped — R1 has no validator, machine checks and the gate stand in — and `delivery-approval` reads the minimal artifact.
