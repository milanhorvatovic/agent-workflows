---
name: intake
description: Entry stage of every workflow — confirms the brief through at most one clarifying question, classifies risk with the spec §5.2 rubric, and collects the human's decision at the intake gate. Outputs a confirmed brief artifact and a risk class recorded in run state.
---

# Stage: intake

The entry stage of every workflow (spec §6.2). Three parts, in order: the clarifying-question gate, the risk router, the intake gate. Outputs: a confirmed `{run}/brief.md` and a risk class with a one-line rationale in run state.

## Steps

### brief-confirm (analyst)

Parse the request and restate it as a brief: goal, constraints, acceptance criteria, and what is explicitly out of scope. If the request's ambiguity is above threshold — the brief cannot be restated with confidence — stop at the `clarifying-question` gate and ask exactly one question, then fold the answer into the brief. One cheap question here beats a full revision loop later.

```yaml
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
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

- **clarifying-question** — conditional: fires only when ambiguity is above threshold, and sits before `risk-route`, so `accept` resumes at classification whichever step raised it. Either step can: `brief-confirm` when the brief cannot be restated with confidence, `risk-route` when the rubric's ambiguity signal is above threshold, which routes here instead of inflating the class (spec §5.2) and proposes no class until the answer lands. Blocking whenever it fires, in every risk class — a question is waiting for its answer. Outcome vocabulary: record `accept` when the answer confirms the (possibly amended) brief — the answer's content lands in the brief artifact, never in the gate record; record `revise` when the answer redirects the brief enough to need a re-draft, returning to `brief-confirm` per the spec §7 default; `reject` ends the run.
- **intake-approval** — after `risk-route`: the human sees the confirmed brief and the proposed class, and MAY override the class (spec §5.3). Transport per risk class ([overlays](../overlays.md)). Outcomes: `accept` proceeds to the next stage in composition order; `revise` returns to `brief-confirm`; `reject` ends the run. An override resting on a security surface whose **Security surface** field in the Routing section opens with `no` is a `revise` rather than an `accept` carrying a new class: that first word, not the presence of the field, is what the R2 security-review condition is evaluated against, so a class raised past it buys the process and skips the pass it was raised for. Accepting a higher class cannot correct the reading: the brief has to come back naming that surface for `risk-route` to read it differently, which is what `revise` is for and what an `accept` has no way to do.

## Notes

- **Run-state bootstrap:** the run-state file is first written when `risk-route` proposes a class, because `run.risk` is required. The clarifying-question exchange happens before run state exists and is not resumable — deliberately so; the exchange is one cheap question.
- Neither step declares `on`: intake artifacts have no validation step, so steps and gates proceed in composition order (spec §9.1).
