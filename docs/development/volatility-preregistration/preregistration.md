# #191 — Next-session realized-variance preregistration

**Status:** frozen design; empirical execution not authorized by this slice
**Assessment date:** 2026-08-23
**Parent decision:** #147 target/horizon portfolio

## Decision

The first redesigned target will test **next-session realized variance**, not signed return.
It is intentionally a small market-only experiment. The purpose is to learn whether daily Henry Hub
volatility persistence is forecastable under the corrected same-contract/PIT rules before adding
weather, storage, positioning, LNG, power, Kronos, or other model complexity.

The primary challenger is one fixed log-HAR-style linear model. The primary comparator is one
20-session same-contract realized-variance mean. There is no hyperparameter search, feature
selection, ablation ladder, checkpoint search, or post-result rescue path.

No model is fitted and no new OOS outcome is inspected in #191.

## Prediction object and cutoff

For prediction row `t`, the target contract `c_t` is the contract selected by the repository's
existing deterministic roll policy using only information available at the cutoff. The cutoff is
the existing `after_current_daily_bar_close` timestamp, represented in UTC, with trading sessions
resolved by the `CME_NYMEX` calendar and `America/Chicago` session semantics.

The target contract is frozen at `t`. The target must never switch to whichever contract would be
selected on `t+1`.
## Primary target

The target is the next `CME_NYMEX` trading session's daily Garman–Klass realized variance for `c_t`:

`RV_GK = 0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2`.

`O`, `H`, `L`, and `C` are the raw per-contract daily OHLC values for `c_t` on its next trading
session. The target unit is squared log-return. QLIKE uses the numerical floor `epsilon = 1e-12`:
`y = max(RV_GK, epsilon)`. The floor exists only to define logarithms and ratios; it must not be used
to discard or rank observations.

A scored row is admissible only if the same target contract has exactly one valid next-session raw
OHLC bar, with finite positive prices and valid OHLC ordering. If the bar is absent because of expiry,
source coverage, or any other reason, execution fails closed. Cross-contract substitution, synthetic
OHLC, row dropping, or target imputation is prohibited.

The target becomes knowable only when that next-session raw daily bar is itself available. It is
therefore prohibited from every feature calculation at prediction time `t`.

## Primary loss and baseline

Primary loss is QLIKE:

`QLIKE(y, h) = y/h - log(y/h) - 1`, with both `y` and forecast `h` floored at `1e-12`.

The sole primary comparator is `same_contract_rv20_mean`: the arithmetic mean of the 20 most recent
valid Garman–Klass variance observations for `c_t` that are available at the cutoff. A row requires
all 20 observations. No shorter-window fallback is allowed.
## Primary challenger

The challenger is a fixed log-HAR-style ordinary least-squares model with an intercept and exactly
three predictors, all computed from `c_t` history available at the cutoff:

1. `log_rv_d1 = log(max(RV_GK_t, epsilon))`.
2. `log_rv_w5 = log(max(mean(RV_GK_t ... RV_GK_t-4), epsilon))`.
3. `log_rv_m20 = log(max(mean(RV_GK_t ... RV_GK_t-19), epsilon))`.

The fitted response is `log(max(RV_GK_t+1, epsilon))`. The variance forecast is `exp(predicted_log_rv)`
with the same numerical floor. There are no penalties, nonlinear transforms beyond those stated,
interaction terms, weekday/event dummies, exogenous variables, or additional lag choices.

Training uses expanding walk-forward history with 252 initial admissible rows and refits every five
new scored rows. Each refit may use only labels whose target bar is already available. Feature
standardization is prohibited because this OLS specification does not require it.

## Frozen exclusions

Weather revisions, storage surprises, positioning, power, LNG, production, curve features, Kronos,
HistGradientBoosting, Ridge tuning, alternative HAR lag windows, and feature selection are excluded.
They require separately preregistered successor hypotheses. A negative result here cannot activate
one of those alternatives automatically.

Squared settlement return and absolute settlement return may be reported later only as explicitly
labelled target sensitivities. They are not members of the primary family and cannot rescue a failed
Garman–Klass/QLIKE result.
## Diagnostic split

The first execution, if separately authorized, is diagnostic only and reuses the exact consumed
Phase-D row identity. Its candidate dataset has 456 prediction timestamps: 252 initial training rows
followed by exactly 204 scored timestamps from `2025-10-03T23:59:00+00:00` through
`2026-08-11T23:59:00+00:00`.

All 456 candidate timestamps must satisfy the new same-contract target and 20-history requirements.
Any failure stops the diagnostic before fitting; rows must not be silently dropped. This diagnostic
may answer whether the redesign looks technically/economically interesting, but it has **zero
promotion authority** because the dates were already consumed during V1/V2 development.

## Untouched confirmation

Promotion requires #137 and a separate execution release. The untouched confirmation set is the
first **504 consecutive admissible prediction rows strictly after `2026-08-11T23:59:00+00:00`**.
The model, target, baseline, feature surface, and evaluation rules above are frozen before any of
those confirmation outcomes may be scored or summarized. No interim confirmation metric inspection
is permitted.

