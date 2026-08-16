# #83 V2 Indicator / Surprise Challenger — Preparation Specification

**Issue:** `NielPieterse0/commodity#83`

**Parent:** `#80`

**Dependency:** `#81`

**Empirical release gate:** `#88`

**Preparation base:** `e11a891b58e67b61593b9c2ec5c86974e64cb0bc`

**Status:** preparation only; non-executable while `#15` remains open

## Scope and authority

This document freezes the Agent 5 preparation surface only: information families, PIT rules, deterministic transformations, missingness policy, family ablations, exclusions, and the existing-data inventory needed to review the proposal.

It does **not** activate a V2 candidate. `#81` owns the executable experiment identity, exact V1 comparator, metric identities, split/fold identity, seed semantics, significance/materiality rules, compute cap, and artifact namespace. `#88` independently decides whether empirical execution may begin.

No model fitting, prediction generation, feature execution, new acquisition, tuning, threshold search, or result inspection is authorized by this document.

## Candidate principle

The #83 challenger is a compact, hypothesis-led **indicators-only** component. It inherits the strongest comparable V1 feature/control basis selected by `#81`; inherited V1 variables are controls, not relabeled V2 discoveries. The only V2 increments are the predeclared transforms below.

## Global point-in-time contract

1. Every time-varying input must retain distinct `observed_for`, `issued_at`/publication time when applicable, `available_at`, source identity/vintage, and revision state.
2. A feature row is admissible only when every underlying datum satisfies `available_at <= prediction_time` under the evidence tier frozen by `#81`.
3. Final/revised history must never replace the state knowable at the cutoff. Unknown publication/vintage state fails closed.
4. As-of carry-forward is allowed only when the source contract explicitly permits state persistence and its configured staleness bound is not exceeded.
5. Forecast revision means a change between two actually issued forecasts for the **same valid-time window**. A shifted forecast window must not be mislabeled as revision.
6. A feature may be called `surprise` only when both expectation and realization have independently defensible historical PIT identities. Otherwise use level/change/revision terminology.
7. Any scaler or normalization requiring fitted parameters is fit inside each training fold only. No whole-sample fit is permitted.
8. No clipping, winsorization, target encoding, learned imputation, or data-dependent transform threshold is allowed in the initial #83 candidate.
9. Transformation code/config identity must be hashed and recorded in the eventual #78 longitudinal-metrics record.

## Missingness and coverage

- After `#81` freezes the dataset and split identities, required #83 feature columns must achieve **1.000 coverage on every row consumed by model fitting or scoring**, not only evaluation rows.
- Pre-fit context rows may exist solely to form predeclared lag/revision transforms. They are never fitted or scored, and they may extend only far enough to obtain the immediately preceding eligible source state/run/report/session required by this specification.
- No training or evaluation row may be dropped to rescue a family. Models with native missing-value handling do not relax this rule.
- Zero/mean/median/model-based imputation is prohibited. Any required feature missing on a fit/scored row invalidates the candidate before fitting.
- Carry-forward and staleness are governed by `config/data_sources.json` at preparation SHA-256 `179e53ff12a5a0a42b4276dd8baef65209c558f896dd15c08b166e18506b35fd`; this document does not independently own those numeric limits.
- Declared weather archive gaps may use only the latest complete actually-issued forecast permitted by that pinned source contract; no reanalysis or later run may backfill the cutoff.
- If a required family cannot meet the coverage rule without violating PIT/staleness rules, the candidate is invalid before fitting. It is not silently weakened.

## Family W — issued weather level and revision

**Mechanism:** weather expectations alter heating/cooling demand expectations; changes in the expected demand-weighted weather path may carry incremental information beyond a single forecast level.

**Inherited controls:** the existing four-anchor ECMWF-IFS issued-run features, including 7-day temperature, HDD65, CDD65, humidity, precipitation, wind, and anchor aggregates.

**V2 increments:**
- `weather_hdd65_revision_1run`: current eligible run HDD65 minus the immediately preceding eligible run HDD65, both recomputed over the current run's exact `[+24h,+192h)` valid-time window.
- `weather_cdd65_revision_1run`: same-valid-window CDD65 revision using the same two issued runs.
- Per-anchor revisions are not admitted initially; the revision pair uses the existing unweighted four-anchor aggregation to avoid geographic search.

**PIT rule:** both runs must be immutable issued forecasts and each must have `available_at <= prediction_time`. For each prediction cutoff, the current run is the eligible configured-cycle run with greatest `issued_at`; the prior run is the eligible configured-cycle run with greatest `issued_at` strictly below the current run. Duplicate/tied `issued_at` identities fail closed. The prior run must contain every hourly valid time in the current run's exact `[+24h,+192h)` window; otherwise the revision features are missing and the candidate is invalid under the coverage rule.

