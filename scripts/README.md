# scripts/

Repository maintenance scripts, stdlib-Python only. Every script carries unit tests (`test_<script>.py`, stdlib `unittest`), run by conformance CI: `python3 -m unittest discover -s scripts`.

- [`generate_index.py`](generate_index.py) — regenerates the tier sections of [`AGENTS.md`](../AGENTS.md) (roles, skills, workflows, stages) from each file's frontmatter `description`, between `generated:` markers; `--check` verifies consistency without writing and exits non-zero on drift (run by conformance CI).
