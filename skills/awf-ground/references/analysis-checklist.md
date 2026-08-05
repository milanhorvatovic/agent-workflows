# Analysis checklist — the ten grounding areas

What a grounding establishes per area. Work through the areas the brief makes relevant, at the depth it warrants; skip an area only when the brief makes it irrelevant, and record why in the artifact. Every finding cites its evidence — files, directories, functions, line numbers. Read and verify; never speculate.

## 1. Structure and organization

- Top-level directories and key root files: configuration, entry points, manifests.
- The organizational pattern: by feature, by layer, by domain, or a hybrid — and how consistently it is applied.
- Standard directories present or missing (source, tests, docs, config, scripts); non-standard or surprising structural choices.

## 2. Tech stack

- Primary language(s) and their relative usage.
- Frameworks and libraries in use — from manifests, build files, and import statements, not assumptions.
- Build tools, task runners, bundlers, package manager(s); language or runtime version constraints where declared.

## 3. Architecture

- The overall pattern: monolith, modular monolith, microservices, serverless, plugin-based, other.
- Where boundaries are drawn (directories, packages, modules, services) and how components communicate (calls, events, HTTP, queues, shared state).
- Stated architectural intent (ADRs, docs) versus what the code actually does — flag drift explicitly.

## 4. Entry points

- Main entry files, route and endpoint declarations, CLI entry points, scheduled jobs, background workers.
- The boot sequence: initialization order, configuration loading, dependency injection or service registration.
- Multiple entry points (API server vs worker vs CLI) and what each starts.

## 5. Internal dependencies

- How internal modules depend on each other; high fan-in modules (many dependents) and high fan-out modules (many dependencies).
- Circular dependencies and tight coupling; whether dependencies flow in a clean direction or tangle.
- A textual diagram or structured list of the dependency shape where it helps downstream planning.

## 6. External dependencies

- Key external dependencies grouped by purpose: framework, data, networking, testing, utilities, tooling.
- Outdated, deprecated, unmaintained, or security-flagged packages; dependencies oversized for their use.

## 7. Conventions and patterns

- Naming conventions per context; file naming; formatter and linter configuration and its rules.
- Recurring patterns: error handling, state management, side-effect structure, design patterns in use.
- Consistency: applied uniformly, or do different areas betray different authors or eras?

## 8. Tests

- Frameworks, test organization (co-located vs separate), and the types present: unit, integration, end-to-end, snapshot, contract.
- Relative coverage: which areas are well-tested, which are bare; the utilities, fixtures, and factories the suite leans on.
- What CI runs and what it actually checks.

## 9. Technical debt and concerns

- TODO/FIXME/HACK/XXX comment themes; oversized files and functions; dead or commented-out code.
- Hardcoded values and configuration that should be externalized; missing error handling, bare catches, swallowed exceptions.
- Security concerns: hardcoded secrets, exposed credentials, unsafe patterns.

## 10. Focus-area deep-dives

- For each focus area the brief names: read the specific files in full, trace the specific flows, and report at file and function granularity — deeper than the general pass.
- Omit entirely when the brief names no focus areas.
