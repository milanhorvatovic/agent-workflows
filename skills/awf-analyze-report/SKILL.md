---
name: awf-analyze-report
description: Distills an existing grounding artifact into a polished, prioritized codebase report for humans — executive summary, architecture and module map, dependency and testing health, technical debt ranked by impact, actionable recommendations, and a developer quick reference — optionally answering specific questions with evidence. Standalone (no stage binds it); triggers when a completed grounding needs a readable deliverable, such as onboarding material, an architecture review, or a codebase health check. It does not explore the codebase itself — producing the grounding first is awf-ground.
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

## Method

Synthesize rather than copy: connect related findings, interpret what they mean for the project, and prioritize — the most important information leads every section. Every claim traces to the grounding and ultimately to cited code.

Open with an executive summary useful to someone who reads nothing else: what the codebase is, its defining characteristics, the highest-priority findings, and a forward-looking close on maintainability or readiness.

Rank technical debt by severity and consequence — what it is, why it matters, what leaving it costs. Group recommendations as immediate, short-term, and long-term, each referencing the findings that support it. Answer any invoker questions directly, with evidence, in their own section.

## Output

Write the report to `{run}/report.md`, scaffolded from `references/report.template.md` (spec §8.3 — the executor scaffolds it by script; load the template before structuring the report, since it fixes the section order and the quick-reference tables; fill every placeholder, omitting only the sections it marks conditional).

The report is self-contained — fully understandable without the grounding — and actionable: readers know what to do after reading it.
