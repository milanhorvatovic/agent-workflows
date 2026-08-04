# protocol/schemas/

Normative JSON Schemas (draft 2020-12) for the four protocol structures defined in [`../spec.md`](../spec.md):

- [`step.schema.json`](step.schema.json) — step/handoff: the acting role, the input contract, the declared output, verdict-routed edges (spec §9.1)
- [`loop.schema.json`](loop.schema.json) — loop contract: exit-criteria conjunction, iteration cap, stall detection, scope binding (spec §9.2)
- [`trigger.schema.json`](trigger.schema.json) — workflow entry trigger: kind, cadence, stop condition (spec §9.3)
- [`run-state.schema.json`](run-state.schema.json) — the executor-maintained `workflow-state.yaml` (spec §10)

The step, loop, and trigger schemas validate the value of a skill's `metadata.workflow` frontmatter key. Each is strict within its own structure but tolerates unknown _top-level_ keys under `workflow` — siblings of the declared structures — per the 0.x degradation rules (spec §9.4); one block may carry `step`, `loop`, and `trigger` together. The run-state schema validates the whole state file and rejects unknown keys; that format is protocol-owned.

[`examples/`](examples/) carries one commented, minimal **starter** per schema (`*.valid.yaml` — copy, paste, adjust) and one deliberately broken counterpart (`*.invalid.yaml`) that schema validation must reject. Validate with any standard JSON Schema validator, for example:

```sh
cd protocol/schemas && uvx check-jsonschema --schemafile step.schema.json examples/step.valid.yaml
```
