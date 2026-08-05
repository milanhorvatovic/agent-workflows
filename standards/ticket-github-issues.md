# GitHub Issues Standard - {{PROJECT_NAME}}

## Title Format

Titles should be action-oriented, specific, and easy to scan in a list.

```
<Action verb> <what> <optional context>
```

Good:
- "Add rate limiting to public API endpoints"
- "Fix CSV export truncating Unicode characters"
- "Update deployment docs for Kubernetes migration"

Bad:
- "Rate limiting"
- "Export bug"
- "Docs"

Keep titles under 80 characters.

## Description Body

Use Markdown for structure. Every issue should include enough context for someone unfamiliar with the problem to understand and act on it.

### Feature / Enhancement Template

```markdown
## Summary
Brief explanation of the desired feature and why it is needed.

## Motivation
- Who benefits from this change?
- What problem does it solve or what opportunity does it create?
- Link to related discussion or user feedback if available.

## Proposed Solution
High-level description of the implementation approach.

## Alternatives Considered
Briefly note any alternatives that were evaluated and why they were not chosen.

## Additional Context
Screenshots, mockups, links to external references.
```

### Bug Report Template

```markdown
## Summary
One-sentence description of the bug.

## Current Behavior
What happens now. Include error messages, logs, or screenshots.

## Expected Behavior
What should happen instead.

## Steps to Reproduce
1. Go to ...
2. Perform ...
3. Observe ...

## Environment
- {{PROJECT_NAME}} version:
- OS / Browser:
- Relevant configuration:
```

## Acceptance Criteria

Define what "done" means for this issue. Use a task list.

```markdown
## Acceptance Criteria
- [ ] Public API endpoints enforce rate limits (100 requests/minute per API key).
- [ ] Rate limit headers are included in responses (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset).
- [ ] Exceeding the limit returns HTTP 429 with a clear error message.
- [ ] Rate limiting is covered by integration tests.
- [ ] Documentation is updated with rate limit details.
```

## Labels

Apply labels consistently. Keep the label taxonomy manageable.

### Type Labels
| Label          | Color   | Purpose |
|----------------|---------|---------|
| `bug`          | #d73a4a | Something is not working correctly. |
| `enhancement`  | #a2eeef | New feature or improvement to existing functionality. |
| `documentation`| #0075ca | Documentation additions or updates. |
| `refactor`     | #e4e669 | Code restructuring with no behavior change. |
| `tech-debt`    | #fbca04 | Cleanup, dependency updates, tooling. |

### Status Labels
| Label              | Purpose |
|--------------------|---------|
| `needs-triage`     | New issue, not yet reviewed. |
| `ready`            | Triaged and ready for someone to pick up. |
| `in-progress`      | Actively being worked on. |
| `blocked`          | Cannot proceed — reason noted in a comment. |
| `needs-discussion` | Requires team input before proceeding. |

### Priority Labels
| Label             | Purpose |
|-------------------|---------|
| `priority: high`  | Should be addressed in the current iteration. |
| `priority: medium`| Standard priority. Schedule in upcoming iteration. |
| `priority: low`   | Address when bandwidth allows. |

## Milestone Assignment

- Assign every issue to a **Milestone** representing the target release or sprint.
- Issues without a milestone are considered backlog.
- Close milestones once the release ships and move unfinished issues to the next milestone.

## Task Lists for Sub-tasks

For issues that involve multiple steps, use GitHub task lists directly in the issue body rather than creating separate issues for trivial sub-tasks.

```markdown
## Tasks
- [ ] Research rate limiting libraries compatible with {{TECH_STACK}}
- [ ] Implement rate limiting middleware
- [ ] Add configuration for rate limit thresholds
- [ ] Write integration tests
- [ ] Update API documentation
- [ ] Deploy to staging and validate
```

GitHub tracks task list completion as a progress bar on the issue.

Create **separate linked issues** when a sub-task is large enough to warrant its own PR, discussion, or assignee.

## Linking Related Issues and PRs

### Issue References
- `Relates to #45` — general reference.
- `Depends on #67` — this issue is blocked until #67 is resolved.
- `Duplicate of #89` — close this issue in favor of #89.

### PR Closing Keywords
Including these in a PR description will auto-close the issue when the PR is merged:

- `Closes #123`
- `Fixes #123`
- `Resolves #123`

### Cross-repository References
Use the full format for issues in other repositories:

```
Relates to org/other-repo#45
```

## Assignees and Notifications

- Assign yourself when you start working on an issue.
- Mention specific people with `@username` in comments when their input is needed.
- Unassign yourself if you can no longer work on the issue so it returns to the pool.
