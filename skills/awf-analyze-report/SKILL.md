---
name: awf-analyze-report
description: Distills an existing grounding artifact into a polished, prioritized codebase report for humans — executive summary, architecture and module map, tech stack and key patterns, dependency and testing health, technical debt ranked by impact, actionable recommendations, and a developer quick reference — optionally answering specific questions with evidence. Standalone (no stage binds it); triggers when a completed grounding needs a readable deliverable, such as onboarding material, an architecture review, or a codebase health check. It does not explore the codebase itself — producing the grounding first is awf-ground.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/grounding.md"
          required: true
      output:
        artifact: "{run}/report.md"
        template: references/report.template.md
---

# Skill: awf-analyze-report

Distills a completed grounding into a report for humans: what the codebase is, how it hangs together, what needs attention, and what to do about it — prioritized, evidence-backed, and readable on its own.

Standalone: no stage declares this step. Run it whenever a grounding exists and a human needs the deliverable — onboarding a developer, reviewing an architecture, health-checking a codebase.

## Role

The step runs as the analyst producing a final deliverable: precise, evidence-backed, well-organized. It synthesizes existing analysis; it does not re-analyze the codebase.

## Inputs

- `{run}/grounding.md` (required) — the raw analysis, read in full before writing anything; it is the single source of truth. Files it cites may be opened to verify or sharpen a specific finding, but no new exploration happens here: a gap in the grounding is reported as a gap, never filled ad hoc.
- Specific questions (optional) — the invoker may name questions the report must answer, such as readiness for a migration or the biggest onboarding risks.

No project standard is an input here. The report judges plenty — what a piece of debt costs, whether the coverage is thin, what the architecture is doing — and it judges against the evidence the grounding carries rather than against a bar of its own: `awf-ground` has already read the project's coding and architecture standards to tell what the project committed to from what its code merely exhibits, and recorded the disagreements as grounding. Reading them again here would make this a review of the codebase rather than a report on it, and a departure from a project's own standard is a finding this step inherits and relays, never one it makes.

## Method

Synthesize rather than copy: connect related findings, interpret what they mean for the project, and prioritize — the most important information leads every section. Every claim traces to the grounding and ultimately to cited code.

Open with an executive summary useful to someone who reads nothing else: what the codebase is — purpose, stack, scale — its architecture and organizational approach, its most important strengths beside its highest-priority concerns, and a forward-looking close on maintainability, scalability, or readiness.

Between that summary and the technical debt sit the sections describing the system, and each is a reading rather than a transcription — the grounding already holds the facts, so what this step adds is what they amount to. **Architecture Overview**: the pattern, how the codebase is organized, where component boundaries sit and how components communicate, a textual structural diagram where the grounding supports one, and whether the architecture is clean, evolving, or drifting from its stated intent — that last read off the drift the grounding is required to flag rather than compared afresh here, this step saying what those flags amount to for the architecture as a whole and reporting the gap where the grounding made no such comparison. **Tech Stack**: languages, frameworks, build tools, package managers, and runtime requirements grouped by category, with version constraints and the notable choices or gaps — an unpinned runtime is a fact about the stack. **Key Patterns**: the coding, design, and convention patterns a contributor must understand to work here, and how consistently they are applied, since a convention held in half the modules is a finding rather than a convention. **Module Map**: each internal module's responsibility and its dependencies, as a textual diagram or a structured list, with the shapes that cost something named — the core modules, the high-coupling areas, the circular or otherwise problematic ones. **Dependencies**: external dependencies grouped by purpose, the outdated, deprecated, unmaintained, and critical ones flagged, and the overall health stated rather than left for the reader to total. **Testing Approach**: the frameworks, how the tests are organized, which types are present, and what CI checks automatically, with relative coverage the part that takes a judgment — well-tested against bare, both sides named, since the contrast is the information and the bare areas are what a reader acts on.

Rank technical debt and the risks beside it by severity and consequence — what it is, why it matters, what leaving it costs. Group recommendations as immediate — low effort or high impact, worth doing now — short-term at moderate effort next cycle, and long-term where the effort is higher and the reason strategic, each referencing the findings that support it. Answer any invoker questions directly, with evidence, in their own section, pointing back to the report sections each answer rests on.

Close with the **Quick Reference**: key files, entry points, configuration, and the commands a developer runs on their first day, each row earning its place by being one they would otherwise have to go looking for. It is the section most likely to be read on its own and the costliest to get wrong — an entry point that no longer starts anything costs a reader more than an absent table.

## Output

Write the report to `{run}/report.md`, scaffolded from `references/report.template.md` (spec §8.3 — the executor scaffolds it by script; load the template before structuring the report, since it fixes the section order and the quick-reference tables; fill every placeholder, omitting only the sections it marks conditional).

Its **Scope** is the grounding's rather than the codebase's: general where the analysis was general, and naming the focus areas where the brief pointed at particular parts of the system, since a focused report that reads as a survey overstates what it covers.

The report is self-contained — fully understandable without the grounding — and actionable: readers know what to do after reading it.
