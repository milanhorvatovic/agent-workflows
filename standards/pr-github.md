# GitHub Pull Request Standard - {{PROJECT_NAME}}

## Title Format

```
<type>(<scope>): <short summary>
```

- Follow the same type and scope conventions as the project commit standard.
- Keep the title under 72 characters.
- Use imperative mood: "add" not "added" or "adding."

Examples:
- `feat(auth): add OAuth2 login flow`
- `fix(api): handle timeout on payment endpoint`

## Description Body

Every PR must include a description using the structure below.

---

### Summary

<!-- What does this PR do and why? Provide enough context for a reviewer who is not familiar with the ticket. -->

A brief explanation of the change, its motivation, and any relevant background. Link to the design doc or RFC if one exists.

### Changes

<!-- Bulleted list of the concrete modifications. Group by area if the PR spans multiple modules. -->

- Added `AuthService.loginWithOAuth()` method.
- Updated `/login` route to accept the `provider` query parameter.
- Created migration to add `oauth_provider` column to `users` table.
- Updated unit and integration tests for the auth module.

### Testing

<!-- How should a reviewer verify this works? Include commands, URLs, or manual steps. -->

1. Run the test suite: `npm test` (or equivalent for {{TECH_STACK}}).
2. Start the dev server and navigate to `/login?provider=google`.
3. Verify the OAuth redirect flow completes and the user record is created.

### Screenshots / Recordings

<!-- If the change has a visual component, attach before/after screenshots or a short recording. Remove this section if not applicable. -->

### Checklist

- [ ] Tests pass locally and in CI.
- [ ] Code follows the project coding standards.
- [ ] Documentation updated (if public API or behavior changed).
- [ ] No breaking changes — or breaking changes are documented and communicated.
- [ ] PR is appropriately sized (single concern, reviewable in one sitting).
- [ ] Self-reviewed the diff before requesting review.

### Related Issues

<!-- Link to related GitHub issues. Use closing keywords for issues resolved by this PR. -->

- Closes #123
- Relates to #456

---

## Guidelines for Authors

- Keep PRs focused. One logical change per PR.
- Provide context in the description — reviewers should not have to read the ticket to understand the PR.
- Respond to review comments promptly. Resolve conversations after addressing feedback.
- Rebase onto the target branch before requesting re-review if conflicts arise.

## Guidelines for Reviewers

- Review within one business day of being requested.
- Focus on correctness, security, and maintainability — not personal style preferences.
- Use the project code review checklist as a guide.
- Approve only when all checklist items are satisfied or explicitly waived.
