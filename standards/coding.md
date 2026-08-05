# Coding Standards - {{PROJECT_NAME}}

> Tech Stack: {{TECH_STACK}}

## Naming Conventions

### Files
- Use consistent casing across the project (kebab-case, camelCase, or PascalCase as dictated by {{TECH_STACK}} conventions).
- File names should reflect the primary export or purpose.
- Test files: append `.test` or `.spec` before the extension (e.g., `parser.test.ts`).
- Configuration files: use the tool's expected name (e.g., `tsconfig.json`, `.eslintrc`).

### Variables
- Use descriptive names that convey intent — prefer `remainingRetries` over `r` or `count`.
- Booleans: prefix with `is`, `has`, `should`, `can` (e.g., `isAuthenticated`, `hasPermission`).
- Avoid abbreviations unless universally understood (`id`, `url`, `http` are acceptable).

### Functions and Methods
- Use verb-first naming: `fetchUser`, `calculateTotal`, `validateInput`.
- Keep function names under 4 words where possible.
- Event handlers: prefix with `on` or `handle` (e.g., `onSubmit`, `handleClick`).

### Classes and Types
- Use PascalCase for classes, interfaces, type aliases, and enums.
- Interfaces should describe capability or contract, not implementation (e.g., `Serializable`, `UserRepository`).

### Constants
- Use UPPER_SNAKE_CASE for true compile-time or environment constants (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT_MS`).
- Configuration objects that are const but complex may use regular naming.

## Code Organization

### File Structure
- One primary concept per file. If a file exceeds ~300 lines, consider splitting.
- Group related files in directories by feature or domain, not by technical role.
- Keep entry points (index files, main modules) thin — they should compose and re-export, not implement.

### Imports
- Order imports: (1) standard library / runtime, (2) external dependencies, (3) internal modules.
- Separate each group with a blank line.
- Prefer named imports over wildcard imports.
- Avoid circular imports — they indicate an architecture problem.

### Module Boundaries
- Each module should have a clear public API. Internal details should not leak.
- Shared utilities belong in a dedicated `shared` or `common` module.
- Cross-module communication should happen through defined interfaces, not direct file access.

## Error Handling

### Patterns
- Fail fast: validate inputs at boundaries (API endpoints, function entry, user input).
- Use typed or domain-specific errors rather than generic error strings.
- Never swallow errors silently. At minimum, log them.
- Distinguish between recoverable errors (retry, fallback) and fatal errors (crash, alert).

### Error Types
- Define a base error class or type for the project.
- Include error codes or categories for programmatic handling.
- Wrap external errors with project-specific context before propagating.

### Logging
- Log at appropriate levels: `error` for failures, `warn` for degraded states, `info` for key events, `debug` for development.
- Include context in log messages: what operation failed, with what input, and what the impact is.
- Never log sensitive data (passwords, tokens, PII).

## Documentation

### Inline Comments
- Comment the "why", not the "what". Code should be readable on its own.
- Use `TODO:` for known incomplete work. Include a ticket reference when possible.
- Use `HACK:` or `WORKAROUND:` for intentional shortcuts with explanation.

### Function Documentation
- Public functions must have a doc comment describing: purpose, parameters, return value, and thrown errors.
- Private/internal functions: document if the logic is non-obvious.
- Keep doc comments up to date when function signatures change.

## Language-Specific Guidelines

<!-- Replace or extend the section below with rules specific to {{TECH_STACK}} -->

### {{TECH_STACK}} Conventions
- Follow the idiomatic style guide for {{TECH_STACK}}.
- Use the standard formatter and linter configuration for the ecosystem.
- Prefer language-native features over third-party utilities when the standard library suffices.
- Document any deviation from community conventions and the rationale.
