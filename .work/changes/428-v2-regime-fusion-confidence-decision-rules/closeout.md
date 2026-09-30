# Closeout: V2 Regime Fusion Confidence Decision Rules

## Implemented scope

- Reconciled #427 landing evidence into the #428 record.
- Added prior-only regime/state thresholds, persistence, favored-signal fusion, explicit TRADE/ABSTAIN gates, chronological calibrated meta-confidence, model disagreement, and prior-only policy selection.
- Added a source-bound no-scoring preflight, 29-config core lane, 3-config conditional OI lane, matched replay, cost/risk/effective-sample diagnostics, confidence calibration, outer stability, remove-one-input ablations, and complete trial accounting.
- Corrected OI plumbing so conditional OI context cannot shorten or otherwise change inherited forecast-model training history.
- Corrected policy-history chronology so every score-year, outer, and OI training set requires `target_end_timestamp` strictly before the scoring boundary; fill date alone is insufficient.
- Enforced outcome-availability boundaries inside every outcome-dependent fitter, kept equal-time calibration rows on the calibration side, and excluded training labels whose outcomes were not observable by the calibration boundary.
- Corrected effective-sample accounting so selected trades and active months are counted from risk/margin-executed replay-ledger positions rather than requested/admitted signals.
- Froze the exact 29-config parameter identity, fail-closed on missing retained-signal values, rejected protected 2023+ target outcomes, and excluded non-finite policy-ranking metrics.

## Implementation evidence

- Focused decision tests: 23 passed.
- Ruff and compile checks: clean on #428 runner/module/tests.
- Final hardened source-bound no-scoring preflight: PASS; 3,088 feature rows; 3,897 session rows; zero failures; `preflight_sha256=5e6594debec71103c650ba928f0a900b24936bd903c76ae80b721a18f6552119`.
- Frozen preregistration SHA-256: `a81ef8912634be233ea3d8c3227c0e9e0e0a364af78417fb72663e87338cbe0c`.
- Runner SHA-256: `bf0904183ef42105c0263d4995b101c756a427ad1549840725eae1ff23260d9a`.
- Decision module SHA-256: `e0702fdcea3d0dcef16ef454bdfb0cff591f1bb61772c8579e9d65768585e224`.
- Final hardened empirical result SHA-256: `718b79625d36318b9e4462e96b5421271a50aa69340833e7b76e8823e5663894`; 143 trial-ledger rows; trial ledger SHA-256 `2a780122be4fab6df4a5891dc29c749554be5759c20cb815b34468435a0d6cf1`.

## Research return

- Main promotion disposition: `HOLD_NO_ROBUST_CONDITIONAL_GAIN`.
- Outer-2019-2020 selected the baseline; no conditional rule improved the preregistered selection objective. The replay ledger shows 117 risk-executed selected trades across 12 months, so this outer passes the frozen effective-sample gate.
- Outer-2021-2022 selected `meta-interactions-p60` from prior 2019-2020 evidence and produced a +0.0005542 mean monthly net-return delta versus the matched baseline, but only 1 selected trade was risk-executed in 1 month, so this outer fails the frozen effective-sample gate.
- Main mean outer monthly-return delta: +0.0002771; nonnegative outer fraction: 1.0; effective-sample gate failed; no kill-trigger regression; promotion therefore remains false without changing any frozen research parameter.
- OI diagnostic remains non-promotable. `meta_interactions_oi_p055` produced positive matched-baseline deltas in both eligible development blocks (+0.0033923 in outer-2020-oi and +0.0006208 in outer-2021-2022), but only 19 risk-executed trades across 5 months and 5 across 2 months respectively survive. `oi_favored_state_gate` passes effective-sample controls in both blocks but turns negative in outer-2021-2022, so uniform OI value remains disallowed.
- Protected 2023+ confirmation, true-forward, paper, SIM, and LIVE evidence remained untouched.

## Review / landing evidence

- Source revision/tree: pending final commit.
- Full repository verification: PASS; `scripts/verify.ps1` completed with 943 passed / 7 skipped and all registered governance/data/documentation checks passing.
- Reusable decision module + regression tests review: exact staged fingerprint `c664d6494ed9f4a7ed9ca51f1a7363de4003d14a42fd48e87cf21bd3869a0bb4`; bounded reviewer completed with zero findings.
- Runner review: KIS projector declared `manual_fallback=exact-diff` for staged fingerprint `2009fcd8910bda765e4bbd17028b27f78ef749b4327c95c171fd396a6e2921b6`; exact-diff checks passed, all five outcome-dependent fitter calls carry `outcome_available_before`, effective-sample accounting is bound to replay-ledger `target_position`, and `git diff --cached --check` passed.
- Pull request exact head / provider-native CI / merge: pending.
- Work reconciliation and cleanup: pending.

## Residual items

- Continue to #429 only from this governed HOLD result after #428 verification/landing; do not retune #428 thresholds from observed outer outcomes.
