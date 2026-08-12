# standards/

Single source of truth for coding and artifact standards. Every file here is a placeholder-parameterized source; project-specific copies are **generated** from these files by [`scripts/render_standards.py`](../scripts/render_standards.py), never hand-copied — one authored source, rendered variants, no drift.

## Sources

Quality standards, internalized by task skills before executing:

- [`coding.md`](coding.md) — naming, code organization, error handling, documentation
- [`architecture.md`](architecture.md) — architecture pattern, module boundaries, dependency direction, API design
- [`testing.md`](testing.md) — test organization, naming, assertion style, coverage expectations
- [`review-checklist.md`](review-checklist.md) — systematic checklist applied during code review

Artifact formats, selected per project — one commit format, one PR format, one tracker format:

- [`commit-conventional.md`](commit-conventional.md) / [`commit-angular.md`](commit-angular.md) — commit message standards
- [`pr-github.md`](pr-github.md) / [`pr-gitlab.md`](pr-gitlab.md) / [`pr-bitbucket.md`](pr-bitbucket.md) — pull/merge request standards
- [`ticket-jira.md`](ticket-jira.md) / [`ticket-linear.md`](ticket-linear.md) / [`ticket-github-issues.md`](ticket-github-issues.md) — ticket/issue standards

A tool not listed here needs no framework change: a consuming project writes its own rendered-standard file (e.g. `ticket-format.md` for another tracker) and skills honor it the same way.

## Shared report templates

[`templates/`](templates/) holds report templates that several skills share — currently two: [`templates/validation-report.template.md`](templates/validation-report.template.md), the verdict report every validator skill declares, and [`templates/review-report.template.md`](templates/review-report.template.md), the verdict-free findings report both review passes declare. Each is authored once here and copied verbatim, under a generated-do-not-edit header, into every consuming skill's `references/` directory by `render_standards.py --render-shared`; the copies are committed, and conformance CI's `--check` fails on a copy that is missing or has drifted from its source. Unlike the sources above, shared templates never render for a consumer and carry no `{{…}}` placeholders — the bracketed section prompts and `{run}` tokens inside them are template content, not render syntax. Edit the source, regenerate, commit both.

## Placeholders

The vocabulary is closed — sources may use only these tokens, and conformance CI fails on anything else (`render_standards.py --check`):

| Placeholder | Meaning |
| --- | --- |
| `{{PROJECT_NAME}}` | the consuming project's name |
| `{{TECH_STACK}}` | the project's primary language/framework stack |
| `{{ARCHITECTURE_TYPE}}` | the project's architecture pattern |

Single-brace text (`/users/{id}`, JSON examples) is ordinary content, not placeholder syntax.

## Rendering

[`setup/init.py`](../setup/README.md) renders into a consuming project's `.agents/standards/` as part of an install; the direct invocation below serves re-renders and other layouts:

```sh
python3 scripts/render_standards.py --config project.json --out .agents/standards
```

where `project.json` supplies the placeholder values:

```json
{
  "PROJECT_NAME": "acme-shop",
  "TECH_STACK": "TypeScript/Node",
  "ARCHITECTURE_TYPE": "modular monolith"
}
```

`--only coding,testing,commit-conventional,pr-github,ticket-jira` renders a selection. Rendered copies are the project's to customize further — the HTML comments inside mark the sections meant to evolve with the project (valid scopes, stack-specific conventions).
