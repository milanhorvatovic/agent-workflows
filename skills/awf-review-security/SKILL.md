---
name: awf-review-security
description: Security-focused fresh-context pass over the implemented change — authentication and authorization, crypto, input handling at every boundary, dependency changes, sensitive-data exposure, error-path leakage — producing severity-graded findings with attack scenarios and remediations, and no verdict, in the run's security findings report, which also settles whether the security-surface reading intake recorded still holds against the change now visible. Triggers as the review stage's review-security step per the risk-class overlays — at R2 only where the Security surface value in the brief's Routing section begins with yes, matched case-insensitively, always at R3, recorded skipped where it does not run. General code quality belongs to awf-review-code; the verdict on the change is awf-review-validate's.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: reviewer
      inputs:
        - artifact: "{run}/phase-{N}-impl-log.md"
          required: true
        - artifact: "{run}/brief.md"
          required: true
      output:
        artifact: "{run}/security-findings.md"
        template: references/review-report.template.md
---

# Skill: awf-review-security

Adversarial security pass over the implemented change: every changed surface examined as an attacker would examine it. The focus is exclusive — vulnerabilities, weaknesses, and exposure introduced or touched by the change — not general quality, style, or architecture; those are `review-code`'s. The reviewer reports findings and renders no verdict. One thing besides findings comes out of this pass: `risk-route` made its security-surface reading against a brief, and this is the first step that can hold that reading against code — so the report says whether it held.

## Role

The step runs as the reviewer, always with fresh context (spec §4), thinking in attack scenarios: for each finding, who can reach this code path, with what input, and what do they gain. Findings are specific and remediable — never rewrite the code, never let a known vulnerability pass unflagged, and never pad the report with hardening theater unconnected to the change.

## Inputs

- `{run}/phase-{N}-impl-log.md` (required) — what was changed and why: the files touched, dependency changes, machine-check evidence. This stage runs once after the final phase, so `{N}` ranges over every completed phase rather than naming a current one: a multi-phase run has one log per phase and every one is read, since a dependency added in phase 2 is part of the surface this pass examines whatever phase came last.
- `{run}/brief.md` (required) — its `## Routing` section, where `awf-risk-route` records the security-surface reading whether or not it fired, alongside the goal and constraints that reading was made against. Spec §5.2's rule has two halves — any security-surface signal proposes at least R2 *and* enables security review — and this line is where the second half is written down; a reading nothing downstream consumes is a reading nobody can be wrong about. Required rather than optional because the brief exists wherever this step runs: `brief-confirm` is the first step of every workflow in every risk class, so no run reaches review without one.
- The change itself, read directly — the whole diff under review, which in a multi-phase run is every completed phase's work together, plus enough surrounding code to trace how untrusted data reaches it.
- The project's security context: the kind of data it handles (PII, credentials, financial, health), its trust boundaries, and any security standards or checklist the project provides.

## Method

Load `references/security-checklist.md` — the systematic catalog this pass works through: injection in every form, authentication and session weaknesses, sensitive-data exposure, access control, misconfiguration, unsafe deserialization, secrets in source, error-path leakage, storage and transport, security headers, and dependency risk.

Start from the boundaries: every point where external data enters the changed code is an attack vector — request bodies, parameters, headers, uploads, third-party responses, user-supplied paths and URLs, configuration. Verify validation and sanitization at the boundary, not deep inside. Trace authentication and authorization through the changed flows looking for bypasses: missing checks on new endpoints, checks defeated by parameter manipulation, token and session handling defects, missing ownership validation.

Search the diff for hardcoded secrets — keys, tokens, connection strings, private keys — and flag every one, test-looking values included. Review dependency additions and updates for known advisories. Check what error paths and logs expose: internal paths, schema details, stack traces with sensitive values. Where the change stores or transmits sensitive data, verify encryption at rest and in transit and that the primitives are current — no MD5 or SHA-1 in security contexts, no ECB, no home-rolled crypto.

Severity is exploit-oriented: critical means exploitable as shipped — a reachable path to breach, escalation, or exposure; major means a real weakness that widens the attack surface or is exploitable under conditions; minor means defense-in-depth eroded but not directly exploitable; suggestion means hardening worth doing. Every finding names its attack scenario — a vulnerability nobody can reach is a different severity than one on an open path, and the scenario is the evidence for the grade.

Check the brief's security-surface reading last, never first. `risk-route` read the *brief* for auth, crypto, input-handling, and dependency signals; this pass reads the *change*, which is the better evidence and did not exist yet when the reading was made. Taking the reading first anchors the search: a pass opening on "no security surface" looks less hard for one, and a review that inherits the judgment it exists to test returns less than spec §5.2's MUST bought. So work the change on its own terms, then compare. Where the surface the diff presents matches the one intake predicted, say so. Where the change touches auth, crypto, a trust boundary, or a dependency the reading did not anticipate, say that plainly: the run has been executing under a class chosen without it, and this pass is the first point at which anyone can see the difference. The opposite mismatch is worth its sentence too — a reading that fired on a surface the change never touched cost exactly one review pass, which is the error the rubric tells the classifier to prefer.

## Output

Write the report to `{run}/security-findings.md`, scaffolded from `references/review-report.template.md` (spec §8.3; a generated copy — the source lives in `standards/templates/`), the Security dimension expanded into the catalog's sub-areas and the others condensed or dropped. Findings carry stable `S-…` ids, severity, location, the attack scenario as impact, and a concrete remediation. No verdict — `review-validate` weighs these findings alongside the code review's.

Open that Security assessment with the reading's disposition — checked last so the search is not anchored, reported first because it frames every finding under it: what intake recorded, what the diff shows, and whether the two agree, with the code that decided it. It belongs there rather than in a finding because findings are defects in the change and a reading that misjudged the brief is a fact about the run — where an unanticipated surface carries real weaknesses those are findings on their own merits, and where it is clean the mismatch still belongs in the report, since nothing else in the run will notice it. The shared template is not touched for this: `review-code` has no reading to check, and a rule only one consumer reads stays with that consumer.
