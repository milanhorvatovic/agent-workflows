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

direction:                               # present where a gate supplied any; the human's own, so no decided_by
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
| `direction[].text` | per item supplied | what the human asked for, quoted or restated. The list is present where a gate supplied direction and absent where it did not — spec §7 has a `revise` *should* carry direction rather than must, so `trigger: gate` with no direction is a valid revision and not a gap to fill. Gate direction has no finding or question to key to — a plan reaches `plan-approval` on a *passing* validation, so there may be no `F-…` at all — and this is where it goes |
| `direction[].action` | with `text` | `accept` or `escalate` — **not** the finding vocabulary. A finding is a claim the planner may disagree with; direction is the human's instruction, and declining it is not the planner's call. Where it cannot be followed — it would break a phase list that bounds work already planned or done — the answer is `escalate`: the audit records that the planner did not follow it and why, and the plan carries the same thing as an **Open question** addressed to the human at `plan-approval`, which is what actually reaches them. This file is working material and reaches no gate, so an `escalate` recorded only here is a decision nobody sees. Before `plan-approval` fixes the list it is `accept` where the list is the only obstacle: the list is still provisional, `{run}/phase-1-plan.md` resolves to the plan under revision, and escalating would hand the instruction back with nothing the first ask did not already have. Direction blocked by anything else — infeasible, contradicting the brief, departing from a project standard — is `escalate` before approval as after, since `accept` is the only alternative the vocabulary offers and it would buy a plan that fails validation rather than a question the human can answer |
| `direction[].reason` | for escalate | what the direction would require and why the planner cannot decide it; a human's instruction is never silently dropped or quietly deferred |

Every finding and every blocking question in the validation report appears exactly once, and so does every item of gate direction. What catches an omission differs by kind, and the difference is worth stating rather than implying one guarantee covers both. A finding is a defect in the plan, so a decision missing from here surfaces as that same defect on the next pass and `plan-validate` raises it again — the plan is what it re-reads, not this file. Direction is not a defect: a plan that quietly drops "split step 3" is still a valid plan, the **Gate direction** section that asked for it has been returned to `None`, and no validator declares this file. What catches that is the human at the next `plan-approval` — but not from this file, which is working material rather than a declared output and reaches no gate. It is the plan they are given, so an `escalate` states what the change would require in the plan's **Open questions** — non-blocking, since it asks the human whether to change the plan rather than telling the planner the plan is wrong — and the changelog row names the gate as its trigger; this file carries the same decision in the detail an audit wants and the plan cannot hold. An item recorded only here is an item the human never sees. Iteration caps and stall handling live in the planning stage's loop contract, not in this format.
