# Review Resolution: [subject]

> **Run:** [run id]
> **Sources:** [review-findings.md, review-validation.md — plus security-findings.md where present]
> **Trigger:** [the disagreement that fired the step — e.g. passing verdict over unresolved criticals, contested failure — or "mandatory at R3"]
> **Iteration:** [review loop iteration, 1-based]

## Summary

[1–3 sentences: what disagreed or what was synthesized, how many findings arrived across the sources, how many survived, and what review-fix must act on.]

## Resolved findings

[The single actionable list the loop consumes — every finding that survived, by severity, in fix order. Each keeps the id of its strongest source statement; merged duplicates record the ids they absorb. Every acceptance records the refutation attempt that failed — a finding survives because refutation failed, not because sources agree.]

- **[R-001] [title]** — [critical / major / minor / suggestion]
  - **Sources:** [ids merged into this finding and where each came from; severity conflicts noted with the grade that won and why]
  - **Refutation attempted:** [the strongest case against the finding, and why it failed]
  - **Resolution:** [what review-fix must do, concretely]

## Dismissed findings

[Findings that did not survive, each with rationale as rigorous as an acceptance: refuted with evidence, mistaken about the code, immaterial to the change. "None" when everything survived.]

- **[S-002] [title]** — [why it was dismissed]

## Conflicts

[Where sources disagreed — a contested finding, a disputed severity, a verdict at odds with the findings: each resolved on evidence with the losing side's reasoning preserved. A conflict the evidence cannot resolve is escalated here explicitly, never averaged away. "None" where sources aligned.]

## Devil's advocate

[Where the sources agreed — an uncontested verdict included — the strongest opposing case, argued before endorsing: what would have to be true for the consensus to be wrong, and why it is not the case here.]
