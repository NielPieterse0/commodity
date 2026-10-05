# Change Specification: V2.38 Adverse Path Add Guard

- **Change ID**: `470-v238-adverse-path-add-guard`
- **Status**: Active
- **Complexity**: medium
- **Authority**: GitHub issue #470 / `WORK-470`

## Outcome

Block only an increase in absolute exposure on an already-open same-side V3 position when the matured current-position-instance `economic_path_pnl_fraction < 0`.

## Requirements

- Preserve hard-risk reductions and exits, ordinary reductions, holds, starter entries, and reversals.
- Use only current-instance economic-path evidence already matured strictly before decision time.
- Never allow prior-position-instance evidence or `outcome_available_at == decision_time` to gate a decision.
- Record an explicit lifecycle/reason code when an otherwise-valid add is blocked.
- Preserve #468 replay-engine semantics and optimizations.

## Acceptance criteria

- Focused lifecycle/PIT/future-invariance tests pass.
- Exact six-month 96 x 3 replay preserves October/November behavior and removes the adverse December scale-up.
- Base and execution-stress outcomes meet the #470 diagnostic expectations unless an implementation difference is explicitly explained.
- Full future-invariance remains PASS and independent review finds no leakage or hidden fitting.
- After the development block passes, freeze this controller rule and move next to the untouched six-month block.
