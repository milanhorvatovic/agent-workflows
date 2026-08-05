# Code Review Checklist - {{PROJECT_NAME}}

> Use this checklist when reviewing pull requests. Not every item applies to every PR — use judgment, but do not skip a category entirely without consideration.

## Correctness

- [ ] The code does what the PR description claims it does.
- [ ] Edge cases are handled (empty inputs, null/undefined values, boundary conditions).
- [ ] Error paths are tested and produce meaningful feedback (not silent failures).
- [ ] Off-by-one errors are absent in loops, slicing, and pagination logic.
- [ ] Concurrent access is handled where relevant (race conditions, deadlocks).
- [ ] Data types are correct — no implicit coercion or precision loss.

## Security

- [ ] User input is validated and sanitized at the boundary before processing.
- [ ] Authentication and authorization checks are present on all protected operations.
- [ ] Sensitive data (passwords, tokens, PII) is not logged, exposed in URLs, or returned in responses.
- [ ] SQL/NoSQL queries use parameterized statements — no string concatenation.
- [ ] Dependencies introduced are from reputable sources and do not have known critical vulnerabilities.
- [ ] Secrets and credentials are not hardcoded — they come from environment variables or a secrets manager.
- [ ] CORS, CSP, and other security headers are configured correctly if modified.

## Performance

- [ ] Algorithm complexity is appropriate for the expected data size.
- [ ] Database queries are efficient — no N+1 problems, unnecessary full-table scans, or missing indexes.
- [ ] Large data sets are paginated, streamed, or processed in batches — not loaded entirely into memory.
- [ ] Caching is used where beneficial and invalidated correctly.
- [ ] No unnecessary network calls or redundant computations inside loops.
- [ ] New dependencies do not significantly increase bundle size or startup time.

## Maintainability

- [ ] Code is readable without needing the PR description for context.
- [ ] Names (variables, functions, files) are descriptive and consistent with project conventions.
- [ ] Functions are focused — each does one thing. Long functions are broken into helpers.
- [ ] Duplication is minimized. Shared logic is extracted into reusable utilities.
- [ ] Magic numbers and strings are replaced with named constants.
- [ ] Complex logic has explanatory comments covering the "why."
- [ ] Dead code, commented-out code, and debug statements are removed.

## Testing

- [ ] New logic has corresponding unit tests.
- [ ] Edge cases identified in the Correctness section above are covered by tests.
- [ ] Tests are deterministic — no flaky tests introduced.
- [ ] Test names clearly describe the scenario and expected outcome.
- [ ] Mocks and stubs are used appropriately — integration points are tested separately.
- [ ] Coverage does not regress below the project threshold.

## Standards Compliance

- [ ] Code follows the project naming conventions (files, variables, functions, classes).
- [ ] Architectural patterns are respected — no layer violations or bypassed boundaries.
- [ ] Commit messages follow the project commit format.
- [ ] PR title and description follow the project PR template.
- [ ] Linter and formatter pass with no new warnings suppressed without justification.
- [ ] Documentation is updated if public APIs, configuration, or behavior changed.

## Final Assessment

- [ ] I would be comfortable maintaining this code six months from now.
- [ ] The change is appropriately sized — it does one thing and does it well.
- [ ] There are no unrelated changes bundled in.