**Exclusion:** no realized-weather `surprise` is admitted initially because the repository has no governed historical realization/expectation pair satisfying this contract. Reanalysis is forbidden as a substitute.

## Family S — storage state/change dynamics

**Mechanism:** inventory level and the direction/acceleration of weekly balance changes encode supply-demand tightness.

**Inherited controls:** `storage_lower48_bcf`, `storage_weekly_change_bcf` from the WNGSR point-in-time event stream.

**V2 increment:** `storage_change_accel_bcf = current_weekly_change_bcf - prior_public_weekly_change_bcf`, using three distinct observed storage weeks and only values public by the prediction cutoff.

**PIT rule:** original releases and published revisions remain chronological state events. A later revision changes a week's public value only from its own `available_at` onward. At each prediction cutoff, reconstruct the public storage state by `observed_for`: for each storage week, use the latest eligible release/revision value available by that cutoff. Order those **distinct `observed_for` weeks** chronologically. Let `W0` be the latest eligible week, `W1` the immediately preceding week, and `W2` the week before `W1`; then `current_weekly_change_bcf = value(W0) - value(W1)` and `prior_public_weekly_change_bcf = value(W1) - value(W2)`. `storage_change_accel_bcf` is their difference. Revisions therefore update the as-of-cutoff values for their week but can never become a same-week predecessor. Duplicate/ambiguous eligible values for one week, non-monotone week identity, or absence of `W0/W1/W2` fails closed.

**Exclusion:** `storage_surprise` is not admitted. No historically PIT-admissible market-consensus/expectation series is present locally, so actual-minus-consensus would be mislabeled or future-informed.

## Family C — futures curve / roll state

**Mechanism:** front-curve shape and its movement reflect scarcity, carry, seasonality, and roll pressure not represented by a single continuous price path.

**Inherited controls:** M1-M4 settles/volumes/DTE, M1-M2/M2-M3/M3-M4 spreads, M1-M4 slope, and M1/M2 volume ratio from the provider-neutral market-structure builder.

**V2 increments:**
- `curve_curvature_123 = curve_spread_m1_m2 - curve_spread_m2_m3`.
- `curve_spread_m1_m2_change_1 = current curve_spread_m1_m2 - prior-session curve_spread_m1_m2`.
- `curve_slope_m1_m4_change_1 = current curve_slope_m1_m4 - prior-session curve_slope_m1_m4`.

**PIT rule:** all contracts contributing to the curve must satisfy the frozen market availability cutoff. `prior-session` means the immediately preceding available `trade_date` in the frozen V1 `CME_NYMEX` market-session sequence under the existing provider-neutral market contract; weekends/holidays therefore do not synthesize rows. No forward-fill across a missing expected market session is permitted, and a missing prior-session value fails closed. Cross-contract returns remain forbidden. Roll state is represented continuously by existing DTE/volume information; no optimized roll-proximity threshold is introduced.

**Boundary:** use only the market source/evidence identity allowed by `#81`. Databento adoption/value testing remains `#51`, not #83.

## Family V — volatility persistence / calendar seasonality

**Mechanism:** short-vs-medium volatility state can encode persistence/regime changes while deterministic calendar phase captures recurring gas seasonality.

**Inherited controls:** `ret_1`, `ret_5`, `range_pct`, `vol_5`, `vol_20`, `ma_gap_5`, `ma_gap_20`, `season_sin`, `season_cos`.

**V2 increment:** `vol_ratio_5_20 = vol_5 / vol_20`; a zero/non-finite denominator is missing and therefore subject to the global fail-closed coverage rule.

No additional technical-indicator library, regime threshold, event bucket, or alternative seasonality encoding is admitted in the initial candidate.

## Family P — CFTC positioning

**Mechanism:** participant positioning may proxy speculative crowding and producer/merchant hedging pressure.

**Inherited controls:** open interest, category net positions, and Managed Money long/short percent of OI from the Disaggregated Futures Only Henry Hub series (`023651`).

**V2 increments:**
- `managed_money_net_pct_oi = managed_money_long_pct_oi - managed_money_short_pct_oi`.
- `managed_money_net_pct_oi_change_1report = current managed_money_net_pct_oi - prior public report value`.

