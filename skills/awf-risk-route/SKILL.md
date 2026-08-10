---
name: awf-risk-route
description: Applies the spec §5.2 classification rubric to the confirmed brief — blast radius, reversibility, security surface, decomposability, novelty, requirement ambiguity — and proposes at most one risk class, R0 through R3, with the one-line rationale run state carries, written into the brief's own Routing section. Triggers as the intake stage's risk-route step, in every workflow and every risk class, once awf-brief-confirm has confirmed the brief. Two rubric rules bind rather than being weighed — any security-surface signal proposes at least R2 and records that security review is enabled, and ambiguity above threshold withholds the class and routes back to the clarifying question rather than inflating it. It proposes and never decides — the human accepts or overrides at the intake-approval gate and the executor transcribes the accepted class into run state — and it classifies the brief rather than revisiting it, restating or reopening the brief being awf-brief-confirm's.
license: MIT
metadata:
  workflow:
    protocol: "0.1"
    step:
      role: analyst
      inputs:
        - artifact: "{run}/brief.md"
          required: true
        - artifact: "{run}/grounding.md"
          required: false
      output:
        artifact: "{run}/brief.md"
---

# Skill: awf-risk-route

Proposes how much protocol a run gets: the class that sets its execution mode, which roles split out, which gates fire and how, and whether security review runs (spec §5.1).

The second and last step of intake, in every workflow and every risk class (spec §6.2). The class it proposes is what every later stage reads before deciding how much of itself to run — which is why this step proposes and the human decides.

## Role

The step runs as the analyst (spec §3.1): weigh the evidence and state what it supports. A class is not a preference, and both errors cost. An over-classified typo fix spends a planning loop and a blocking approval gate on a one-line change; an under-classified migration reaches implementation with no validated plan to bind it.

## Inputs

- `{run}/brief.md` (required) — the confirmed brief, the only authority on intent, and where a `clarifying-question` this step raised has its answer waiting: an `accept` there resumes at classification rather than returning to `brief-confirm`, and the answer is in the brief's **Gate direction** section (spec §7) rather than in an input of its own. This gate fires before run state exists, so the section buys no durability here; what it buys is that the answer reaches this step as something to apply rather than as prose someone else already folded in. Its goal, constraints, acceptance criteria, and out-of-scope boundaries are what is being classified, and the assumptions it records are part of the ambiguity reading.
- `{run}/grounding.md` (optional) — where a grounding from an earlier run in this codebase is available and fresh (spec §8.4), it answers the three signals that are claims about the codebase rather than about the brief: blast radius, decomposability, novelty. Intake precedes the ideation stage's grounding step, so a first run has none — read the codebase directly for those three rather than inferring them from the brief's prose.
- The project's architecture standard, where one exists — blast radius is counted across the module boundaries it declares, and novelty is measured against the patterns it commits to; neither is a property of the request. Nothing here is judged for conformance, so a departure from the standard is not a finding: this step reads it to know where the project's own boundaries are.

## Method

Weigh all six rubric signals (spec §5.2) and classify on the whole reading rather than on the loudest one — except for the two that bind regardless of the rest.

**Blast radius** — the files, modules, and public API surface the work touches. Count across boundaries rather than files: ten files inside one module is a smaller radius than two files that change a signature other modules call.

**Reversibility** — what undoing the change would cost after it lands. Data migrations, released API surface, anything already running in production, and anything writing state other systems read are expensive to undo however small the diff is.

**Security surface** — auth, crypto, input handling at any boundary, dependency changes. Binding: any signal here proposes at least R2 with security review enabled (spec §5.2). Err toward yes — an unnecessary security pass costs one review, and a missed one is the failure the rule exists to prevent.

**Decomposability** — whether the work wants phases. Work that does is R3 territory (spec §5.1). Fixing the phase list belongs to planning; reading the signal that there will be one belongs here.

**Novelty** — greenfield against pattern-following. A feature new to the product, built the way this codebase already builds such things, is not novel; the same feature introducing a pattern the codebase has never carried is.

**Requirement ambiguity** — how confidently the brief can be restated. Binding, and in the other direction: this signal never inflates the class (spec §5.2). A brief too vague to classify is a brief that needs its clarifying question, so route back to the `clarifying-question` gate rather than proposing R3 to buy process against uncertainty.

Otherwise propose exactly one class. A proposal that hedges between two has not classified — "R2, possibly R3" hands the decision back to the human it was made for. Where the reading genuinely sits near a boundary, propose the class and say in the rationale which way it leans and what would move it: an override at the gate is a designed outcome (spec §5.3), and a stated boundary is what makes it cheap.

Where the two candidates are genuinely balanced, lean upward. Reclassification runs one way — a class may be raised mid-run and never lowered (spec §5.3) — so a class proposed too low is corrected only after the drift or stall signal that exposes it, by which point steps have already run under the wrong defaults.

## Output

Fill the brief's `## Routing` section in place. The output is the artifact `awf-brief-confirm` wrote: the class belongs with the brief it classifies, and the intake gate reads one document rather than two.

Record the proposed class, the one-line rationale, and the security-surface reading. The rationale is one line because the executor transcribes it verbatim into `run.risk_rationale` (spec §10), so it names the signals that decided rather than narrating the analysis. That transcription holds where the human accepts the class proposed here; where they override, `risk_rationale` takes their reason from **Accepted rationale** in the same Routing block and this line stays the proposal it was (spec §5.3). One field cannot serve both claims when they disagree, which is why the override's reason travels separately rather than overwriting the evidence for the class it displaced. The security reading is recorded whether or not it fired: the rubric's rule has two halves, and the second — enabling security review — otherwise leaves intake with nothing carrying it. `awf-review-security` declares the brief and holds that line against the change, so the reading is a claim this run checks later rather than a note that dies at the gate. Begin the value with the reading itself, `yes` or `no`, bare and with no formatting around it, and put any explanation after it: the overlays condition and `awf-review-security` read that word, so a value whose first word is the reading needs no parsing rule at either end, while one that opens with narration does. It is also what the executor evaluates to decide whether that step runs at R2 at all (the risk-class overlays), which is what makes recording the honest reading rather than the safe one matter — and matter unequally: one that fired on a surface the change never touched comes back as an over-fire the pass itself records, while one that missed a surface skips the step that would have caught it. At R3 the pass runs regardless and both come back. That asymmetry is the whole of the instruction above to err toward yes.

Do not write run state. The executor transcribes the class the human accepts at `intake-approval`, which may not be the class proposed here, into `run.risk`, and the reason for that class into `run.risk_rationale` (spec §5.3). A class written to run state before the gate decides is a proposal impersonating a decision.

Where ambiguity is above threshold, propose no class. Return to the `clarifying-question` gate and record in the Routing section what could not be pinned down, so the question that follows has a subject and the reader can see why the class is absent rather than missing.

The answer comes back to this step rather than to `brief-confirm`, since an `accept` there resumes at classification whichever step raised the question (the intake stage's gate contract). Read it from the brief's **Gate direction** section, where the executor recorded it before the outcome (spec §7), fold what it changes into the brief section it changes rather than leaving it only in the Routing note that asked for it, and empty the direction section as you go. A brief reaching the intake gate with that section still filled is a question that was answered and never applied.
