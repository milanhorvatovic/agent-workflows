---
name: awf-validate-tickets
description: Adversarially validates a ticket set against the work items it was built from — does every item have a ticket and every ticket an item, does each ticket stand on its own for someone picking it up cold, do any two describe the same work, does the dependency chain resolve without cycles, and are priority and size calibrated across the set rather than per ticket? — and renders exactly one verdict, PASS, PASS_WITH_CONDITIONS, or FAIL, in a structured validation report. Triggers after awf-create-tickets writes the ticket set, standalone and fresh-context, with no stage binding it. It identifies issues and asks questions, never fixes them — rewriting the tickets against these findings is awf-create-tickets again — and its verdict gates no loop — nothing downstream consumes it, so it reports to whoever invoked the run and the decision to file or revise stays theirs.
license: MIT
metadata:
  workflow:
    protocol: "0.3"
    step:
      role: validator
      inputs:
        - artifact: "{run}/tickets.md"
          required: true
        - artifact: "{run}/parsed-requirements.md"
          required: true
      output:
        artifact: "{run}/tickets-validation.md"
        template: references/validation-report.template.md
---

# Skill: awf-validate-tickets

Renders the verdict on a ticket set: is this work someone could actually pick up, in an order that holds, covering what the requirements asked for and nothing else?

Standalone: no stage declares this step, so no loop consumes the verdict. It reports to the human who invoked it, which raises rather than lowers the bar on saying plainly what is wrong — there is no next iteration that will catch what this pass excuses.

## Role

The step runs as the validator (spec §3.3), always with fresh context (spec §4): professional skepticism, omissions hunted as hard as errors, exactly one verdict. Identify and report — never rewrite a ticket, never add the missing one. A ticket the set is missing is a coverage finding, not an invitation to supply it.

## Inputs

- `{run}/tickets.md` (required) — the ticket set under validation, read in full before judging any part of it.
- `{run}/parsed-requirements.md` (required) — the source of truth for coverage. Its work items, their acceptance criteria, and their flags are what the ticket set is measured against; a ticket that quietly resolves a flagged ambiguity is deciding something the flag left open.
- The project's rendered ticket-format standard, where one exists — the bar the report's **Standards** checklist row is checked against. Without it that row asserts conformance to nothing; with it, a ticket missing a field the standard requires is a finding against the standard rather than against the reviewer's taste. An argued departure stays legitimate and is judged on its argument; only a silent one is a finding.

## Method

Check coverage in both directions, because the two failures are different and neither implies the other. Walk every work item and find the ticket that addresses it — an item with no ticket is a gap, reported against the core **Completeness** row. Then walk every ticket back to its source item — a ticket tracing to nothing is scope that entered here, reported against **Scope**. Do the walk item by item rather than by counting: equal totals prove nothing when one item was dropped and one ticket invented.

Test self-containment by reading each ticket as someone who has seen no other artifact. Is the title action-oriented, is the description complete without the requirements document, are the acceptance criteria specific and testable rather than restatements of the title, and is every dependency named rather than implied? An implicit dependency is the most expensive defect in a ticket set, because it surfaces only when someone is already blocked.

Hunt duplicates and overlaps. Tickets describing the same work, or overlapping enough that two people would collide implementing them, are a finding with a recommendation — merge, deduplicate, or keep separate with boundaries drawn explicitly. Say which, and why.

Trace the dependency chain: every referenced dependency exists, every direction is right — the depended-on ticket genuinely must land first — no cycle exists at any length, and the stated implementation order respects every dependency it declares. A cycle is critical: the set cannot be executed as written.

Assess priority and size as a calibration across the set, not ticket by ticket. Critical should genuinely block or affect production; low should be genuinely deferrable; tickets describing comparable work should carry comparable sizes. A simple UI change at `XL` beside a backend refactor at `S` is an inconsistency regardless of which of the two is wrong, and naming both is what makes the finding actionable.

Close on the set as a whole: is the sequence efficient, are there gaps that would leave an implementer blocked, is the total scope proportionate to the requirements, and are labels used consistently enough to be worth filtering on?

## Output

Write the report to `{run}/tickets-validation.md`, scaffolded from `references/validation-report.template.md` (spec §8.3 — a generated copy of the shared source; load it before writing, since it fixes the section order, the checklist, and the stable `F-…`/`Q-…` id scheme).

Append three rows to the core eight, for what a ticket set can fail that the shared rows do not reach: **Self-containment** — every ticket is actionable by someone who has read nothing else; **Duplication** — no two tickets describe the same work; **Calibration** — priority and size are consistent across the set. Coverage needs no row of its own: its two directions are exactly the core **Completeness** and **Scope** rows, and the dependency chain is the core **Dependencies** row.

Append one section, **Coverage**, above the findings: the item-by-item mapping of work items to the tickets that address them, with gaps and orphans marked in place. It is a table rather than a row because coverage is the one check whose result is not a boolean — the **Completeness** and **Scope** rows record *whether* it holds, and this is the evidence for how that was established. A reader disputing a coverage finding checks it here; a reader disputing the verdict starts here, since a gap this table makes visible is the cheapest finding in the report to confirm.

Render exactly one verdict in the spec §3.3 vocabulary — `PASS`, `PASS_WITH_CONDITIONS`, `FAIL` — and state the conditions exactly where the verdict carries them. Critical findings force `FAIL` on their own.
