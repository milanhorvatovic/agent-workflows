# Phase-list validation — sequencing and coverage checks

Additional checks for a plan whose Phase list section authors the run's phase list (a phase-1 plan of multi-phase work). Loaded on top of the standard method, which still applies to the phase-1 steps themselves. The phase list is fixed for the run once this plan is approved, not merely once it passes here — `plan-approval` follows this verdict, and direction at that gate can still move the list. An error that survives both surfaces phases later, as cross-phase escalation, which is what makes this the cheapest place to catch one.

## Requirements coverage across phases

- Walk the brief's requirements against the whole phase list, not just phase 1: every requirement traces to a phase, and the phases jointly cover the brief with nothing parked in an implicit "later".
- Coverage gaps hide preferentially in non-functional requirements — security, performance, observability, migration — and in infrastructure work no feature phase claims.
- Work in the list that traces to no requirement is scope creep at the phase level; flag it unless explicitly justified.

## Phase boundaries

- Each phase's scope and out-of-scope statements are precise enough that no work item could plausibly belong to two phases — boundary ambiguity is where multi-phase plans fail.
- Each phase is an independently deliverable, testable increment; a phase whose value only materializes if every later phase completes is a mis-cut, not an increment.

## Sequencing

- The declared dependencies are real: what each phase consumes from its predecessors actually exists by then, and no later phase silently depends on something never produced.
- No circular dependencies; no unstated ones — check what each phase's work actually requires, not just what the diagram claims.
- Riskiest work scheduled early is the expectation; a foundation-risk phase deferred to the end is a finding.

## Cross-cutting concerns

- Testing strategy, migrations, rollback, performance, and security each have a declared home — the phase where that work lands — rather than appearing in every phase's margins or in none.
- Concerns the decomposition placed once are checked against the phase boundaries: the phase that owns a concern has it in scope.
