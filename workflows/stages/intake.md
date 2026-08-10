---
name: intake
description: Entry stage of every workflow — confirms the brief through at most one clarifying question, classifies risk with the spec §5.2 rubric, and collects the human's decision at the intake gate. Outputs a confirmed brief artifact and a risk class recorded in run state.
---

# Stage: intake

The entry stage of every workflow (spec §6.2). Three parts, in order: the clarifying-question gate, the risk router, the intake gate. Outputs: a confirmed `{run}/brief.md` and a risk class with a one-line rationale in run state.

## Steps

### brief-confirm (analyst)

Parse the request and restate it as a brief: goal, constraints, acceptance criteria, and what is explicitly out of scope. If the request's ambiguity is above threshold — the brief cannot be restated with confidence — stop at the `clarifying-question` gate and ask exactly one question, then fold the answer into the brief. One cheap question here beats a full revision loop later.

Both intake gates return here on a `revise`, so the step declares its own output as an optional input — which is also where the human's direction is waiting, in the brief's **Gate direction** section (spec §7) rather than in a declaration of its own: a re-entry revises the brief it already wrote rather than re-drafting from the request, which is an instruction that depends on the artifact (spec §9.1). Optional on availability — on a first run nothing precedes the step that writes it, and the absence is what marks a first run — and never satisfied from the spec §8.4 cache, being this run's restatement of this run's request.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: false
      output:
        artifact: "{run}/brief.md"
```

### risk-route (analyst)

Apply the classification rubric (spec §5.2) to the confirmed brief and propose at most one risk class with a one-line rationale, appended to the brief as a `## Routing` section. Two rubric rules bind: any security-surface signal proposes at least R2 with security review enabled, and ambiguity above threshold withholds the class and routes back to the clarifying question rather than inflating it — at most, because that is the case where no class is proposed at all. The executor transcribes the accepted class into `run.risk` and `run.risk_rationale`; the router only proposes.

Three of the six signals — blast radius, decomposability, novelty — are claims about the codebase rather than about the brief, so a grounding is a cacheable optional input (spec §8.4): intake precedes the ideation stage's `ground` step, and a first run in a codebase has none.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/grounding.md"
          required: false
      output:
        artifact: "{run}/brief.md"
```

## Gates

- **clarifying-question** — conditional: fires only when ambiguity is above threshold, and sits before `risk-route`, so `accept` resumes at classification, and returns through `brief-confirm` to get there whichever step raised the question: an answer can change the goal, a constraint or a criterion, restating the brief is `brief-confirm`'s work, and composition carries the run on to classification once it has folded the answer in. Routing only the questions `risk-route` raised would leave the ones `brief-confirm` raised with their answer recorded and never applied, since `risk-route` reads an amended brief rather than amending one. Either step can: `brief-confirm` when the brief cannot be restated with confidence, `risk-route` when the rubric's ambiguity signal is above threshold, which routes here instead of inflating the class (spec §5.2) and proposes no class until the answer lands. Blocking whenever it fires, in every risk class — a question is waiting for its answer. Outcome vocabulary: record `accept` when the answer confirms the (possibly amended) brief — the answer is recorded in the brief's **Gate direction** section before the outcome is recorded, never in the gate record (spec §7), and the step that resumes folds its content into the sections it is about; record `revise` when the answer redirects the brief enough to need a re-draft, returning to `brief-confirm` as an explicit edge rather than by the spec §7 default — either step can raise this gate and both declare `{run}/brief.md` as their output, so the default names two producers, and of the two only `brief-confirm` can re-draft; `reject` ends the run.
- **intake-approval** — after `risk-route`: the human sees the confirmed brief and the proposed class, and MAY override the class (spec §5.3). Transport per risk class ([overlays](../overlays.md)). Outcomes: `accept` proceeds to the next stage in composition order; `revise` returns to `brief-confirm` — an explicit edge, because both steps of this stage declare `{run}/brief.md` as their output, so spec §7's default of returning to the step that produced the gated artifact names two of them, and `brief-confirm` is the one that can act: a class disagreement is corrected by amending what the rubric reads, and `risk-route` re-runs after it in composition order either way — carrying whatever the human wants changed, recorded in the brief's **Gate direction** section before the outcome and never in the gate record (spec §7), for `brief-confirm` to fold into the brief; a `revise` that states none returns the brief to a step with nothing to work from; `reject` ends the run. An override **to R2** resting on a security surface whose **Security surface** value in the brief's `## Routing` section begins with `no` is a `revise` rather than an `accept` carrying the new class: that leading word of the value, not the presence of the field, is what the R2 security-review condition is evaluated against ([overlays](../overlays.md)), so a class raised past it buys R2's process and skips the pass it was raised for. Accepting the higher class cannot correct the reading — the brief has to come back naming that surface for `risk-route` to read it differently, which is what `revise` is for and what an `accept` has no way to do. This is guidance to whoever decides at the gate rather than a rule an executor applies: the gate record carries the outcome and not the reasoning for it (spec §7). What the record cannot hold the brief does — an override writes **Accepted class** and **Accepted rationale** into the Routing block (spec §5.3) — so the override itself is auditable downstream; what stays indistinguishable is the reasoning for choosing `accept` over `revise`, which is the choice this guidance is about. An override to R3 needs none of this and `accept` is right there: the security pass is mandatory at R3 whatever the reading says, and it holds that reading against the change when it runs.

## Notes

- **Run-state bootstrap:** the run-state file is created when the run starts, before this stage runs a step. It carries no class until `intake-approval` accepts one — `run.risk` and `risk_rationale` hold the human's decision, not the router's proposal, and the schema leaves both absent until there is a decision to record (spec §5.3, §10). That is what gives both gates here something to resume from, which `intake-approval` needs: it takes the `inbox` transport at R0–R2, and a gate whose decision another driver may clear cannot be the thing that creates the state it resumes from. `risk-route` still writes no run state, and now there is nothing it could have written.
- Neither step declares `on`: intake artifacts have no validation step, so steps and gates proceed in composition order (spec §9.1).
