# Ideation: [subject]

> **Run:** [run id]
> **Brief:** [{run}/brief.md — one-line restatement of the goal]
> **Grounding:** [{run}/grounding.md, or "not available — impact claims verified against the code directly"]
> **Approaches:** [count considered, count carried as candidates]

## Problem

[The problem in the planner's own words, with the brief's constraints and acceptance criteria carried here, plus any constraint from the project's architecture standard that every approach must respect. This section is what makes the artifact stand alone: revision works from it, and the reader at plan-approval sees what the approaches answer.]

## Approaches

### Approach A: [name]

- **Core idea:** [what this approach is and how it fundamentally works, in 2–3 sentences]
- **How it works:** [the mechanics: where the work lives, what happens when, what the system does differently]
- **Advantages:** [what makes it attractive — each tied to something the brief asks for]
- **Risks and drawbacks:** [what could go wrong, what it trades away, what it costs after it ships — migration, operational burden, lock-in. "None" is not an answer.]
- **Codebase impact:** [named modules, components, and interfaces created or changed]
- **Complexity:** [low | medium | high — relative to this project, never absolute time]
- **Key decisions it forces:** [choices that would have to be made if this path is taken]

[Continue for all candidate approaches — three to five, each differing in shape rather than in parameters.]

## Comparison

[The candidates side by side on the axes that matter for this brief. The table is a summary of the sections above, never a substitute for them.]

| Approach | Complexity | Main advantage | Main risk | Fit with the codebase |
| --- | --- | --- | --- | --- |
| A: [name] | [low \| medium \| high] | [one line] | [one line] | [one line] |

## Discarded approaches

[Considered and ruled out, with the reason — a criterion it cannot satisfy, a constraint it violates, a cost the brief will not carry. Evidence of the space explored, and what stops a revision re-proposing a ruled-out option. "None" where every approach considered is carried above.]

- **[name]** — [why it was ruled out]

## Recommendation

[Exactly one approach, or one explicit combination named as such. The reasoning traces to the brief's constraints and acceptance criteria, not to preference, and follows from the advantages and risks recorded above rather than contradicting them.]

**Recommended:** [approach]

**Why:** [the reasoning]

**What would overturn it:** [the condition under which the runner-up wins — a constraint that changes, an assumption that proves false, a risk that materializes]

[Where the recommendation was refined for planning readiness — components, integration points, data flow, risk mitigation, readiness assessment — those sections follow here, per the refine reference.]

## Open questions

[Ambiguities the exploration could not resolve, each specific and answerable, with its alternatives. These are what reach the human at plan-approval. "None" when nothing is open.]

## Revision log

[Empty at creation — awf-ideate-revise appends one row per finding or question it decided, accept, reject, or defer, with what changed or why nothing did.]

| Iteration | Finding or question | Decision | What changed |
| --- | --- | --- | --- |
