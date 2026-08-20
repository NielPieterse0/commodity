# V2 Executable Contract Freeze (#81)

## Scope

This slice is Agent 2's #81 lane only. It freezes the V2 executable experiment contract against the landed #78 longitudinal metrics/comparability authority. It does not execute #88 and does not perform model fitting, prediction generation, feature computation, new data acquisition, tuning, results-driven design, or empirical V2 execution.

## Gate state

1. #78 is closed/reconciled and landed in PR #95 at `3e2aa9117a82368782eb5c674eb33c62ef2fd9ee`.
2. #15 is closed/reconciled through PR #92 / `e11a891b58e67b61593b9c2ec5c86974e64cb0bc`.
3. #81 is now **frozen**, with executable candidate identities and common evaluation rules in `config/experiment_candidates.json` and `activation-contract.json`.
4. #88 remains **not executed / not passed**. Freezing #81 does not release #82 or #83 empirically.

## #78 binding

`activation-contract.json` references `contracts/research_metrics.schema.json` and `artifacts/research-metrics/longitudinal-ledger.json`. It inherits the exact #78 comparison kinds `previous_stage` and `best_comparable`, policy `strict-no-silent-regression-v1`, and all three required metrics: `model_rmse`, `baseline_rmse`, and `rmse_improvement_vs_baseline`.

The V2 contract does not replace those metric identities. It freezes how they are used for the V2 comparison and robustness gate.

## Frozen V1 control

The final governed Phase-D stage `phase-d-full-v1-hist-gb` supplies the comparable target, dataset/OOS, split/protocol, baseline, PIT-availability, and evidence context. Within that exact context, the zero-return naive baseline had lower RMSE than HistGB and Ridge, so `zero_return_naive` / `semantic:zero-return-naive-v1` is frozen as the strongest comparable V1 control.

The primary V2 claim therefore requires a challenger RMSE strictly below every required comparator, positive `rmse_improvement_vs_baseline`, and the inherited robustness/significance gate. #78 longitudinal stage comparisons remain mandatory in parallel.

## Frozen candidate identities

- `v2-82-kronos-only` — Kronos-only component control.
- `v2-83-indicators-only` — indicators-only component control; `I-ALL` is primary and `I-NO-*` variants are attribution-only.
- `v2-84-kronos-indicator-fusion` — fusion claim using both frozen component-control identities. #84 still owns its combination-rule implementation, but it may not redefine #81 target, metrics, comparators, seeds, leakage, cost, or stop rules.

Exact preparation/implementation revisions, source manifests, audit lineage, and release state are owned by `activation-contract.json` and `config/experiment_candidates.json`; this historical design note does not duplicate those mutable bindings. Each candidate has a deterministic artifact namespace. Any mutation of a frozen #81 field requires reopening #81 and a fresh independent successor activation audit.

## Frozen common rules

The contract freezes the Phase-D target/horizon/timestamp semantics, dataset/vintage/OOS identity, evaluation protocol/split, PIT cutoff, seed `0`, 1.0 required-row coverage, no post-cutoff inputs, fold-local fitted transforms only, zero paid data/provider expansion, CPU-only bounded compute, and no result-driven rescue search.

Uncertainty and robustness inherit the established V1 discipline: moving-block bootstrap with block size 20, 1000 resamples, 95% confidence, Benjamini-Hochberg multiplicity control at adjusted p-value <= 0.05, positive lower confidence bound, and positive evidence in at least two of three chronological periods and two of three frozen regimes.

## Execution boundary

Empirical authorization is owned by `activation-contract.json` and the candidate registry. The currently affected #83 path remains fail-closed until the independently governed successor audit recorded there passes the exact frozen preparation/implementation bindings and a separate explicit release change is landed.