**PIT rule:** report-as-of date is never treated as publication time. Use only point-in-time report rows permitted by the pinned conservative/scheduled/special release-availability contract and its staleness rule. For each prediction cutoff, the current positioning state is the eligible distinct report with greatest `available_at`; the prior state is the eligible distinct report with greatest `available_at` strictly below it. `observed_for` remains the report identity and must differ between current and prior. Published special/delayed releases enter this same public-availability ordering; they are not backdated to report-as-of. Duplicate/tied `available_at` identities, non-point-in-time revision status, or an absent eligible predecessor fail closed under the global coverage rule.

## Family L — issued power/load expectation

**Mechanism:** next-day power demand expectations proxy gas-fired power demand pressure.

**Inherited controls:** NYISO next-day load mean/max/min from archived P-7 issued forecasts.

**V2 increments:**
- `power_next_day_load_range_mw = max_mw - min_mw`.
- `power_next_day_load_mean_change_1run_mw = current issued mean - prior eligible issued mean`.

**PIT rule:** only immutable archived P-7 vintages permitted by the pinned source contract are eligible. For each prediction cutoff, the current row is the eligible P-7 row with greatest `issued_at`; the prior row is the eligible row with greatest `issued_at` strictly below it. Duplicate/tied `issued_at` identities fail closed. `power_next_day_load_mean_change_1run_mw` is explicitly a **shifted-valid-day issued-level change**, not a forecast revision or surprise: the two `forecast_valid_at` local dates must be consecutive NYISO calendar days. If that alignment is absent, the feature is missing and the candidate fails the global coverage rule. Current/revised EIA-930 history cannot be used as a historical realized-load surprise.

## Predeclared ablation matrix

The empirical implementation must produce one aggregate #83 challenger plus fixed family attribution. Model, split, metrics, seeds, and evaluation rows remain identical across these records. **`I-ALL` is the sole primary #83 challenger. Every `I-NO-*` record is attribution-only and is ineligible to rescue, replace, redefine, or promote #83 if `I-ALL` is null, negative, invalid, or non-comparable.**

1. `I-ALL`: inherited V1 control basis plus **all six required** #83 increment families W/S/C/V/P/L. No family is optional within the primary challenger.
2. `I-NO-W`: `I-ALL` without weather-revision increments.
3. `I-NO-S`: `I-ALL` without storage-dynamics increment.
4. `I-NO-C`: `I-ALL` without curve/roll increments.
5. `I-NO-V`: `I-ALL` without volatility-persistence increment.
6. `I-NO-P`: `I-ALL` without positioning increments.
7. `I-NO-L`: `I-ALL` without power/load increments.

No single-feature fishing, family redefinition, threshold revision, or extra ablation may be added after #83 results are inspected. If any W/S/C/V/P/L constituent fails PIT or coverage validation, `I-ALL` is invalid and **no reduced aggregate is fitted or scored**. The failed-family state may be recorded diagnostically, but it is not an ablation result and cannot release any `I-NO-*` run as a substitute primary candidate.

## Fixed exclusions

- Kronos features or latent representations: owned by `#82` and later fusion work.
- Storage consensus surprise without an independently verified historical expectation vintage.
- Reanalysis-as-forecast, future weather observations, or revised-current weather substitutes.
- EIA current-state production/consumption/trade/spot history until historical publication/revision vintages are governed.
- EIA-930 historical actual/forecast rows as strict PIT evidence while revision history remains incomplete.
- New geography, new weather anchors, demand-weight optimization, or spatial feature search.
- Databento-derived challenger features/adoption decision, paid-provider expansion, and any new acquisition.
- Broad indicator libraries, alternate targets/horizons, post-hoc regimes/events, learned feature selection, and hyperparameter search.
- Any variable whose mechanism, source identity, availability rule, or deterministic transform cannot be frozen before execution.

## Activation handoff

Before any #83 feature generation or empirical run:

- `#15` must be closed and reconciled.
- Agent 2 must freeze `#81`, including exact comparator, dataset/vintage, split, metric/materiality, seed, multiplicity, stop, compute, and artifact identities.
- Agent 3 must execute `#88` and explicitly pass #83 for empirical release.
- The #83 implementation must bind this specification by immutable revision and reject unlisted features/transforms.
- PIT/coverage validation must run before fitting; failure stops the candidate rather than changing the contract.
- #78 longitudinal metric/comparability recording is mandatory for the aggregate challenger and all required comparisons.

## Null result and stop rule

No incremental value is an accepted outcome. A negative, null, non-comparable, or PIT-invalid result ends this bounded candidate under its frozen contract; it does not authorize replacement features, looser missingness, alternate windows, thresholds, models, or data acquisition inside #83.

## Preparation evidence

The companion `data-inventory.json` records only existing local source/manifests and eligibility constraints. No prediction, model metric, target-conditioned statistic, feature importance, or V2 feature value was computed during preparation.
