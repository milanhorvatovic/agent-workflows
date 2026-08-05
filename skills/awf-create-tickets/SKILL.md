---
name: awf-create-tickets
description: Turns parsed work items into self-contained tickets in the project's tracker format — each with an action-oriented title, a description that stands on its own, testable acceptance criteria as a checklist, priority, size, explicit dependencies, and labels — ordered by the sequence they should actually be implemented in, into the run's tickets artifact. Triggers once awf-parse-requirements has produced its work items and they need to become tickets a team can pick up; standalone, with no stage binding it. The ticket shape comes from the project's rendered ticket-format standard where one exists — Jira, Linear, and GitHub Issues ship as built-ins and any other tracker is one project-local standard file — and from references/ticket.template.md where none does. It writes tickets and never files them — pushing them into the tracker through its API stays the consumer's own channel, and judging the result against the requirements is awf-validate-tickets.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/parsed-requirements.md"
          required: true
      output:
        artifact: "{run}/tickets.md"
        template: references/ticket.template.md
---

# Skill: awf-create-tickets

Renders decomposed work as tickets someone can pick up cold: what to do, why it matters, what done looks like, and what it waits on — in the format the project's tracker actually uses.

Standalone: no stage declares this step. Run it whenever parsed work items need to become tracked, orderable units of work.

## Role

The step runs as the planner (spec §3.2): decompose into ordered, verifiable units with explicit dependencies and acceptance criteria. Every ticket traces to a parsed work item — inventing a ticket with no item behind it is scope creep that `awf-validate-tickets` will find as an orphan, and dropping an item is the coverage gap it will find as a hole.

## Inputs

- `{run}/parsed-requirements.md` (required) — the work items with their types, descriptions, acceptance criteria, sizes, dependencies, and groupings. Read all of it, including the flags, before writing any ticket: a work item carrying an unresolved ambiguity becomes a ticket that says so, not a ticket that quietly picks one reading.
- The project's rendered ticket-format standard, where one exists — it fixes the fields, their names, and their order, over any shape suggested here. This is the one input that decides what a ticket looks like, which is why the semantics below stay tracker-independent: what a ticket must *say* is invariant, how it is laid out is the project's to declare.

## Method

Write each ticket to be independently actionable. Someone picking up one ticket, having read nothing else, should know what to do, why it matters, what done looks like, and what they are waiting on. That standard is what makes the description self-contained rather than a pointer to the requirements document, and it is what turns implicit assumptions into stated ones.

Title with a verb and a concrete object — "Add user authentication endpoint", "Fix pagination offset error" — so a list of titles reads as a list of work. Carry the type and size across from the work item, adjusting size only when the ticket's scope genuinely differs from the item's, and say what changed it.

Assign priority against consequence, not enthusiasm: `critical` blocks other work or affects production, `high` carries significant impact on the goals, `medium` is standard planned work, `low` is genuinely deferrable. A ticket set where everything is critical has ranked nothing.

Express acceptance criteria as a checklist of independently verifiable conditions, and dependencies as explicit references to the tickets that must land first — never as prose inside the description, where an ordering constraint is invisible to anyone scanning the set. Label for the component area, feature, or technical domain, consistently across the whole set: labels that differ ticket to ticket are noise the validator reports.

Order the set by the sequence it should be implemented in. Dependencies bind first; within a dependency tier, prefer what reduces risk or resolves uncertainty earlier, since an early spike can change the shape of everything downstream of it.

## Output

Write all tickets to `{run}/tickets.md`, scaffolded from `references/ticket.template.md` (spec §8.3 — the executor scaffolds it by script). The template carries the artifact's own sections — the summary, the ordered set, the dependency view — and a default per-ticket block used only when the project declares no ticket-format standard; where one exists, its shape replaces the default block and the surrounding sections stay.

Ticket identifiers are consistent and stable across the artifact, so dependency references resolve unambiguously and the validator's coverage walk can address any ticket by id.

Filing these into a tracker is out of scope by design. The artifact is the deliverable, and any API push into Jira, Linear, or GitHub Issues is the consuming project's own channel, run under its own credentials and its own approval — a framework that files tickets on a team's behalf would be making a commitment no one approved.
