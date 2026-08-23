# #193 — Volatility preregistration release audit

**Assessment date:** 2026-08-23
**Audit base:** `759b45b62f53f5f7e21d32a39f52ce937eaf2bb5`
**Audited contract commit:** `47d8c93ce7d364fe63fda94ef0671451f5fef82e`
**Audited contract SHA-256:** `f89a381dbe570c79573732a563b52ec1900a2f22b2f4a287d95de698d5db29fe`

## Decision

**PASS — release the consumed-history diagnostic only.**

The exact landed #191 preregistration is internally consistent and still matches the scientific
intent established by #147, the power discipline from #155/#149, and the untouched-confirmation
boundary in #137. No condition found in this audit requires changing the frozen design.

This release authorizes only the 204-row consumed-history diagnostic. It does **not** authorize the
504-row untouched confirmation, research promotion, model selection, or trading.

No model was fitted, no prediction was generated, no OOS metric was computed, and no confirmation
outcome was inspected during this audit.

## Exact identities

| Evidence | SHA-256 |
| --- | --- |
| `docs/development/volatility-preregistration/contract.json` | `f89a381dbe570c79573732a563b52ec1900a2f22b2f4a287d95de698d5db29fe` |
| `docs/development/volatility-preregistration/preregistration.md` | `a4eff3933b1290067a990081c3648285328a189d98f1980ecdfc208a6ce61073` |
| `src/commodity/roll_safe_market.py` | `d14fd50d8ce06ee1df82cbd420c2bb3b1918ed1a4eb1cfbd45984ec8fb063cd9` |
| `src/commodity/rolls.py` | `66873b7da806d2e001d41c44954358656c4b8d3efbd55d47eecf618b5a7ebe11` |
## Independent reconstruction

- Target: next-session **same-contract Garman–Klass realized variance**,
  `0.5*ln(H/L)^2 - (2*ln(2)-1)*ln(C/O)^2`, epsilon `1e-12`.
- Target contract: freeze the contract selected at prediction cutoff by the existing deterministic
  roll policy. Switching to the contract selected on the target day is prohibited.
- Primary loss: QLIKE, `y/h - log(y/h) - 1`; paired improvement is baseline minus challenger.
- Baseline: `same_contract_rv20_mean`, exactly 20 prior available same-contract GK variances;
  no shorter-window fallback.
- Challenger: `log_har_ols_v1`, OLS with intercept and exactly `log_rv_d1`, `log_rv_w5`,
  and `log_rv_m20`; no tuning, scaling, interaction search, or feature selection.
- Walk-forward: expanding, 252 initial training rows, refit every five scored rows, and only
  labels already available at the cutoff may enter training.
- Primary inference: 1,000 moving-block bootstrap resamples, 95% confidence, seed 0,
  40-session primary block, with 20/60-session sensitivities and one primary hypothesis.
- Materiality: at least 5% reduction in mean QLIKE versus the 20-session variance baseline.
- Robustness: positive mean paired QLIKE improvement in at least 2/3 chronological thirds and
  2/3 baseline-volatility regimes, with regime cut points learned only from the initial 252 rows.

## Diagnostic and confirmation boundaries

The diagnostic identity independently matches the Phase-D longitudinal ledger: 456 candidate rows,
252 initial training rows, 204 scored rows, with OOS from `2025-10-03T23:59:00+00:00` through
`2026-08-11T23:59:00+00:00`. Every candidate row must satisfy the new same-contract target and
20-history requirements; any failure stops execution before fit. The window is consumed history and
has **zero promotion authority**.

Untouched confirmation remains locked to the first 504 consecutive admissible prediction rows
strictly after `2026-08-11T23:59:00+00:00`. It still requires #137, promotion-eligible canonical
market evidence, and applicable project-use rights. No confirmation outcome may be inspected under
this release. #51 remains operator-deferred and is not modified by this audit.

The deterministic roll authority remains `volume_crossover_dte_v1`: two observed-session crossover
confirmations, prior-observed-session volume evidence, forced roll three days before expiry, strict
`>` crossover, fail-closed missing-volume behavior, and nearest-later eligible contract fallback.
The same-contract market boundary validates finite positive OHLC, valid OHLC ordering, and PIT-safe
availability before use. No cross-contract target substitution, imputation, or silent row dropping is
permitted.

## Exclusions and power reconstruction

The primary experiment still excludes weather, storage, positioning, power, LNG, production,
curve features, Kronos, HistGradientBoosting, Ridge tuning, alternative HAR lag search, and
post-result feature selection. Secondary outputs cannot rescue a failed primary result.

At the frozen 40-session planning block:
- `204 / 40 = 5.1` block-equivalent units; the one-primary standardized 80%-power MDE recomputes to
  `1.2405627861`, matching the frozen `1.2406`.
- `504 / 40 = 12.6` block-equivalent units; the corresponding MDE recomputes to `0.7892572224`,
  matching the frozen `0.7893`.

## Release

All #193 acceptance checks pass. The release identity below authorizes a successor execution slice
to run **only** the frozen 204-row consumed-history diagnostic. That successor must bind this audit,
the exact #191 contract hash, and the landed roll/input authority before fitting. Any identity or
coverage mismatch fails closed.

The 504-row confirmation, promotion, live/trading use, paid data acquisition, and any model/feature
search remain unauthorized.
