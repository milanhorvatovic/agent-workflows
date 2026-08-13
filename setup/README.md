# setup/

Installs the framework into a consuming project: every skill package from [`skills/`](../skills/) into the project's `.agents/skills/` (the canonical cross-client path), and the project's standards rendered from the [`standards/`](../standards/) single source into `.agents/standards/`.

## Usage

Interactive — answers collected at the prompt, and the run ends by printing the JSON that repeats it non-interactively:

```sh
python3 setup/init.py --target /path/to/project
```

Non-interactive (CI onboarding) — answers supplied as JSON:

```sh
python3 setup/init.py --target /path/to/project --config setup.json
```

where `setup.json` supplies the placeholder values and at most one artifact-format variant per family — omit a family, or give `none`, to render nothing for it:

```json
{
  "placeholders": {
    "PROJECT_NAME": "acme-shop",
    "TECH_STACK": "TypeScript/Node",
    "ARCHITECTURE_TYPE": "modular monolith"
  },
  "commit_format": "conventional",
  "pr_format": "github",
  "ticket_format": "jira"
}
```

Every standard outside the three format families (`commit`, `pr`, `ticket`) always renders. The variants are the `standards/` file stems — `commit-conventional.md` is `"commit_format": "conventional"` — and an unknown choice fails naming the available set.

## What an install writes

- `.agents/skills/<name>/` — every skill package, copied whole (`SKILL.md` plus its `references/`)
- `.agents/standards/*.md` — the rendered standards
- `.agents/awf-install-manifest.json` — the install manifest: every installed path with a content digest and the framework source tag (`--source-tag` when given; otherwise `git describe` of the checkout, falling back to the CHANGELOG's latest release where the copy has no git history). Commit it with the install — it is what gives later re-runs their ownership knowledge.

## Collision safety and re-runs

Setup never silently overwrites what it did not install, and never overwrites what the consumer changed:

- A path the manifest does not record is skipped and reported; a pre-existing path — a skill directory or a rendered standard — byte-identical to what setup would write is adopted into the manifest without a write.
- A recorded install the consumer modified is skipped and reported — remove it and re-run to reinstall. Rendered standards are the project's to customize (see [`standards/README.md`](../standards/README.md)), and a customized standard is precisely a modified install, so upgrades report it rather than clobber it.
- A recorded install left unmodified is refreshed when the source changed, and reported up to date when it did not — a re-run against an unchanged source changes nothing.
- A recorded install the current run no longer ships or selects is reported stale, never deleted.

Unit tests live in [`test_init.py`](test_init.py) (`python3 -m unittest discover -s setup`), run by conformance CI alongside a smoke install of this repository into a scratch project.
