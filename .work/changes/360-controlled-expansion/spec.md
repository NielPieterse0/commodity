# Change Specification: Phase 6 Controlled Expansion

- **Change ID**: `360-controlled-expansion`
- **Status**: Implemented; verification pending
- **Authority**: GitHub #360; `phase5-stacking-policy-v1.json`; committed Phase-6 preregistration
- **Complexity**: large

## Outcome

Test exactly one Phase-6 mechanism before any broader data expansion: whether annual policy refitting resolves the instability observed under the frozen Phase-5 two-year cadence.

## Scientific contract

- Use only Phase-5 research-OOS policy/year scores through 2022.
- Preserve the Phase-5 policy grid, selection function, costs, risk budget and target horizon.
- Re-select once per calendar year using only earlier OOS yearly scores.
- Compare against the reproduced two-year Phase-5 nested path.
- Advance annual cadence only if every preregistered dominance gate passes.
- Do not access 2023+ confirmation, add global-gas inputs, refit specialists, expand thresholds, or choose metrics post hoc.

## Result

Annual refit improved standard net P&L from $13,980 to $17,160, median yearly P&L from -$2,305 to -$715, preserved the -$6,145 worst year, and reduced transaction cost from $4,530 to $3,540. It failed the drawdown gate: maximum yearly drawdown rose from 6.236% to 8.222%. Therefore annual refit is rejected and the frozen Phase-5 cadence remains authoritative.

## Acceptance

1. Comparator reproduction equals the frozen $13,980 Phase-5 standard replay.
2. 2023+ evidence remains inaccessible.
3. The preregistered decision rule is applied without post-hoc relaxation.
4. Result and input identities are durable and reproducible.
