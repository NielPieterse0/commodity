# Spec: Phase 3 PIT Physical-Balance Contribution

## Upstream scientific authority

- GitHub issue #357, L3 freeze comment `5626442162`.
- Frozen comparator: Phase-2 `histgb-core-v1`, freeze SHA-256 `38225498e910b9a1fa76093e043701b8cada4ed5e70fc40bc5aa890f914eec9d`.
- Development evidence only through 2022-12-31; protected confirmation remains unopened.

## Science-to-code mapping

- `config/phase3_fundamentals.json` binds the three BHLR predictor member hashes, PIT availability rule, frozen comparator identity, model parameters, outer blocks and survival rule.
- `src/commodity/fundamentals_phase3.py` reads only production, working-storage and total-consumption predictor matrices; verifies hashes; extracts source-vintage diagonals; logs positive values; and performs strict PIT as-of joins.
- `src/commodity/phase3_runtime.py` replays the exact frozen Phase-2 baseline, fails on identity/P&L drift, scores the all-three-feature challenger without tuning, runs remove-one diagnostics, applies the predeclared disposition rule and records source/input identities.
- `src/commodity/cli.py` exposes the bounded `phase3-fundamentals` workflow.
- `research/programmes/003-natural-gas-trading-decision-system/phase3-pit-fundamentals-v1.json` is the canonical development result.

## Non-negotiable boundaries

No BHLR Henry Hub outcome matrix, 2023+ market outcome, post-outcome tuning, risk/cost/horizon change, synthetic fill, or alternate physical source is permitted in this change.