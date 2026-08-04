# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until `1.0.0`, minor versions may contain breaking changes to the protocol surface.

## [Unreleased]

### Added

- Workflow tier (`workflows/`): six stage files — `intake`, `ideation`, `planning`, `implementation`, `review`, `delivery` — each owning its steps, loop contracts, and gates as schema-valid `metadata.workflow` blocks; three workflows composing them by reference (`feature`, `bugfix`, `plan`); risk-class overlays (`overlays.md`) encoding once what R0–R3 skip, batch, or substitute, including skip-resolution rules for edges and loop exit criteria. The new `intake` stage carries the clarifying-question gate, the risk router, and the intake gate, and documents the run-state bootstrap boundary and the clarifying-question outcome vocabulary.
- `AGENTS.md` index lines for workflows and stages, and the routing guidance (workflow by intent, risk by the intake rubric, depth by overlay).
- Role definitions (`roles/`) for the six protocol roles — `analyst`, `planner`, `implementer`, `reviewer`, `validator`, `arbiter` — each a compact identity/objectives/guidelines/constraints/output contract; validator verdicts use the spec's `PASS` / `PASS_WITH_CONDITIONS` / `FAIL` vocabulary, and the `arbiter` institutionalizes disagreement (refutation before acceptance, devil's-advocate pass on unanimity). Role files carry no session or isolation language, per the role≠session rule.
- JSON Schemas (`protocol/schemas/`, draft 2020-12) for the four protocol structures — step/handoff, loop contract, trigger, run state — strict within each structure and tolerant of siblings per the `0.x` degradation rules; per-schema YAML fixtures in `protocol/schemas/examples/`: a commented minimal starter that validates and a deliberately-invalid counterpart that must fail.
- Protocol specification (`protocol/spec.md`), protocol version `0.1`: six roles with the role≠session rule, `inline`/`isolated` execution modes, four risk classes with classification rubric and reclassification, gate semantics with the instrumentation requirement, artifact and run conventions, orchestration metadata (step/handoff, loop contract, trigger) with degradation rules, run-state model, versioning policy.
- Repository scaffold: directory tree (`protocol/`, `roles/`, `skills/`, `workflows/`, `standards/`, `bindings/`, `driver/`, `setup/`), `AGENTS.md` skeleton with `CLAUDE.md` importing it, conformance CI stub.

### Changed

- Spec sections 9.1/9.2 clarified: a loop contract's exit criteria are a verdict consumer — a step whose validation verdict is consumed by a loop MAY omit `on`, and the executor's stop-and-escalate rule applies only to verdicts with neither an edge nor a consuming loop. Section 9.1 additionally admits a stage id as an edge target, resolving to that stage's first step past risk-class skips (the step schema's target description matches), and section 9.2 defines the `{machine-checks}` placeholder for the project-bound machine-check command.
