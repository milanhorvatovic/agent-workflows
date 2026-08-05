# Codebase Report: [project name]

> **Date:** [ISO date]
> **Based on:** [{run}/grounding.md]
> **Scope:** [general analysis, or the focus areas the grounding covers]

## Executive Summary

[2–3 paragraphs that stand alone: what this codebase is (purpose, stack, scale), its architecture and organizational approach, the most important strengths and highest-priority concerns, and a forward-looking close on maintainability, scalability, or readiness.]

## Architecture Overview

[The architecture pattern, how the codebase is organized, where component boundaries sit, and how components communicate. Include a textual structural diagram where the grounding supports one. Note whether the architecture is clean, evolving, or drifting from its stated intent.]

## Tech Stack

[Languages, frameworks, build tools, package managers, runtime requirements — grouped by category, with version constraints and notable choices or gaps.]

## Key Patterns

[The coding patterns, conventions, and design patterns a contributor must understand to work effectively here, and how consistently they are applied.]

## Module Map

[Internal modules, their responsibilities, and their dependencies. Highlight core modules, high-coupling areas, and circular or problematic dependency shapes. Textual diagram or structured list.]

## Dependencies

[External dependencies grouped by purpose. Flag outdated, deprecated, unmaintained, or critical ones; state the overall dependency health.]

## Testing Approach

[Frameworks, organization, test types present, relative coverage — well-tested versus bare areas — and what CI checks automatically.]

## Technical Debt & Risks

[Debt and concerns ranked by severity or impact. For each: what it is, why it matters, and the consequence of leaving it unaddressed. Actionable — readers understand what to fix first.]

## Recommendations

[Prioritized and grouped — **Immediate** (now: low effort or high impact), **Short-term** (next cycle: moderate effort), **Long-term** (strategic: higher effort). Each recommendation references the findings that support it.]

## Answers

[Conditional — only when the invoker asked specific questions. Per question:]

### Q: [the question, restated]

[Direct answer with supporting evidence; reference the relevant report sections.]

## Quick Reference

### Key Files

| File | Purpose |
|------|---------|
| [path] | [what it does and why it matters] |

### Entry Points

| Entry point | Type | Description |
|-------------|------|-------------|
| [path] | [API / CLI / worker / …] | [what it starts] |

### Configuration

| File | What it configures |
|------|--------------------|
| [path] | [description] |

### Useful Commands

| Command | Purpose |
|---------|---------|
| [command] | [what it does] |
