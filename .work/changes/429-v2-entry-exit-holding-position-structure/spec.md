# Change Specification: V2.32 Execution Structure Optimization

- **Change ID**: `429-v2-entry-exit-holding-position-structure`
- **Status**: Research complete; landing pending
- **Complexity**: large
- **Authority**: GitHub issue #429 under Programme #393, inheriting the promoted development-only #459 policy.

## Outcome

Identify which components carry the #459 development advantage, then improve realizable economics by changing only entry, exit, holding, cadence, reversal/re-entry, and bounded overlap semantics.

## Fixed parent

The control is exactly `both__strength_q50__f1.00__loss_cooldown_3_sessions__short_none__long_veto` from #459 Wave 2 v2. Its model, target, safety, costs, specialist inputs, and development boundary remain inherited unless an ablation explicitly removes one component.

## Contribution ablations

Run matched removals before lifecycle optimization: long specialist veto, strength gate, loss cooldown, all three retained TA decision-context signals, positioning decision context, and the two volatility-tail decision-context signals. Code inspection before scoring confirms #428 feeds the forecast models only their inherited control columns; these retained signals are attached for decision-state/fusion logic. Context-family ablations therefore keep forecasts and origin rows fixed and recompute only the declared decision context.

## Execution search

Search bounded variants of abstain persistence, same-direction refresh, opposite-signal reversal versus exit-only, one-session entry delay, fixed maximum holds of 1/3/5 sessions, and one-signal-per-target-window cadence. Preserve a single bounded net NG position; independent multi-lot stacking, leverage, and exposure scaling remain #430 scope.

## Evidence and chronology

- Development observations end at `2022-12-31`; protected 2023+ confirmation, paper, SIM, and LIVE remain unread.
- Every signal used to change a position must already be available at that decision timestamp.
- Fixed-hold and delayed-entry rules use only the frozen session calendar; they do not inspect future returns.
- Transaction costs, roll costs, position persistence, drawdown kills, and daily-loss controls are scored through the existing bounded fractional replay ledger.
- All attempted configurations are ledgered at base, 1.5x, and 2x inherited cost profiles across the 2019-2020 and 2021-2022 development outers.

## Event-time boundary

#448 held scheduled-event timing because no proven historical 2010-2022 WNGSR release calendar exists. #429 therefore records the event-time lane as `HOLD_SOURCE_TIMING_NOT_PROVEN` and does not synthesize event timestamps.

## Acceptance

1. Reproduce the promoted #459 control economics under the same source identities before crediting #429 results.
2. Quantify matched removal effects for each declared parent component, including TA as decision-context contribution while keeping the inherited forecast model and forecast outputs fixed.
3. Evaluate the complete preregistered lifecycle grid with exact trial accounting, monthly net return, turnover, costs, drawdown, concentration, and effective sample diagnostics.
4. Promote an execution variant only if it improves mean base-cost monthly net return over the #459 control, is nonnegative versus control in both outers, remains nonnegative at higher costs, does not regress kill triggers, and passes inherited effective-sample/concentration controls.
5. Preserve exact provenance and deterministic hashes for preregistration, preflight, trial ledger, and result.
