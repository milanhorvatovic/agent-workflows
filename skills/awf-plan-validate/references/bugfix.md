# Bugfix-plan validation — root-cause and regression-test checks

Additional checks for a bugfix plan. Loaded on top of the standard method. A bugfix plan cannot afford guesswork: an unvalidated cause hypothesis produces a fix that suppresses the symptom and ships the bug.

## Scope against the bug report

- The plan reproduces the reported behavior, or explains concretely why reproduction is impossible — "hard to reproduce" without a deterministic verification alternative is a finding.
- Expected behavior, actual behavior, and impact scope from the report are all addressed; related surfaces sharing the faulty code path are covered or explicitly declared out of scope with a reason.

## Root cause analysis

- The hypothesis identifies the actual failure point in the code path — named files and functions the validator checks exist and plausibly produce the reported behavior. A cause argued from the symptom's location rather than the failing path is a critical finding.
- Plausible alternative causes the plan ignores are findings; where evidence for the chosen hypothesis is weak, the plan must include steps that confirm it before the fix — or the uncertainty must be a blocking question.
- The fix targets the cause. A fix that would make the symptom disappear while the cause survives — a guard clause where the bad value is consumed rather than where it is produced — is the failure mode this check exists to catch.

## Regression test

- The plan's tests lead with a regression test that fails pre-fix and passes post-fix; its absence without an explicit, justified exception is a critical finding.
- The regression test pins the cause, not the symptom — it would still fail if the symptom were suppressed some other way.
- Edge cases and error paths adjacent to the change carry coverage; test file paths and structure match the project's conventions.

## Fix discipline

- Every step has concrete file paths and precise change descriptions; no step forces a design decision onto the implementer.
- The file scope declares only what the fix and its tests touch — refactoring folded into a bugfix is scope creep, flagged.
- Security and data-integrity implications of the touched path are addressed: input validation, auth implications, error handling that could leak details, transactional consistency.
- Rollback restores a consistent system.
