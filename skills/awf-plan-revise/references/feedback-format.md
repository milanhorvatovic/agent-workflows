# Plan feedback format — the revision decision audit

The YAML structure recording what each revision iteration decided: one decision per validation finding, one resolution per question, one entry per item of direction a gate sent back. Produced by `awf-plan-revise` at every iteration — decisions the human supplied (via the plan-approval gate's `revise` outcome) are recorded as theirs; the rest are the planner's own. The file is the audit trail that makes a revised plan explainable: anyone can trace which finding produced which change, what was rejected and why, and who decided.

Only `plan-revise` and the human consume this format. It is working material in the run directory, not a gated artifact.

## Naming

`{run}/phase-{N}-plan-feedback-{iteration}.yaml` — one file per revision iteration, 1-based, matching the changelog row the same iteration appends to the plan.

## Format

```yaml
plan: "phase-1-plan.md"                  # the plan artifact revised, relative to {run}
validation: "phase-1-plan-validation.md" # the validation report responded to
iteration: 1                             # 1-based, matches the plan's changelog row
trigger: validation                      # validation | gate | implementation | cascade

decisions:
  - finding: "F-001"                     # stable finding id from the validation report
    action: accept                       # accept | reject | defer
    decided_by: planner                  # planner | human
    reason: ""                           # required for reject and defer

  - finding: "F-002"
    action: reject
    decided_by: human
    reason: "Intentional: the brief's out-of-scope section excludes this surface"

  - finding: "F-003"
    action: defer
    decided_by: planner
    reason: "Belongs to phase 3 per the phase list; recorded in the plan's risks"

questions:
  - id: "Q-001"                          # stable question id from the validation report
    text: "Should auth use JWT or session cookies?"
    resolved_by: human                   # human | planner | open
    answer: "JWT"
    alternatives:                        # options considered, when they exist
      - "JWT — stateless, fits the API consumers"
      - "Session cookies — simpler, fits the current stack"

direction:                               # present when trigger is gate; the human's own, so no decided_by
  - text: "Split step 3 — the migration and the backfill want separate reviews"
    action: accept                       # accept | escalate — never reject or defer
    reason: ""                           # required for escalate
```

## Fields

| Field | Required | Values / notes |
| --- | --- | --- |
| `plan` | yes | plan artifact filename, relative to `{run}` |
| `validation` | yes | validation report responded to |
| `iteration` | yes | 1-based; matches the plan changelog row |
| `trigger` | yes | `validation` (revise loop), `gate` (plan-approval `revise`), `implementation` (escalated feedback), `cascade` (another phase's revision) |
| `decisions[].finding` | yes | finding id from the validation report (`F-…`) |
| `decisions[].action` | yes | `accept` (revise accordingly), `reject` (disagree, skip), `defer` (address later, recorded in the plan) |
| `decisions[].decided_by` | yes | `planner` or `human` — human decisions are followed, not re-argued |
| `decisions[].reason` | for reject/defer | why; optional for accept |
| `questions[].id` / `questions[].text` | yes | carried from the validation report (`Q-…`) |
| `questions[].resolved_by` | yes | `human`, `planner`, or `open` — `open` means it moved to the plan's open questions, unanswered |
| `questions[].answer` | unless open | the chosen answer |
| `questions[].alternatives` | no | options considered |
| `direction[].text` | when `trigger` is `gate` | what the human asked for, quoted or restated. Gate direction has no finding or question to key to — a plan reaches `plan-approval` on a *passing* validation, so there may be no `F-…` at all — and this is where it goes |
| `direction[].action` | with `text` | `accept` or `escalate` — **not** the finding vocabulary. A finding is a claim the planner may disagree with; direction is the human's instruction, and declining it is not the planner's call. Where it cannot be followed — it would break a phase list that bounds work already planned or done — the answer is `escalate`, returning what the change would cost to the human who asked. Revising phase 1 it is `accept`: `{N}` is 1, `{run}/phase-1-plan.md` resolves to the plan under revision, nothing has been built against the list, and escalating would hand the instruction back with nothing the first ask did not already have |
| `direction[].reason` | for escalate | what the direction would require and why the planner cannot decide it; a human's instruction is never silently dropped or quietly deferred |

Every finding and every blocking question in the validation report appears exactly once, and so does every item of gate direction — a finding without a decision is the omission `plan-validate` will catch on the next pass. Iteration caps and stall handling live in the planning stage's loop contract, not in this format.