Confirmation additionally requires promotion-eligible canonical market evidence and cleared
project-use rights. The currently quarantined deeper Databento acquisition cannot satisfy this gate
while #51 remains operator-deferred. Evaluation-only evidence can support the consumed-history
diagnostic, not promotion.

An alternative historical holdout may not be substituted for the 504-row future confirmation under
this contract. Such a change requires a new preregistration before its outcomes are inspected.
## Inference, robustness, and materiality

The primary comparison is paired row-level QLIKE improvement:
`delta = QLIKE_baseline - QLIKE_challenger`; positive values favor the challenger.

Inference uses a moving-block bootstrap with 1,000 resamples, 95% confidence, seed 0, and a primary
block size of **40 sessions** because volatility persistence can exceed the return-target dependence
scale. Block-size sensitivities are 20 and 60 sessions. There is one primary hypothesis, so BH is not
needed. The primary p-value threshold is 0.05.

A robust positive diagnostic/confirmation additionally requires positive mean QLIKE improvement in
at least two of three chronological thirds and at least two of three volatility regimes. Volatility
regimes are defined by tertiles of the **baseline forecast** using cut points learned from the initial
252 training rows; regime assignment is therefore knowable at prediction time.

The prespecified material-effect threshold is a **5% reduction in mean QLIKE** relative to the
20-session variance baseline. This threshold is a forecast-quality gate, not a trading-return claim.
No Sharpe, PnL, direction accuracy, or transaction-cost result can substitute for it.

Secondary descriptive outputs are RMSE of `sqrt(RV_GK)` and the last-observation variance baseline.
They carry no promotion authority and are outside the primary hypothesis family.

## Power gate

At a 40-session planning block, 204 diagnostic rows provide about 5.1 block-equivalent units and an
80%-power standardized MDE of about **1.24 SD** for one primary test. The 504-row confirmation has
about 12.6 block-equivalent units and a standardized MDE of about **0.79 SD**.
Before confirmation outcomes are opened, the consumed-history diagnostic may be used once to estimate
the paired QLIKE-loss scale for **power planning only**. Using that frozen pre-confirmation scale, the
execution child must calculate the absolute and relative 80%-power MDE for 504 rows. If the relative
MDE exceeds the 5% materiality threshold, confirmation remains locked and a new preregistration must
set a larger sample before any confirmation outcome is inspected. The 504-row window must not be
peeked at and then extended.

This rule follows #155: detectability controls whether evidence should be consumed; it is not evidence
that an edge exists. #149's deeper-history scenarios remain planning evidence only.

## Stop rules

Execution stops before fitting if any candidate diagnostic row is missing its target, its 20-session
same-contract history, or a required raw availability identity. It also stops if the source/roll
semantics differ from the corrected same-contract authority or if any cross-contract target is formed.

A primary result fails if mean QLIKE improvement is non-positive, its 95% CI lower bound is not
positive, `p > 0.05`, the 5% materiality threshold is missed, or the 2-of-3 period and 2-of-3 regime
requirements fail. No secondary metric or sensitivity can reverse that disposition.

Compute is CPU-only. The design has no paid acquisition step, no GPU requirement, and no model-search
budget. The expected implementation/evaluation budget is bounded to the fixed OLS walk-forward and
bootstrap described above.

Volatility forecasting is not itself a trading strategy. Any options/futures volatility-trading,
position sizing, or execution claim needs a separate preregistration with instrument, costs, and risk
semantics. This slice grants no trading authority.
## Activation gates and lineage

#191 may be reviewed and landed as design evidence while #147 is tooling-held. Empirical execution
must not begin until this exact preregistration is independently reviewed and separately released.
The execution release must also preserve the current #147 scientific decision or wait for #147's
KIS merge gate to be repaired; it may not treat the tooling hold as permission to alter the design.

Diagnostic execution may use the frozen Phase-D evaluation-only market evidence because it has no
promotion authority. Untouched confirmation requires #137 plus canonical/promotion-eligible market
evidence and applicable licensing authority. #51 remains untouched until explicit operator request.

## Evidence used to freeze this design

- GitHub issue #147 / PR #190 — reviewed target/horizon decision ranking volatility first; PR is tooling-held.
- `docs/development/effective-n-detectable-effect/analysis.md` — dependence and MDE discipline.
- `docs/development/v2-model-criticism/review.md` — signed-return redesign and target-native loss rule.
- `docs/development/v1-research-completion/phase-d-closeout.json` — prior shared volatility diagnostic.
- `config/phase_d_evaluation.json` — inherited walk-forward and robustness conventions.
- `src/commodity/roll_safe_market.py` — corrected same-contract/PIT boundary.
- `artifacts/research-metrics/longitudinal-ledger.json` — exact consumed Phase-D OOS identity.

The frozen design deliberately does **not** adopt the historical broad `ng-volatility-direction-v1`
feature-family candidate as the first test. Exogenous surprise/revision families remain valuable
successors, but first this experiment isolates the simpler volatility-persistence question.
