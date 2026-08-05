# External contribution context

Load when the subject is an external contribution — a PR or branch from outside the run — rather than the run's own diff. The review dimensions are unchanged; what changes is the input, the tone, and where the attention concentrates.

## Input

The change arrives as a branch to diff against the base branch, a PR to fetch, or a pasted diff. Read the complete diff — never skim — and read the intent before judging it: commit messages in order, the PR description, any linked issue. Evaluate the code against what the author was trying to accomplish, not against what the reviewer would have built.

## Tone

The report may land verbatim as PR feedback to a colleague or an outside contributor: constructive and respectful, helping the author ship, not gatekeeping. Every finding actionable without further clarification — exact location, why it matters, concrete fix. Acknowledge good work explicitly; it is signal, not padding.

## Compatibility attention

External changes reach shared surfaces more often than run-internal ones. Weight these areas up:

- **Public API changes** — breakage for existing consumers; deprecation notices and migration paths where behavior moves.
- **Schema changes** — migrations reversible, data-integrity risks, performance of the migration itself on production-sized tables.
- **Exported interfaces** — functions, types, classes other code imports: signature and semantic compatibility.
- **Configuration** — new values documented, sensible defaults, environment-specific implications.
- **Documentation** — README, API docs, and inline docs updated where public behavior changed.

## Verification

Confirm tests cover the new behavior and its edge cases before anything else — insufficient coverage on an external change is a major finding, because nobody downstream has the author's context to catch regressions later.
