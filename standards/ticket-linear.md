# Linear Issue Standard - {{PROJECT_NAME}}

## Title Format

Titles should be concise, action-oriented, and scannable in a list view.

```
<Action verb> <what> <optional context>
```

Good:
- "Add webhook retry logic for failed deliveries"
- "Fix timezone handling in schedule display"
- "Refactor notification service to use event bus"

Bad:
- "Webhook stuff"
- "Bug"
- "Refactoring"

Keep titles under 80 characters. They appear truncated in board views.

## Description

Linear supports full **Markdown** in descriptions. Use it for structure and readability.

### Feature / Enhancement Template

```markdown
## Summary
Brief explanation of what this change accomplishes and why it matters.

## Background
- Link to relevant discussion, RFC, or design document.
- Explain the current state and what is lacking.

## Proposed Approach
High-level description of the implementation approach. Not a spec — just
enough for the implementer to understand the direction.

## Out of Scope
Explicitly list what this issue does NOT cover to prevent scope creep.
```

### Bug Template

```markdown
## Summary
One-sentence description of the bug.

## Current Behavior
What happens now (include error messages, screenshots, or logs).

## Expected Behavior
What should happen instead.

## Steps to Reproduce
1. Go to ...
2. Click on ...
3. Observe ...

## Environment
- App version:
- Browser/OS:
- Account type:
```

## Acceptance Criteria

Define clear, testable conditions for completion.

```markdown
## Acceptance Criteria
- [ ] Failed webhook deliveries are retried up to 3 times with exponential backoff.
- [ ] Each retry attempt is logged with timestamp and response status.
- [ ] After 3 failures, the webhook is marked as failed and an alert is sent.
- [ ] Retry behavior is covered by integration tests.
```

## Labels

Use labels to categorize and filter issues. Keep the label set small and consistent.

| Label         | Purpose |
|---------------|---------|
| `feature`     | New functionality. |
| `bug`         | Something is broken. |
| `improvement` | Enhancement to existing functionality. |
| `tech-debt`   | Refactoring, cleanup, tooling. |
| `security`    | Security-related work. |
| `design`      | Requires design input before implementation. |
| `blocked`     | Cannot proceed — document the reason in a comment. |

## Priority

Linear uses four priority levels. Apply them consistently.

| Priority   | When to Use |
|------------|-------------|
| **Urgent** | Production incident or critical blocker. Work starts immediately. |
| **High**   | Important for the current cycle. Should be picked up within 1-2 days. |
| **Medium** | Standard work. Scheduled in the current or next cycle. |
| **Low**    | Nice-to-have. Address when higher priority work is complete. |

## Project and Cycle Placement

- **Project**: assign every issue to the relevant Project (e.g., "Auth Overhaul", "Performance Sprint").
- **Cycle**: assign to the current or upcoming cycle during planning. Issues without a cycle are considered backlog.
- Issues should not sit in a cycle without an assignee. If unassigned, move them back to backlog.

## Status Workflow

Linear's default statuses. Transition issues forward — avoid moving backward except when blocked.

```
Backlog -> Todo -> In Progress -> In Review -> Done
                                     |
                                  Cancelled
```

- **Backlog**: triaged but not scheduled.
- **Todo**: scheduled for the current cycle, ready to start.
- **In Progress**: actively being worked on. Assign yourself before moving here.
- **In Review**: PR is open and awaiting review.
- **Done**: merged, deployed, and verified.
- **Cancelled**: no longer needed. Add a comment explaining why.

## Sub-issue Breakdown

Break an issue into sub-issues when:
- The estimate exceeds 2-3 days of work.
- Distinct parts can be reviewed or shipped independently.
- Multiple people will work on it.

Sub-issue titles should be self-contained — readable without the parent for context.

Parent: "Add webhook retry logic for failed deliveries"
Sub-issues:
- "Implement exponential backoff utility"
- "Add retry loop to webhook dispatcher"
- "Create failed webhook alert notification"
- "Add integration tests for webhook retry flow"
