# #78 Agent 1 — Longitudinal Metrics Contract

## Scope

Implement only the contract/infrastructure portion of issue #78. Historical backfill, retrospective diagnosis, statistical interpretation of V0/V1 results, repo hygiene, and V2 empirical work are excluded.

## Requirements

- **R1 — Stable identity:** every stage must carry stable stage/context identities and immutable dataset, evaluation, baseline, code/config, artifact, and reproducibility evidence.
- **R2 — Comparability:** comparison logic must distinguish hard context incompatibility from model/feature methodology movement and fail closed when required context is missing.
- **R3 — Regression detection:** comparable stage-over-stage and best-so-far comparisons must detect material deterioration using explicit metric direction and tolerances.
- **R4 — Disposition gate:** every material regression must have an interpretation; unresolved/likely-defect regressions must be tracked and explicitly accepted before closeout can pass.
- **R5 — Single source:** the governed JSON ledger is authoritative; human-readable summaries must be generated from it.
- **R6 — Future closeout:** a CLI validation path must fail when the latest stage lacks required comparison/regression disposition evidence.

## Acceptance evidence

Schema validation, focused unit tests for identity/comparability/regression/closeout, generated-summary tests, CLI tests, repository verification, and specialist review must pass on the exact change.
