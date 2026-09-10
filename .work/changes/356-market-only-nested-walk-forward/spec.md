# Change Specification: Market-Only Nested Walk-Forward

- **Change ID**: `356-market-only-nested-walk-forward`
- **Status**: implemented; pending verification/review/delivery
- **Complexity**: `large`; risk trigger `money`

## Authority

- Phase-2 L3: issue #356 comment `5621959654`.
- Execution-source amendment: issue #356 comment `5625358200`.
- Work handoff: `WORK-356`, fingerprint `11f941fad28dc03cbcda44d890f13c5e0677a3145ed2e55d17ff0a3f386eb206`.
- Phase-1 execution/risk authority: merged #355 at base `365e1ad`.

## Implemented outcome

The runner reconstructs only retained pre-2023 Databento NG evidence, uses conservative PIT timestamps, forms exact-contract UTC-day execution segments, prevents targets crossing unpriceable gaps, builds the frozen market-only feature sets, and runs the predeclared nested chronological candidate grid under the inherited risk/cost engine.

Runtime hardening adds source hashing, atomic hash-bound checkpoints, run locking, heartbeats, structural preflight, one-origin-per-fill canonicalization, fold survivor fail-fast gates, and code-bound score identities.

The successful development run froze `histgb-core-v1` with freeze SHA-256 `38225498e910b9a1fa76093e043701b8cada4ed5e70fc40bc5aa890f914eec9d`. Canonical evidence is `research/programmes/003-natural-gas-trading-decision-system/phase2-market-only-baseline-v1.json`.

## Boundaries

Evidence ends no later than `2022-12-31`; 2023+ protected confirmation remained unopened. The result is development evidence only and makes no confirmatory edge claim. Later phases must compare against this frozen market-only baseline without changing its identity silently.
