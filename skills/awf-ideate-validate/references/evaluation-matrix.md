# Evaluation matrix

The working method for comparing candidate approaches. Load before comparing; the scores structure the findings and explain the verdict, and they are never the output — the report renders a verdict, not a ranking.

## Criteria

- **Feasibility** — buildable with this codebase, these dependencies, and this team's constraints, as the approach actually describes it. Scored against what was verified in the code, not against what the artifact asserts.
- **Complexity** — the effort, coordination, and technical difficulty the approach demands, relative to this project's current state. Never an absolute time estimate.
- **Risk** — the likelihood and impact of what could go wrong, including what only appears after shipping: migration, operational burden, reversal cost.
- **Architectural alignment** — fit with the codebase's existing patterns, boundaries, and technical direction. A deliberate departure is not automatically a low score, but it must be argued for in the artifact.
- **Scalability** — whether it holds as users, data, or features grow to the scale the brief implies. Where the brief implies no growth, score it as not applicable rather than inventing a scale.
- **Maintainability** — how easy it will be to understand, modify, and debug a year from now, by someone who was not here for this exploration.

## Scale

| Score | Meaning |
| --- | --- |
| 5 | Excellent — minimal concern |
| 4 | Good — low concern |
| 3 | Acceptable — moderate concern |
| 2 | Below average — notable concern |
| 1 | Poor — high concern |

## Using it

Score every candidate on every criterion, including the ones the artifact treats as obvious losers — a set where only the recommendation was seriously scored is itself a finding about the exploration.

Weight by the brief, not by habit: the brief's constraints decide which criteria matter here, so state the weighting in the report rather than carrying a fixed one. A prototype brief that says so weights complexity and feasibility; a brief with a stated growth target weights scalability and maintainability.

Read the scores as a source of findings, not as a verdict. A criterion scoring 1 or 2 on the recommended approach demands either a mitigation in the artifact or a finding in the report. A recommendation that does not lead on the criteria the brief weights heaviest is a recommendation-grounding finding unless the artifact argues the trade-off explicitly. Two candidates scoring identically across every criterion is evidence for a distinctness finding, not a tie to break.

Carry into the report only what explains the verdict: the weighting, the scores that drove findings, and the comparison where it is the clearest way to state one. A full matrix is optional; an unexplained total that contradicts the findings is worse than no matrix at all.
