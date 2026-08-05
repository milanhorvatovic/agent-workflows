# Bitbucket Pull Request Standard - {{PROJECT_NAME}}

## Title Format

```
<type>(<scope>): <short summary>
```

- Follow the same type and scope conventions as the project commit standard.
- Keep the title under 72 characters.
- Use imperative mood.

Examples:
- `feat(payments): integrate Stripe webhook handling`
- `fix(reports): correct date range filter for quarterly exports`

## Description Body

Every PR must include a description using the structure below.

---

### Summary

<!-- What does this PR do and why? -->

A clear explanation of the change, its motivation, and relevant context.

### Changes

<!-- Bulleted list of the concrete modifications. -->

- Added `StripeWebhookController` to process payment events.
- Implemented signature verification for incoming webhooks.
- Created `PaymentEvent` domain model and persistence layer.
- Added unit tests for webhook signature verification.
- Added integration tests for end-to-end payment event processing.

### Testing

<!-- How to verify the change. Include commands or manual steps. -->

1. Run the test suite: specify the command for {{TECH_STACK}}.
2. Use the Stripe CLI to send test webhook events: `stripe trigger payment_intent.succeeded`.
3. Verify events are recorded in the `payment_events` table.

### Screenshots / Recordings

<!-- Attach if the change is visual. Remove if not applicable. -->

### Checklist

- [ ] Tests pass locally and in the Bitbucket Pipeline.
- [ ] Code follows the project coding standards.
- [ ] Documentation updated where applicable.
- [ ] No breaking changes — or they are documented.
- [ ] PR addresses a single concern.
- [ ] Self-reviewed the diff before adding reviewers.

### JIRA Issue

<!-- Link the related JIRA ticket. Bitbucket integrations recognize these patterns. -->

- Jira: [PROJ-123](https://your-org.atlassian.net/browse/PROJ-123)
- Jira: PROJ-456

> **Tip**: Including the JIRA issue key (e.g., `PROJ-123`) in the branch name or commit message enables automatic linking in the Bitbucket-JIRA integration.

---

## Branch Naming Convention

Use the following pattern so Bitbucket and JIRA integration works automatically:

```
<type>/PROJ-<number>-<short-description>
```

Examples:
- `feature/PROJ-123-stripe-webhooks`
- `bugfix/PROJ-456-date-filter-fix`
- `hotfix/PROJ-789-null-pointer-crash`

## Pipeline Requirements

The following Bitbucket Pipeline steps must pass before a PR can be merged:

1. **Build** — project compiles successfully.
2. **Lint** — code style checks pass.
3. **Test** — unit and integration tests pass.
4. **Security Scan** — no critical vulnerabilities in dependencies.

## Merge Strategy

- Use **squash merge** for feature branches to keep the main branch history clean.
- The squash commit message should follow the commit standard.
- Delete the source branch after merge.

## Guidelines for Authors

- Keep PRs focused. One logical change per PR.
- Provide context in the description.
- Link the JIRA ticket in both the branch name and the PR description.
- Respond to review comments promptly.

## Guidelines for Reviewers

- Review within one business day.
- Use the project code review checklist.
- Use inline comments with suggested changes where possible.
- Approve only when all pipeline steps pass and checklist items are addressed.
