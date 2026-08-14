# V1 Research Completion — Phase 0 Review

Program: GitHub issue #15. Phase 0: #16. External review records: #22 and #23.

## Verdict

Phase 0 is closed. The complete merge gate is enforced by code/tests/evidence rather than documentation alone. Phase A may begin only from this exact verified head.

## Baseline and final verification

- Baseline head entering expanded remediation: `888d3d9a8fca2ee986bdd2bf56af00767b9ef617`.
- Baseline verification: 150 tests passed; Ruff passed.
- Final verification: **170 tests passed**.
- Ruff: passed.
- `git diff --check`: passed; Windows line-ending advisories only.
- Diff secret-pattern scan: 0 hits.
- Wheel smoke build: passed; authoritative root `config/*.json` files were packaged under `share/commodity-research/config`.
- Automated Codex review was attempted and failed with the existing `UnicodeEncodeError`.
- Independent NVIDIA review was attempted and failed with its backend error.
- Exact-diff manual code/architecture/statistical review therefore remained mandatory; no blocking or important finding survives.

## Part 1 closure — #1–#6 and #17

1. **#1 roll-policy ownership:** readiness no longer duplicates the owner policy. `config/assumptions.json` owns semantics; one executable parser validates them.
2. **#2 ignored roll semantics:** all registered `volume_crossover_dte_v1` semantics are required and unsupported values fail closed; tests cover missing/unsupported semantics.
3. **#3 canonical market disconnection:** canonical dataset mode now requires provider-neutral per-contract rows, passes the canonical readiness gate, derives the selected series, and rejects the bootstrap proxy as canonical evidence.
4. **#4 PIT grouping:** as-of joins support explicit `by` grouping and reject unresolved multi-series identity instead of silently cross-matching series.
5. **#5 reproducible environment:** CI and documented bootstrap install `requirements.lock.txt`, then install the project with `--no-deps`; the non-default-index local Torch marker was removed from the primary V1 lock.
6. **#6 installed config resolution:** config loading supports explicit `COMMODITY_CONFIG_DIR`, source-owner config, and installed distribution data without requiring `parents[2]/config` to exist.
7. **#17 viable walk-forward:** the preserved Massive snapshot contains 11,200 contract rows over 500 distinct sessions from 2024-08-14 through 2026-08-12. The owner experiment now uses 252 initial rows, while runtime still rejects any split that leaves no OOS period.

## Part 2 closure — A1, A2, A4, F1, H1, K1

- **A1 Databento governance:** the existing paid acquisition is explicitly `quarantined_pre_governance_acquisition`; no paid reacquisition is approved.
- **A2 Databento integrity:** evidence records actual cost `$39.65421365574002`, verified definition/OHLCV hashes, incomplete statistics integrity, completeness only through 2018-12-31, and continued prohibition on canonical/backtest promotion.
- **A4 statistical significance:** tournament comparisons use a deterministic moving-block bootstrap against the configured naive baseline, with paired RMSE improvement, confidence interval, centered two-sided null p-value, and conservative significance decision.
- **F1 experiment contract:** the real `run-tournament` CLI writes schema-v2 `experiment.json` for every tournament model. Integration tests validate naive, Ridge, and histogram-GB records against `contracts/experiment.schema.json`.
- **H1 leakage strength:** regression tests mutate multiple future-label suffixes and require all protected earlier forecasts to remain exactly invariant. Tournament execution also runs a full-path timestamp isolation audit before model comparison and records the result.
- **K1 LIVE approval:** `live_trading_allowed=true` alone is insufficient. LIVE additionally requires a complete explicit-human-approval record with approver, decision identifier, and timezone-aware timestamp. Repository defaults remain not approved, do not allow `live`, and deny model order authority.

## Evidence decisions

- Databento is not being reacquired in this program.
- Massive remains the configured canonical provider; its licensing/backtest gate remains closed where the owner config says it is closed.
- Phase 0 does not make a predictive-edge claim and does not authorize LIVE execution.
- Optional Kronos dependencies are outside the primary V1 environment lock and require their own reproducible environment before Phase C execution.

## Manual review closeout

The final manual exact-diff review specifically rechecked authority ownership, provider-neutral canonical flow, PIT grouping, experiment lineage, bootstrap inference, leakage enforcement, and execution safety. During that review the bootstrap p-value was strengthened to a centered two-sided null and an end-to-end CLI experiment-record test was added. Both changes were reverified before this closeout.
