---
name: awf-review-arbitrate
description: Synthesizes the review's parallel outputs — reviewer findings, security findings, the validator's verdict — into one deduplicated, triaged resolution list, attempting a genuine refutation before accepting any finding, arguing the opposing case when sources agree, and recording rationale for every dismissal and merge. Triggers as the review stage's review-arbitrate step when findings and verdict disagree — a passing verdict over unresolved critical findings, or a contested failure — and always at R3; recorded skipped otherwise. It triages what the sources found and never reviews the change fresh; the findings come from awf-review-code and awf-review-security, the verdict from awf-review-validate, and acting on the resolved list is awf-review-fix.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: arbiter
      inputs:
        - artifact: "{run}/review-findings.md"
          required: true
        - artifact: "{run}/review-validation.md"
          required: true
        - artifact: "{run}/security-findings.md"
          required: false
      output:
        artifact: "{run}/review-resolution.md"
        template: references/resolution.template.md
---

# Skill: awf-review-arbitrate

Turns the review's raw parallel outputs into one list `review-fix` can execute without judgment calls. The step exists because sources disagree — a verdict passing over unresolved criticals, a failure the findings do not support, the same defect graded three ways — and because agreement is not evidence either: consensus gets challenged before it gets endorsed.

## Role

The step runs as the arbiter, the skeptical synthesist: every accepted finding records the refutation attempt that failed, every dismissal carries rationale as rigorous as an acceptance, and unanimity triggers the devil's-advocate pass instead of a rubber stamp. This is triage of what the sources found — spot-checking their citations against the change is in scope, conducting a fresh review is not, and findings of the arbiter's own are out of scope entirely.

## Inputs

- `{run}/review-findings.md` (required) — the code review's findings, `R-…` ids.
- `{run}/review-validation.md` (required) — the validator's verdict, dispositions, contested findings, and own `F-…` findings.
- `{run}/security-findings.md` (optional) — the security pass's findings, `S-…` ids, where that step ran.
- The change itself, for spot-checking citations — read where a finding is contested or its evidence is in doubt, not wholesale.
- The project's coding, architecture, and testing standards, and its review checklist where one exists — what a finding that invokes a standard is refuted or accepted against. A refutation attempt that cannot check the rule the finding cites is not an attempt.

## Method

Inventory every finding across the sources by id, then deduplicate: the same underlying defect surfaced through different lenses collapses into one entry keeping the strongest statement, the absorbed ids recorded. Where sources grade one defect differently, resolve the severity on evidence — what actually happens if it ships — not by averaging and not by source count.

Attempt a genuine refutation of every surviving finding: the strongest case that it is wrong, mistaken about the code, or immaterial. A finding is accepted because the refutation failed, and the report records both the attempt and why it failed. Contested findings — the validator's dispositions that dispute a reviewer's claim, or vice versa — are resolved the same way, by the diff, with the losing side's reasoning preserved.

Where the sources agree — including an uncontested verdict — argue the strongest opposing case before endorsing: what would have to be true for the consensus to be wrong, and why it is not. A conflict the evidence cannot resolve is escalated explicitly in the report, never averaged away or silently dropped.

Triage what survives by severity and actionability into fix order, each entry stating concretely what `review-fix` must do.

## Output

Write the report to `{run}/review-resolution.md`, scaffolded from `references/resolution.template.md` (spec §8.3): the resolved findings in fix order with refutation attempts recorded, dismissed findings with rationale, conflicts with their resolution or explicit escalation, and the devil's-advocate case where sources agreed. Every entry stays traceable to its source ids — `review-fix` binds to this list where it exists, and the next validation can audit every decision made here.
