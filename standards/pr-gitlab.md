# GitLab Merge Request Standard - {{PROJECT_NAME}}

## Title Format

```
<type>(<scope>): <short summary>
```

- Follow the same type and scope conventions as the project commit standard.
- Keep the title under 72 characters.
- Use imperative mood.

Examples:
- `feat(auth): add SAML single sign-on support`
- `fix(db): resolve connection pool exhaustion under load`

## Description Body

Every MR must include a description using the structure below.

---

### Summary

<!-- What does this MR do and why? Provide enough context for a reviewer unfamiliar with the ticket. -->

A clear explanation of the change, its motivation, and relevant background.

### Changes

<!-- Bulleted list of concrete modifications. -->

- Implemented `SamlAuthProvider` class in the auth module.
- Added `/auth/saml/callback` endpoint.
- Updated configuration schema to accept SAML provider settings.
- Added integration tests for the SAML flow.

### Testing

<!-- How to verify. Include commands, steps, or relevant URLs. -->

1. Run the test suite: specify the command for {{TECH_STACK}}.
2. Configure a test SAML identity provider (instructions in `docs/saml-setup.md`).
3. Navigate to `/auth/saml/login` and verify the redirect and callback.

### Screenshots / Recordings

<!-- Attach before/after if the change is visual. Remove if not applicable. -->

### Checklist

- [ ] Tests pass locally and in CI pipeline.
- [ ] Code follows the project coding standards.
- [ ] Documentation updated where applicable.
- [ ] No breaking changes — or they are documented.
- [ ] MR is focused on a single concern.
- [ ] Self-reviewed the diff.

### Related Issues

<!-- Use closing patterns that GitLab recognizes. -->

- Closes #123
- Relates to #456

---

## GitLab Quick Actions

Use these in MR comments or description to automate triage:

```
/label ~"type::feature" ~"module::auth"
/assign @reviewer-handle
/milestone %v2.1
/approve
```

### Common Labels

| Label               | Purpose |
|---------------------|---------|
| `~"type::feature"`  | New functionality |
| `~"type::bug"`      | Bug fix |
| `~"type::refactor"` | Code improvement |
| `~"priority::high"` | Needs prompt review |
| `~"needs-review"`   | Ready for reviewer attention |

## Pipeline Requirements

The following CI stages must succeed before an MR can be merged:

1. **Build** — project compiles and dependencies resolve.
2. **Lint** — code style and static analysis checks pass.
3. **Test** — unit and integration test suites pass.
4. **Security** — dependency vulnerability scan produces no critical findings.

## Guidelines for Authors

- Keep MRs focused. One logical change per MR.
- Provide context in the description. Reviewers should not have to read the issue to understand the MR.
- Rebase onto the target branch rather than creating merge commits.
- Resolve threads after addressing feedback.

## Guidelines for Reviewers

- Review within one business day.
- Use the project code review checklist.
- Approve only when all checklist items are satisfied.
- Use GitLab suggestions for small inline fixes instead of vague comments.
