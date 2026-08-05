---
name: awf-review-security
description: Security-focused fresh-context pass over the implemented change — authentication and authorization, crypto, input handling at every boundary, dependency changes, sensitive-data exposure, error-path leakage — producing severity-graded findings with attack scenarios and remediations, and no verdict, in the run's security findings report. Triggers as the review stage's review-security step per the risk-class overlays — at R2 when the change touches auth, crypto, input handling, or dependencies, always at R3, recorded skipped where it does not run. General code quality belongs to awf-review-code; the verdict on the change is awf-review-validate's.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
      output:
        artifact: "{run}/security-findings.md"
        template: references/review-report.template.md
---

# Skill: awf-review-security

Adversarial security pass over the implemented change: every changed surface examined as an attacker would examine it. The focus is exclusive — vulnerabilities, weaknesses, and exposure introduced or touched by the change — not general quality, style, or architecture; those are `review-code`'s. The reviewer reports findings and renders no verdict.

## Role

The step runs as the reviewer, always with fresh context (spec §4), thinking in attack scenarios: for each finding, who can reach this code path, with what input, and what do they gain. Findings are specific and remediable — never rewrite the code, never let a known vulnerability pass unflagged, and never pad the report with hardening theater unconnected to the change.

## Inputs

- `{run}/phase-{N}-impl-log.md` (required) — what was changed and why: the files touched, dependency changes, machine-check evidence.
- The change itself, read directly — the diff of this phase's work, plus enough surrounding code to trace how untrusted data reaches it.
- The project's security context: the kind of data it handles (PII, credentials, financial, health), its trust boundaries, and any security standards or checklist the project provides.

## Method

Load `references/security-checklist.md` — the systematic catalog this pass works through: injection in every form, authentication and session weaknesses, sensitive-data exposure, access control, misconfiguration, unsafe deserialization, secrets in source, error-path leakage, storage and transport, security headers, and dependency risk.

Start from the boundaries: every point where external data enters the changed code is an attack vector — request bodies, parameters, headers, uploads, third-party responses, user-supplied paths and URLs, configuration. Verify validation and sanitization at the boundary, not deep inside. Trace authentication and authorization through the changed flows looking for bypasses: missing checks on new endpoints, checks defeated by parameter manipulation, token and session handling defects, missing ownership validation.

Search the diff for hardcoded secrets — keys, tokens, connection strings, private keys — and flag every one, test-looking values included. Review dependency additions and updates for known advisories. Check what error paths and logs expose: internal paths, schema details, stack traces with sensitive values. Where the change stores or transmits sensitive data, verify encryption at rest and in transit and that the primitives are current — no MD5 or SHA-1 in security contexts, no ECB, no home-rolled crypto.

Severity is exploit-oriented: critical means exploitable as shipped — a reachable path to breach, escalation, or exposure; major means a real weakness that widens the attack surface or is exploitable under conditions; minor means defense-in-depth eroded but not directly exploitable; suggestion means hardening worth doing. Every finding names its attack scenario — a vulnerability nobody can reach is a different severity than one on an open path, and the scenario is the evidence for the grade.

## Output

Write the report to `{run}/security-findings.md`, scaffolded from `references/review-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`), the Security dimension expanded into the catalog's sub-areas and the others condensed or dropped. Findings carry stable `S-…` ids, severity, location, the attack scenario as impact, and a concrete remediation. No verdict — `review-validate` weighs these findings alongside the code review's.
