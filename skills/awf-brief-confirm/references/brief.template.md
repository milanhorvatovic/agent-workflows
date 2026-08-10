# Brief: [one-line restatement of what is being asked]

> **Run:** [run id]
> **Workflow:** [feature | bugfix | plan]
> **Source:** [where the request arrived from — a ticket key, an issue link, a document reference, or "direct request"]
> **Focus:** [codebase areas the request points at, or "general"]

## Goal

[The outcome, not the activity: what is different, and for whom, once this run is done. One or two sentences.]

## Constraints

[What bounds the solution — compatibility that must hold, performance that must not regress, deadlines, dependencies the project will not take on, approaches already ruled out. Each marked stated, inferred, or directed, so the gate can strike an inference cheaply and can tell its own additions from the requester's: directed is a constraint the human added at a gate, which the request neither stated nor implied and which must not be recorded as either. "None" only when the request states no constraint, none was inferred, and no gate directed one.]

- [constraint] — [stated | inferred | directed]

## Acceptance criteria

[Conditions on the finished work, each specific enough that two readers would agree on whether it holds. plan-validate traces every one to a plan step; deliver-validate walks them one at a time against what shipped.]

- [ ] [criterion]

## Out of scope

[Only what a reasonable reader might otherwise assume is included, with the reason where it is not obvious. "None" when nothing needs excluding.]

- [boundary] — [why]

## Assumptions and clarification

[Assumptions taken where the request did not say, each naming the part of the request that left it open. Where a gate sent something back: the question asked and the content of the answer at clarifying-question, or what an intake-approval revise asked for — folded into the sections above, not left only here, since this section records what was asked while those sections are what the run is measured against. "None" when the request was restatable with none of them.]

## Routing

[Filled by risk-route; left as scaffolded until then.]

**Proposed class:** [R0 | R1 | R2 | R3 — or "withheld", where ambiguity above threshold routed back to the clarifying question instead]
**Rationale:** [one line naming the signals that decided it — transcribed verbatim into `run.risk_rationale` where the human accepts this class; where they override it, run state takes their reason from the gate's direction carrier instead and this line stays the proposal it always was; where the class is withheld, what could not be pinned down]
**Security surface:** [the value begins with yes or no, written as a bare word with no formatting around it, then what decided the reading either way — for yes, what triggers it, which also enables security review; for no, what was checked and found absent]
