---
name: awf-plan-revise
description: Revises a phase plan against validation findings, human direction from the plan-approval gate, structured implementation feedback, or another phase's cascading changes — deciding accept, reject, or defer per finding with an auditable feedback trail, preserving unaffected content, and logging every revision in the plan's changelog, while escalating rather than revising wherever a change would break a phase list that later phases are already bound to, and applying a phase-1 gate's direction where that list is the only thing in its way. Triggers as the planning stage's plan-revise step whenever a plan-validate verdict, a gate revise outcome, or escalated implementation feedback routes back into planning. Creating a plan from scratch is awf-plan-create; rendering the verdict on the revised plan is awf-plan-validate.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: planner
      inputs:
        - artifact: "{run}/phase-{N}-plan.md"
          required: true
        - artifact: "{run}/phase-{N}-plan-validation.md"
          required: true
        - artifact: "{run}/phase-1-plan.md"
          required: true
      output:
        artifact: "{run}/phase-{N}-plan.md"
      on:
        PASS: plan-approval
        PASS_WITH_CONDITIONS: plan-revise
        FAIL: plan-revise
---

# Skill: awf-plan-revise

Rewrites the phase plan to address what came back: validation findings, a human's direction from the plan-approval gate, structured feedback escalated from implementation, or the ripple of another phase's revision. Every finding gets an explicit decision with reasoning, every revision leaves an audit trail, and unaffected content survives untouched — a revision is surgery, not a rewrite from scratch.

## Role

The step runs as the planner: answer each finding with reasoning, keep the plan specific enough to implement without guessing, and flag remaining uncertainty instead of burying it. The output is the revised plan, not a rebuttal — but rejecting a finding with justification is legitimate; silently ignoring one is not.

## Inputs

- `{run}/phase-{N}-plan.md` (required) — the current plan, revised in place, and where a `plan-approval` `revise` leaves its direction: the human's decisions and answers are recorded in the plan's **Gate direction** section before the outcome is (spec §7), so no separate input carries them. Read that section, apply what it asks into the plan itself, and record each item in the feedback file's `direction` list as the audit of what was decided — where direction that keys to no finding goes, and the gate fires on a *passing* validation, so direction that is about no finding is the ordinary case rather than the exception — and return the section to `None` in the revision.
- `{run}/phase-{N}-plan-validation.md` (required) — the validation report whose findings and questions drive the revision; its stable finding and question ids are what the decisions reference.
- `{run}/phase-1-plan.md` (required) — the phase list this revision must stay inside once it is fixed: moving scope between phases, adding one, or shifting a boundary breaks it, and this is what says whether an accepted finding would. Fixed means approved — the phase-1 plan authors the list, validation checks it, and `plan-approval` is what binds it for the run, which is why direction at that gate can still move it and a revision afterwards cannot. Without it the escalation below has nothing to test against, so the list gets broken silently by a revision that looks local. Required rather than optional because it always exists wherever this step runs, the same availability argument `plan-validate` makes for the same input: revising phase 1 or a single-phase run, `{N}` is 1 and this resolves to the plan under revision; revising a later phase, phase 1 was planned before that phase could exist. Never satisfied from another run, the guard `plan-validate` states for the same artifact: §8.4's cache does not reach a required input, and a decomposition made for a different run would be the wrong list even if it did — so check the plan's `Run` header.
- The project's coding and architecture standards, where they exist — revisions stay inside them, and a revision that must depart from one records the departure with its reasoning rather than making it quietly. A finding that asks for a change contradicting a standard is answered on the record — accepted with the departure argued, or rejected citing the standard — never split the difference in silence.
- Depending on the entry point, the driving feedback also includes: the implementation log's structured plan-defect feedback (what is wrong, where, suggested correction) when implementation escalated back into planning; the triggering phase's revised plan in a cross-phase cascade.

## Method

