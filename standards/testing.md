# Testing Standards - {{PROJECT_NAME}}

> Tech Stack: {{TECH_STACK}}

## Test Types

### Unit Tests
- **Scope**: a single function, method, or class in isolation.
- **When to use**: for all business logic, data transformations, utility functions, and domain models.
- **Speed**: must run in milliseconds. No I/O, no network, no database.
- **Proportion**: majority of the test suite (~70%).

### Integration Tests
- **Scope**: interaction between two or more components — e.g., service + repository, API endpoint + database.
- **When to use**: to verify that components work correctly together, especially at layer boundaries.
- **Speed**: seconds per test is acceptable; minutes is not.
- **Proportion**: moderate share of the suite (~20%).

### End-to-End Tests
- **Scope**: full user workflows through the running application.
- **When to use**: for critical user journeys — login, checkout, data submission. Keep the set small and focused.
- **Speed**: slowest tier. Run in CI but not on every commit if the suite grows large.
- **Proportion**: smallest share (~10%).

## Test Organization

### File Naming
- Test files mirror the source file: `user-service.ts` -> `user-service.test.ts`.
- Integration tests may use a `.integration.test` suffix or live in an `__integration__` directory.
- E2E tests live in a dedicated top-level `e2e/` or `tests/e2e/` directory.

### Co-location vs. Separate
- Unit tests: co-locate next to the source file or in a `__tests__` directory within the same module.
- Integration and E2E tests: separate directory at the project root or within a `tests/` folder.

## Naming Convention

Test names should read as sentences describing the expected behavior:

```
// Good
"returns empty array when no users match the filter"
"throws AuthError when token is expired"

// Bad
"test1"
"user filter works"
```

Use a consistent pattern: `[unit under test] [scenario] [expected result]`.

## Coverage Expectations

| Type         | Minimum Threshold |
|--------------|:-:|
| **Statements** | 80% |
| **Branches**   | 75% |
| **Functions**  | 80% |
| **Lines**      | 80% |

- New code must meet or exceed these thresholds. Coverage must not decrease with a PR.
- Coverage alone does not prove quality. Focus on testing behavior, not just hitting lines.
- Critical paths (auth, payments, data integrity) should target near-100% coverage.

## Mocking Strategy

### When to Mock
- External services (APIs, databases, message queues) in unit tests.
- Time, randomness, and system-dependent values.
- Dependencies that are slow, flaky, or have side effects.

### What NOT to Mock
- The unit under test itself.
- Simple value objects and data structures.
- Internal collaborators in integration tests — the point is to test their interaction.

### Guidelines
- Prefer fakes (in-memory implementations) over mocks when possible — they provide more realistic behavior.
- Limit mock assertions to what matters: "was this method called with the right arguments?" not "was it called exactly once in this order."
- Reset mocks between tests to prevent leakage.

## Test Data

### Fixtures
- Store shared test fixtures in a `fixtures/` or `__fixtures__/` directory.
- Fixtures should be minimal — only include the fields relevant to the test.

### Factories and Builders
- Use factory functions or builder patterns to create test objects with sensible defaults.
- Override only the fields relevant to each test case.
- Example: `createUser({ role: 'admin' })` fills in all other fields with defaults.

### Rules
- Never use production data in tests.
- Avoid random data unless testing randomness-dependent behavior — deterministic tests are easier to debug.
- Clean up test data after integration tests (use transactions or teardown hooks).

## CI Requirements

Before a pull request can be merged, the following must pass:

- [ ] All unit tests pass.
- [ ] All integration tests pass.
- [ ] Coverage thresholds are met (no regression).
- [ ] Linter and formatter checks pass.
- [ ] No test is skipped without a linked tracking issue explaining why.
- [ ] E2E tests pass on the designated CI stage (nightly or per-PR, depending on suite size).
