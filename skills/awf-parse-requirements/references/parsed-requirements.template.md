# Parsed requirements: [source title]

> **Run:** [run id]
> **Source:** [pasted text | Jira EPIC-123 | Confluence page | Notion doc | Linear project — with the reference]
> **Items:** [N total]

## Summary

[2–4 sentences: what this body of requirements asks for and what most constrains decomposing it. Written last.]

**By type:** [N] feature · [N] bug · [N] chore · [N] spike

## Work items

### WI-001 — [one-line summary]

**Type:** feature | bug | chore | spike
**Size:** S | M | L | XL
**Group:** [theme or component label]
**Depends on:** [WI-NNN, WI-NNN — or "None"]

[Detailed description: what the item entails, the context it sits in, and why it is wanted. Self-contained — a reader does not go back to the source text to understand it.]

**Acceptance criteria**

- [ ] [Specific, testable condition]
- [ ] [Specific, testable condition]

[Repeat the block per item, ids sequential and stable — downstream tickets and the coverage check both address items by id.]

## Dependency map

| Item | Depends on | Why |
| --- | --- | --- |
| [WI-002] | [WI-001] | [what WI-001 introduces that WI-002 consumes] |

[No cycles. An item depending on nothing is omitted from this table rather than listed as empty.]

## Groupings

### [Theme or component label]

[WI-NNN, WI-NNN — the items that share this area, and one line on what makes it a group.]

## Flags

[Ambiguities, contradictions, and gaps. Omit the section only when there are genuinely none — an empty Flags section on a real body of requirements is itself worth a second look.]

### FL-001 — [what is unclear, contradictory, or missing]

**Source:** [quote or reference the specific part of the requirements]
**Problem:** [what cannot be determined from the text, or what two parts of it disagree about]
**Resolution:** [the clarifying question to ask, or the default assumption taken — state which]
**Affects:** [WI-NNN, WI-NNN]