Determine the entry point from what arrived — a fresh validation report (the revise loop), human direction from the gate, implementation feedback, or a cascade — then process every finding and question to a decision: **accept** (revise accordingly), **reject** (disagree, with reasoning), or **defer** (address later, recorded in the plan's risks or open questions). Human decisions, where provided, are followed, not re-argued; the planner decides the rest itself and documents each decision per `references/feedback-format.md` — load it before recording decisions, and whenever a feedback YAML arrives as input.

For implementation feedback, revise around the work already done: address the defect the implementer hit without invalidating completed steps, and prefer the correction that disturbs the fewest untouched steps. For a cross-phase cascade, first establish which of this plan's assumptions and dependencies the other phase's change actually breaks, and revise only that.

Apply accepted changes surgically: modify the affected steps, add or remove steps where the correction requires it, and update the file scope, testing plan, rollback, and technical decisions wherever a change touches them — a revised step whose file-scope entry or test requirement still describes the old version is the classic revision defect, and `plan-validate` checks for exactly that.

Respect the phase list, read from `{run}/phase-1-plan.md`, once it is fixed — and `plan-approval` is what fixes it. Before that the list is provisional: a validation finding this revision accepts may move it, as may the human's direction at that gate, which is what lets the loop correct a decomposition the validator found wrong rather than escalating a plan nobody has approved. After approval, what cannot stay within it — scope must move between phases, the list needs a new phase, a boundary must shift — splits by where it came from, and the split is `plan-validate`'s to act on rather than a preference.

The human's own direction escalates by the route the protocol has: state what it requires and why it breaks the list as an **Open question** in the plan, and revise everything else the iteration can. That question is addressed to the human at `plan-approval` rather than to the planner, so it does not block — the plan is implementable as written, and what is open is whether they want it changed. `plan-validate` passes a plan whose only open question is one of these, the gate is reached, and the person who set the boundary decides about it. Left blocking instead it would FAIL, the loop exits only on PASS, and the escalation would reach a human by the stall or the cap — the backstop for an escalation nobody made, not the path for one deliberately made.

A validation finding this revision accepts takes the other route, and must: where covering it needs a re-cut of a list approval has fixed, the plan cannot cover the requirement at all, and `plan-validate` keeps that finding blocking so the plan does not reach approval carrying coverage nobody could establish. Record what the re-cut would require, leave the finding unresolved rather than dressing it as a question for the gate, and the loop's stall signal escalates it. The difference is not who is inconvenienced but what is true of the plan: direction leaves it implementable and asks whether to change it, an uncoverable requirement leaves it defective. That decision belongs to the human at a gate, never to a revision quietly rewriting the run's shape — which is why direction from `plan-approval` is applied rather than escalated *where changing the still-provisional phase list is the only thing standing in its way*: the human at the gate is asking, the list is this plan's own content, and nothing has been built against it, so escalation would return their instruction to them with nothing new attached. Any other blocker still escalates, before approval as after — direction that is infeasible, that contradicts the brief, or that would depart from a project standard is not made workable by the list being provisional, and accepting it produces a plan that fails validation instead of a question the human can answer. Once the list is fixed the escalation returns for the reason it always had: it bounds work already planned or done, and what the planner returns is what the change would cost, which the first ask could not see.

Direction that answers an escalation this plan already carries is the other half of that, and is applied rather than escalated again. The open question stated what the re-cut would cost; direction that comes back to it is the human deciding with that in front of them, which is the whole point of returning the cost rather than the refusal. Escalating a second time would ask them the question they just answered, and the loop would run until its cap on a decision that was already made. Where `{N}` is 1 that is a revision like any other: the list lives in the artifact under revision, so apply the re-cut and record in the plan what it invalidates — the phases planned against the old boundary, the work already done inside it — because that consequence is what their answer bought and the next reader cannot infer it from a list that now looks deliberate.

Where `{N}` is greater than 1 this step cannot carry it out, and saying so is the honest answer rather than a route. The list lives in `{run}/phase-1-plan.md`, which is declared here as an input and is another step's output; rewriting it is precisely what the one-output contract forbids, and no edge in this stage returns a later phase to phase-1 planning. Record the authorization in the plan's **Open questions**, with what the re-cut needs: the run's decomposition re-planned, which nothing in this run can do. A `revise` returns here to the same wall, and a `reject` at this gate ends the current phase and moves to the next one (spec §7) — it carries on under the decomposition the re-cut was meant to replace rather than replacing it. The protocol has no outcome that abandons a multi-phase run part-way, so acting on the authorization means ending this run outside the gate vocabulary and starting another whose phase-1 plan cuts the phases the human asked for. Say that, rather than naming a gate outcome that would not do it. What this step can still do is everything the direction asks for that stays inside the list. The criterion is approval throughout, never the phase number — a phase-1 plan revised after its approval, on feedback escalated from implementation, is as bound by the list as any later phase's.

Questions that remain unresolved go to the plan's open questions section, never answered by a guessed default. Iteration caps and stall detection live in the stage's loop contract, not here — reaching them is the executor's escalation, and the revision simply leaves the plan in its honest current state.

## Output

The revised plan, written back to `{run}/phase-{N}-plan.md`: same structure, unaffected content preserved, and one new changelog row — iteration, date, what changed, and which trigger drove it (validation, gate, implementation feedback, cascade).

Alongside it, the decision audit: `{run}/phase-{N}-plan-feedback-{iteration}.yaml` per `references/feedback-format.md`, recording every decision and question resolution of this iteration. The revised plan is re-validated by `plan-validate` under the loop contract.
