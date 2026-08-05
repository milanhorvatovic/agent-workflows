# Tickets: [source title]

> **Run:** [run id]
> **Source:** [{run}/parsed-requirements.md — N work items]
> **Format:** [the project's rendered ticket-format standard, named — or "default (no project standard declared)"]

## Summary

[2–4 sentences: what this ticket set delivers and what drives its ordering.]

**Total:** [N] tickets
**By type:** [N] feature · [N] bug · [N] chore · [N] spike
**By priority:** [N] critical · [N] high · [N] medium · [N] low

## Implementation order

| # | Ticket | Depends on | Why here |
| --- | --- | --- | --- |
| 1 | [TICKET-001 — title] | [none] | [unblocks TICKET-003 and TICKET-004] |
| 2 | [TICKET-002 — title] | [TICKET-001] | [consumes the API TICKET-001 introduces] |

[Ordering respects every dependency. Within a tier, what reduces risk or resolves uncertainty comes first.]

## Tickets

[In implementation order. Where the project declares a ticket-format standard, each ticket takes that standard's shape and the block below is not used — only these surrounding sections are. Where it does not, the block below is the format.]

## [TICKET-001] [Action-oriented title, starting with a verb]

**Type:** feature | bug | chore | spike
**Priority:** critical | high | medium | low
**Size:** S | M | L | XL
**Labels:** [label-1, label-2]
**Dependencies:** [TICKET-NNN, TICKET-NNN — or "None"]
**Source item:** [WI-NNN]

### Description

[What needs to be done and why, with the context and rationale carried in. Self-contained: a reader who has seen none of the other artifacts can start from this alone.]

### Acceptance criteria

- [ ] [Independently verifiable condition]
- [ ] [Independently verifiable condition]

### Notes

[Additional context, references, implementation hints, or an assumption carried over from a parsed-requirements flag — naming the flag. Optional; omit the section when empty.]
