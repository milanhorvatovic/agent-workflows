# Conventional Commits Standard - {{PROJECT_NAME}}

> Reference: https://www.conventionalcommits.org

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

- **type**: required. Describes the category of the change.
- **scope**: optional. A noun describing the area of the codebase affected.
- **description**: required. A short summary of the change in imperative mood.

## Types

| Type       | When to Use |
|------------|-------------|
| `feat`     | A new feature visible to the end user or consumer of the API. |
| `fix`      | A bug fix. |
| `docs`     | Documentation-only changes (README, inline docs, API docs). |
| `style`    | Formatting, whitespace, semicolons — no logic change. |
| `refactor` | Code restructuring that neither fixes a bug nor adds a feature. |
| `test`     | Adding or updating tests. No production code change. |
| `chore`    | Maintenance tasks: dependency updates, tooling config, CI scripts. |
| `perf`     | A change that improves performance. |
| `ci`       | Changes to CI/CD configuration files and scripts. |
| `build`    | Changes to the build system or external dependencies. |

## Scope

Scopes are project-specific. Use short, lowercase nouns that match the module or area of the codebase.

Valid scopes for {{PROJECT_NAME}} include:

<!-- Update this list as the project evolves -->
- `core` — core business logic
- `api` — API layer
- `ui` — user interface
- `db` — database and migrations
- `auth` — authentication and authorization
- `config` — configuration and environment
- `deps` — dependency management

When the change crosses multiple scopes, either omit the scope or use the most significant one.

## Description Rules

- Use imperative mood: "add feature" not "added feature" or "adds feature."
- Do not capitalize the first letter.
- No period at the end.
- Keep it under 72 characters.
- Describe **what** the commit does, not **how**.

## Body

- Separate from the description by a blank line.
- Wrap at 72 characters per line.
- Explain **what** changed and **why**, not how.
- Use bullet points for multiple changes if needed.

## Footer

- Separate from the body by a blank line.
- Reference related issues: `Refs: #123` or `Closes: #456`.
- Note breaking changes (see below).
- Multiple footers are allowed, one per line.

## Breaking Changes

Indicate a breaking change in one of two ways:

1. **Exclamation mark** after the type/scope:
   ```
   feat(api)!: change authentication endpoint response format
   ```

2. **Footer**:
   ```
   BREAKING CHANGE: the /auth/login endpoint now returns a session object instead of a raw token.
   ```

Both may be used together. Every breaking change must describe the migration path.

## Examples

### Simple feature
```
feat(auth): add password reset via email
```

### Bug fix with body
```
fix(api): prevent duplicate order submissions

The order endpoint was not idempotent. Added a unique request ID
check to reject duplicate submissions within a 5-minute window.

Closes: #342
```

### Breaking change
```
feat(api)!: rename user endpoints to follow REST conventions

BREAKING CHANGE: GET /user/:id is now GET /users/:id.
POST /user is now POST /users.
Clients must update their base paths.

Refs: #501
```

### Chore
```
chore(deps): upgrade {{TECH_STACK}} dependencies to latest stable
```

### Documentation
```
docs: update API authentication guide with new token flow
```
