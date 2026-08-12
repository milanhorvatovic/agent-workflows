# Contributing

The deliverables here are markdown contracts and the small scripts that keep them honest. Most changes are prose with the force of an interface — a skill body, a stage contract, a spec section — so contributions are reviewed the way code is: against what the change claims, what it declares, and what the rest of the repo already says.

## How a change lands

Everything lands through a pull request against `main`. Subjects follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) — typed (`fix:`, `feat:`, `docs:`, …), imperative, under 72 characters — the same cap [`standards/commit-conventional.md`](standards/commit-conventional.md) states for consuming projects. PRs are squash-merged: the PR title becomes the subject on `main`, and the merge body is a short self-contained summary. Branch commit messages are public artifacts all the same — a PR's commits are visible the moment it opens, and squash machinery can carry their messages into the merge body — so write them to the same bar as the files they describe (the first rule below applies to them in full). Every code change, maintenance scripts included, lands with its unit tests in the same PR.

## Run the checks locally

Conformance CI ([`.github/workflows/conformance.yml`](.github/workflows/conformance.yml)) runs these on every PR; run them first:

```sh
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt

.venv/bin/python -m unittest discover -s scripts     # script unit tests
.venv/bin/python scripts/validate_conformance.py     # schemas, workflow blocks, frontmatter, budgets, step parity
.venv/bin/python scripts/generate_index.py --check   # AGENTS.md index freshness
.venv/bin/python scripts/render_standards.py --check # placeholder integrity, shared-template freshness
```

CI runs these under the Python version the workflow pins; when a result differs between local and CI, match that interpreter first.

A touched skill also gets the advisory packaging check, one directory per invocation: `npx --yes skills-ref validate skills/<name>`. It is deliberately unpinned, unlike the SHA-pinned actions in the CI workflow: the check is a canary against the current release of the Agent Skills validator, and drift there is part of what it reports. The flip side is stated rather than implied — it downloads and runs the validator's current release, which this repo has not reviewed, so treat it as you treat any unvetted executable; skipping it costs only the advisory signal, since CI does not run it. What each script covers is described in [`scripts/README.md`](scripts/README.md).

## Generated surfaces are edited at their source

Two kinds of content are generated, and CI fails on the drift rather than on the editing intent:

- The tier sections of [`AGENTS.md`](AGENTS.md), between `generated:` markers, are produced from each file's frontmatter `description` by `scripts/generate_index.py`. Edit the description at its source, regenerate, commit both. A description is a published surface — its index line is what routes a consumer to the file — so it is held to the same accuracy as the contract it summarizes.
- The shared report templates under [`standards/templates/`](standards/templates/) are copied verbatim, under a generated-copy header, into consuming skills' `references/` directories by `scripts/render_standards.py --render-shared`. Edit the source, regenerate, commit every copy with it.

## The rules no check runs

Three rules, each learned on this repo's own pull requests. They compare meaning with meaning, which is why no script enforces them and review does.

### Every claim must be checkable from this repo alone

A public artifact — a repo file, a PR description, a commit message — must not state a conclusion whose basis a reader cannot reach. The failure is subtler than naming an unreachable source: stripping the citation while keeping the conclusion launders it, turning unpublished reasoning into what reads as established convention, and a scan for foreign vocabulary cannot catch a foreign conclusion restated in local words. The test is whether a stranger can verify the claim from the repo alone; where they cannot, publish the basis or cut the claim. Two corollaries. Commit messages are in scope, precisely because they are written before anyone is thinking about a public reader. And a claim about an earlier, unpublished draft of the same change is unverifiable by construction — a draft corrected before it was ever pushed exists nowhere a reader can reach — so describe what the change does, never what an unpublished draft of it said.

### A widened declaration obliges six surfaces, and the six must agree

Whether a widening is owed at all is spec [§9.1](protocol/spec.md#91-step-and-handoff)'s completeness rule: a step declares every artifact whose content its instructions depend on. Widening a step's contract — an input added, an output moved, an edge changed — then obliges six surfaces: the skill's step block, the stage contract's copy of it, the frontmatter `description`, the body's opening summary, the downstream consumers, and the changelog. The declaration's strength is part of the widening, argued from availability rather than caution: required means some step produces the artifact before this one wherever this one runs, and optional means a real case exists where it is absent — six surfaces in agreement about an input nothing upstream produces are six surfaces agreeing on a step §9.1 leaves permanently blocked. Conformance holds the first two surfaces to agreement (the step-bound parity check); the other four are the author's, with three riders:

- Agreement, not coverage: all six touched is not all six agreeing. The standard is the meaning, not the wording — an equivalent paraphrase agrees — but paraphrase is where meaning slips, and the drift is worst in the `description`, where it publishes through the generated index and is invisible in a diff read file by file.
- A place the widening does not reach is checked and recorded as empty — the PR says which consumers were inspected and why none moves — never skipped. An unrecorded place is indistinguishable from a forgotten one.
- The `description` is where self-review fails structurally rather than carelessly: the author reads the whole file, in which the description still looks right; the reviewer reads the diff, against which it no longer matches the clause beside it. Check the description against the diff, not against the file it sits in.

### Run the repo's own checks against your own diff

The natural failure mode of a corrective change is applying the standards it edits to the artifact under correction and never to the correction itself — the findings review then makes cluster in the prose just written, not in the contracts it fixes. Three passes counter that:

- Before review: run everything above against your own diff, and hold your own prose to the rules it states — a change that states a rule can violate it in the stating, and that is exactly what review finds.
- After every fix: re-check the surfaces that describe the change — the changelog, the commit messages, the PR description — against the change itself. A claim corrected in the contract and left standing in a surface that describes it is the defect the fix itself invites. A grep of the claim's wording finds the copies that share it; a copy that paraphrases it evades the grep and is re-read, the same semantic bar as above.
- After review comes back clean: two checks still belong to the author, because they need the final diff. Pair every touched body with the template it declares — where it declares none there is nothing to pair — checking that the method says what fills each section the template carries, that the template has a place for every result the method produces, and a shared template once per consumer, not once per file. Then read each touched file whole: a diff review sees the lines that moved, and neither it nor the pairing sees what a file says together.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
