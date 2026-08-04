# scripts/

Repository maintenance scripts, stdlib-Python only.

- [`generate-index.py`](generate-index.py) — regenerates the tier sections of [`AGENTS.md`](../AGENTS.md) (roles, skills, workflows, stages) from each file's frontmatter `description`, between `generated:` markers; `--check` verifies consistency without writing and exits non-zero on drift (run by conformance CI).
