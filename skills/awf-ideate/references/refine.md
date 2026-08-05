# Refining the recommendation

Load when the recommended approach must reach planning-ready detail before `plan-create` works from it: the brief's work is large enough that its integration surface is where the risk lives, the approach's mechanics are not obvious from the core idea alone, or a validation finding says the recommendation is too thin to plan from. Refinement expands the ideation artifact's Recommendation section — it produces no separate artifact, because the stage declares one output.

## What refinement adds

- **Components:** the modules, services, interfaces, or UI elements the approach requires, each named and placed — new alongside existing, with what each is responsible for.
- **Integration points:** where the approach meets what already exists — the interfaces, call sites, events, schemas, and configuration it touches. Name them as they are named in the codebase.
- **Data flow:** how data moves for the key use cases the approach enables, including what changes shape, what is persisted, and what crosses a boundary.
- **Codebase impact, specifically:** the existing modules, configurations, database schemas, APIs, and workflows that would have to change — the ideation-level "impact" line resolved to actual paths and modules.
- **Risk mitigation:** every risk the approach recorded, answered with mitigate (how), accept (why it is tolerable), or defer (until when, and what makes it safe to defer). A risk left unanswered is the gap this pass exists to close.
- **Open technical decisions:** choices the refinement surfaces but does not resolve — technology, boundary, or trade-off decisions. They join the artifact's open questions rather than being decided quietly here.

## Readiness

Close with an explicit assessment: **ready to plan**, or **not ready** with what must be resolved first. Ready means the approach is concrete enough that a planner can decompose it into steps without inventing structure, its risks have answers, and no blocking unknown remains. Not ready is a legitimate outcome — say what would change it, and leave the blocker in the artifact's open questions where the human at `plan-approval` will see it.

## Boundary

Refinement adds detail to the chosen approach; it does not become the plan. No step decomposition, no file-scope declaration, no test plan, no sequencing into phases — those are `plan-create`'s, and producing them here would put an unvalidated plan inside an artifact the planning stage is about to build from.
