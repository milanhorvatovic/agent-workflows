# Shipping the change

Load this when the change must actually reach the project's channel — a pull request opened, a change note filed — rather than only being described. The delivery artifact is the description; getting it into the channel is the consuming project's business, and this reference states the boundary rather than automating across it.

## The standard decides the shape

The project's rendered PR or change-note standard (the `pr-*` standard installed with the framework, or whatever the project already uses) fixes the title convention, the body sections, the checklist, and the issue-linking keywords. Follow it over the delivery template's own change-description block, which exists for projects that declare no standard. Where the project has a forge template file, that template's sections are the ones to fill.

The branch and commit conventions come from the same place: the project's commit standard governs message format, and commits were already made under it during implementation. Nothing is re-committed here.

## What this step does and does not do

Preparing the description is this step's job. Opening the pull request, pushing the branch, requesting reviewers, and merging are the consumer's channel — a person, a forge CLI, or a harness integration acting on the artifact. Two rules bound whatever performs it:

- Nothing is published before the `delivery-approval` gate returns `accept`. The gate is the approval; there is no separate confirmation prompt, and a gate that has not fired is not an implicit yes.
- Merging, force-pushing, closing issues, and re-targeting branches are never inferred from an `accept`. Accepting the delivery approves the change and its description, not every downstream action a forge makes available.

## Where the description goes

Whoever ships it copies the change description verbatim from `{run}/delivery.md` — the artifact is the source of truth, so a description edited only in the forge leaves the run's record wrong. A late edit belongs in the artifact first, which is what a gate `revise` outcome returns here to do.

Link the run: the artifact path, the ticket or issue the brief came from, and any design document the brief cites. A reviewer landing on the change should be able to reach the run's evidence without asking.
