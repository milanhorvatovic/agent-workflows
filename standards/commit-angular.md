# Angular Commit Message Standard - {{PROJECT_NAME}}

> Reference: https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit

## Format

```
<type>(<scope>): <subject>
<BLANK LINE>
<body>
<BLANK LINE>
<footer>
```

Each line of the commit message must not exceed **100 characters** (header should stay under **72**).

## Types

| Type         | When to Use |
|--------------|-------------|
| `feat`       | A new feature. |
| `fix`        | A bug fix. |
| `docs`       | Documentation-only changes. |
| `style`      | Changes that do not affect the meaning of the code (whitespace, formatting). |
| `refactor`   | A code change that neither fixes a bug nor adds a feature. |
| `perf`       | A code change that improves performance. |
| `test`       | Adding missing tests or correcting existing tests. |
| `build`      | Changes to the build system or external dependencies. |
| `ci`         | Changes to CI configuration files and scripts. |
| `chore`      | Other changes that do not modify source or test files. |
| `revert`     | Reverts a previous commit. |

## Scope

The scope provides additional context about where the change occurred. It should be a lowercase noun.

Valid scopes for {{PROJECT_NAME}}:

<!-- Maintain this list as the project grows -->
- `core`
- `api`
- `ui`
- `auth`
- `db`
- `config`
- `testing`
- `deps`

Omit scope if the change is truly global or does not fit a single area.

## Subject Rules

The subject is a succinct description of the change.

- Use **imperative, present tense**: "change" not "changed" or "changes."
- **Do not capitalize** the first letter.
- **No period** (`.`) at the end.
- Describe what applying the commit will do, not what you did.

Good: `fix(auth): handle expired refresh token gracefully`
Bad: `fix(auth): Fixed the expired refresh token bug.`

## Body

- Use imperative, present tense (same as subject).
- Explain **what** the change is and **why** it was made.
- Wrap lines at **72 characters**.
- Separate from the subject with a blank line.
- May include bullet points prefixed with `-` or `*`.

Example:
```
The previous implementation silently dropped expired refresh tokens,
causing users to be logged out without feedback. This change:

- detects expired refresh tokens before the API call
- redirects users to the login page with a clear message
- logs the event for monitoring purposes
```

## Footer

### Breaking Changes
All breaking changes must be mentioned in the footer with the description of the change, justification, and migration notes.

```
BREAKING CHANGE: the `authenticate()` method now returns a Promise
instead of a synchronous result.

Before:
  const user = authenticate(token);

After:
  const user = await authenticate(token);
```

### Issue References
Reference issues that this commit addresses:

```
Closes #234
Refs #456, #789
```

Use `Closes` for issues fully resolved by this commit and `Refs` for related issues.

## Revert Commits

When reverting a commit, the message should begin with `revert:` followed by the header of the reverted commit.

```
revert: feat(auth): add biometric login support

This reverts commit abc1234.

Reason: biometric API is not stable on the target platform.
```

## Examples

### Feature with body
```
feat(ui): add dark mode toggle to settings page

Users can now switch between light and dark themes from the
settings page. The preference is persisted in local storage
and applied on subsequent visits.

Closes #178
```

### Fix
```
fix(api): return 404 instead of 500 for missing resources

The generic error handler was catching NotFoundError and
re-throwing it as an internal server error.
```

### Refactor
```
refactor(core): extract validation logic into dedicated module

Validation was duplicated across three services. Consolidating
it reduces maintenance burden and ensures consistent rules.
```

### Build
```
build(deps): update {{TECH_STACK}} toolchain to latest release
```
