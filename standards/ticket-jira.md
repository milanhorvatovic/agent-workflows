# JIRA Ticket Standard - {{PROJECT_NAME}}

## Title Format

Titles must be **action-oriented** and describe the desired outcome, not the problem.

```
<Action verb> <what> <context>
```

Good:
- "Implement password reset via email"
- "Add pagination to user list endpoint"
- "Fix order total calculation for discounted items"

Bad:
- "Password reset"
- "Bug in orders"
- "User list is slow"

## Description

Use the user story format for features and enhancements:

```
As a [type of user],
I want [action or capability],
So that [benefit or outcome].
```

Follow the user story with a **Context** section for additional background:

```
### Context
- This was requested by the support team after repeated customer complaints.
- The current flow requires users to contact support to reset their password.
- See design mockup: [link]
```

For bugs, use this format instead:

```
### Current Behavior
Describe what currently happens.

### Expected Behavior
Describe what should happen instead.

### Steps to Reproduce
1. Step one.
2. Step two.
3. Observe the incorrect behavior.

### Environment
- Version: x.y.z
- Browser/OS: ...
- Relevant config: ...
```

## Acceptance Criteria

Every ticket must have explicit acceptance criteria. Use **Given/When/Then** format or a **checklist**.

### Given/When/Then
```
Given the user is on the login page,
When they click "Forgot Password" and enter their email,
Then they receive a password reset email within 2 minutes.

Given the user clicks the reset link,
When they enter a new password meeting complexity requirements,
Then their password is updated and they are redirected to login.
```

### Checklist Format
```
- [ ] Reset email is sent within 2 minutes of request.
- [ ] Reset link expires after 24 hours.
- [ ] Password complexity rules are enforced on the new password.
- [ ] User receives confirmation email after successful reset.
- [ ] Rate limiting: max 3 reset requests per hour per email.
```

## Story Points / Size

Use the Fibonacci scale: **1, 2, 3, 5, 8, 13**.

| Points | Guideline |
|:------:|-----------|
| 1      | Trivial change. Config update, copy change, one-line fix. |
| 2      | Small, well-understood change. A few files, minimal risk. |
| 3      | Moderate change. Requires some design thought, touches multiple areas. |
| 5      | Significant feature. Multiple components, requires testing strategy. |
| 8      | Large feature. May span multiple days. Consider splitting. |
| 13     | Epic-sized. **Must** be broken into smaller tickets before starting. |

## Labels

Apply relevant labels for filtering and reporting:

| Label        | Usage |
|--------------|-------|
| `frontend`   | Change is in the UI layer. |
| `backend`    | Change is in the API or service layer. |
| `database`   | Involves schema changes or migrations. |
| `tech-debt`  | Refactoring or cleanup work. |
| `security`   | Security-related change or fix. |
| `blocked`    | Ticket cannot proceed until a dependency is resolved. |

## Priority Guidelines

| Priority  | Definition |
|-----------|------------|
| Blocker   | Production is down or critical functionality is broken. Drop everything. |
| Critical  | Major feature broken, significant user impact. Fix within 24 hours. |
| Major     | Important work, but not urgent. Schedule in the current or next sprint. |
| Minor     | Low impact improvement. Schedule when bandwidth allows. |
| Trivial   | Nice-to-have. Address opportunistically. |

## Epic Linking

- Every ticket should belong to an Epic (or be explicitly marked as standalone).
- Epic names follow the format: `[Module] Feature Name` (e.g., `[Auth] Password Management`).
- Tickets within an Epic should be ordered by dependency and priority.

## Sub-task Breakdown

Break tickets into sub-tasks when:
- The ticket is estimated at 5+ points.
- Multiple developers will work on parts of it.
- It spans distinct technical areas (e.g., API + UI + migration).

Sub-task title format:
```
[Parent ticket key] <specific action>
```

Example:
- `[PROJ-100] Create database migration for password_resets table`
- `[PROJ-100] Implement reset token generation service`
- `[PROJ-100] Build password reset UI form`
- `[PROJ-100] Add email template for reset notification`
