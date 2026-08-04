# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until `1.0.0`, minor versions may contain breaking changes to the protocol surface.

## [Unreleased]

### Added

- JSON Schemas (`protocol/schemas/`, draft 2020-12) for the four protocol structures — step/handoff, loop contract, trigger, run state — strict within each structure and tolerant of siblings per the `0.x` degradation rules; per-schema YAML fixtures in `protocol/schemas/examples/`: a commented minimal starter that validates and a deliberately-invalid counterpart that must fail.
- Protocol specification (`protocol/spec.md`), protocol version `0.1`: six roles with the role≠session rule, `inline`/`isolated` execution modes, four risk classes with classification rubric and reclassification, gate semantics with the instrumentation requirement, artifact and run conventions, orchestration metadata (step/handoff, loop contract, trigger) with degradation rules, run-state model, versioning policy.
- Repository scaffold: directory tree (`protocol/`, `roles/`, `skills/`, `workflows/`, `standards/`, `bindings/`, `driver/`, `setup/`), `AGENTS.md` skeleton with `CLAUDE.md` importing it, conformance CI stub.
