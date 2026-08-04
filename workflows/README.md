# workflows/

Composable stages in `stages/` plus the workflows that reference them — `feature.md`, `bugfix.md`, `plan.md`. Workflows compose stages by reference and never restate stage bodies; how much of a workflow runs is decided per risk class in `overlays.md`, encoded once for all workflows.

Every stage step, loop contract, and workflow trigger is declared as a `metadata.workflow` block validating against [`protocol/schemas/`](../protocol/schemas/). See [`protocol/spec.md`](../protocol/spec.md), sections 6, 7, and 9.

Validate the blocks with a YAML 1.2 parser (for example, check-jsonschema): under YAML 1.1 the `on` key coerces to boolean `true`, and every step block spuriously fails the schemas' `additionalProperties: false`.
