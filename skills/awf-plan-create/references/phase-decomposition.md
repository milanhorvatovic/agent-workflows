# Phase decomposition — authoring the phase list

How a phase-1 plan cuts multi-phase work into phases. Loaded when the brief's work exceeds one deliverable increment; a single-phase run skips this entirely. The phase list this produces goes in the plan's Phase list section, provisional until `plan-approval` fixes it for the run — later phases plan against it, and changing it mid-run is a cross-phase escalation (`awf-plan-revise`), never a silent edit.

## Cutting phases

- Identify the major workstreams the brief touches — backend, frontend, data, infrastructure, testing, documentation — and group related concerns before cutting anything.
- Each phase is an independently deliverable, testable increment: it makes the system meaningfully better even if every later phase is delayed or cancelled.
- Prefer smaller phases that produce verifiable results over large phases that defer all validation to the end.
- The riskiest or most load-bearing work goes early — a foundation defect discovered in the last phase invalidates everything built on it.

## Boundaries

- For every phase, state explicitly what is in scope and what is deferred to which later phase. Ambiguous boundaries between phases are the most common planning failure — be precise.
- No phase's scope may depend on how another phase chooses to implement its own — boundaries are contracts, not forecasts.

## Sequencing

- State which phases must complete before which others, and why each dependency exists; note where independent phases could run in any order.
- A textual dependency diagram earns its place when the shape is not a straight line:

  ```text
  Phase 1 → Phase 2 → Phase 4
  Phase 1 → Phase 3 → Phase 4
  ```

- No circular dependencies — a cycle means the boundary between those phases is wrong; recut.

## Per-phase entries

Each phase in the list carries: name (descriptive, not "part 2"), scope, out of scope, key deliverables, dependencies on other phases, and relative complexity. Acceptance criteria live in each phase's own plan; the list entry only fixes the boundary.

## Cross-cutting concerns

Concerns spanning phases are placed once, deliberately — not rediscovered per phase: the testing strategy across phases, migration of existing data or systems, rollback of each increment, and performance and security requirements that constrain every phase's approach. Name in which phase each concern's work lands.
