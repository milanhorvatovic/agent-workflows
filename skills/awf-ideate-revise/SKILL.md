---
name: awf-ideate-revise
description: Rewrites the run's ideation artifact against the validation findings — every finding and question decided accept, reject, or defer with its rationale recorded in the artifact's revision log, approaches deepened, differentiated, added, or discarded where a finding lands, the recommendation re-examined whenever the candidate set changed, and everything the findings did not touch preserved. Triggers as the ideation stage's ideate-revise step whenever an ideate-validate verdict of PASS_WITH_CONDITIONS or FAIL routes back into ideation, on every loop iteration until the verdict passes. Answering a distinctness finding by renaming rather than by differentiating or dropping an approach is the stall the loop detects, never a revision. Creating the exploration from scratch is awf-ideate; rendering the verdict on the revised artifact is awf-ideate-validate, never this skill.
license: MIT
metadata:
  workflow:
    protocol: "0.2"
    step:
      role: planner
      inputs:
        - artifact: "{run}/ideation.md"
          required: true
        - artifact: "{run}/ideation-validation.md"
          required: true
      output:
        artifact: "{run}/ideation.md"
      on:
        PASS: planning
        PASS_WITH_CONDITIONS: ideate-revise
        FAIL: ideate-revise
---

# Skill: awf-ideate-revise

Rewrites the ideation to answer what the validator found. Every finding gets an explicit decision with reasoning, the revision leaves an audit trail in the artifact itself, and content no finding touched survives untouched — a revision is surgery, not a fresh exploration that happens to reuse the problem statement.

## Role

The step runs as the planner: answer each finding with reasoning, keep the exploration honest about what it now claims, and surface remaining uncertainty rather than smoothing it over. The output is the revised artifact, not a rebuttal — but rejecting a finding with justification is legitimate; silently ignoring one is not.

## Inputs

- `{run}/ideation.md` (required) — the current exploration, revised in place. It carries the problem, the brief's constraints, and the acceptance criteria in its own words, which is why the brief is not a separate input here: the artifact restates what it was written against, and findings cite the brief where they rest on it.
- `{run}/ideation-validation.md` (required) — the report whose findings and questions drive the revision; its stable `F-…` and `Q-…` ids are what the revision log's decisions reference.
- The project's architecture standard, where one exists — the same bar `ideate` generated against. An approach added or reshaped in revision meets it or argues its departure; a revision is not a route around a standard the original exploration respected.

## Method

Process every finding and every question to a decision: **accept** (revise accordingly), **reject** (disagree, with the reasoning), or **defer** (record it as an open question or a stated risk instead of resolving it now). Nothing is left undecided, and a rejection is only as good as its argument — the next validation reads it.

Apply accepted changes where they land. A feasibility finding is answered by verifying against the code and correcting the claim, not by softening its wording. A coverage finding is answered by an approach that actually addresses the uncovered criterion, given the same treatment as every original candidate — core idea, advantages, risks, impact, complexity, decisions — or by establishing that the brief cannot be satisfied as written. A risk-honesty finding is answered by naming the risk and what it costs, even when doing so weakens the recommendation.

Distinctness findings have exactly two honest answers: differentiate the approach so it genuinely differs in shape, or discard it and record it in the discarded set with the reason. Renaming, reordering, or restating is the no-artifact-delta stall the loop's contract watches for, and it burns an iteration without moving the exploration.

Re-examine the recommendation whenever the candidate set changed. An approach added, removed, or materially revised changes what the recommendation was chosen against, so it must be re-argued explicitly — restated with its reasoning and its overturning condition — or replaced. A recommendation left standing because no finding named it is the classic revision defect here.

Where a finding cannot be answered without changing the brief — every candidate fails a stated constraint, or two criteria are mutually exclusive — the revision does not resolve it. Record it as an open question naming the conflict and the alternatives, and say plainly in the revision log that this is what happened. That decision belongs to the human at `plan-approval`, which is where this stage's open questions surface.

Iteration caps and stall detection live in the stage's loop contract, not here — reaching them is the executor's escalation, and the revision simply leaves the artifact in its honest current state.

## Output

The revised artifact, written back to `{run}/ideation.md`: same structure, untouched content preserved, discarded approaches kept rather than deleted so a later iteration cannot re-propose them.

Alongside the revision, the decision audit: one revision-log row per finding and question decided this iteration — id, decision, and what changed or why nothing did. The trail lives in the artifact because the stage declares one output for this loop and one source of feedback for it; the revised artifact is re-validated by `ideate-validate` under the loop contract.
