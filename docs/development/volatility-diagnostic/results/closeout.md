# #195 — Volatility diagnostic closeout

## Decision

The frozen consumed-history diagnostic **passes its preregistered primary forecast-quality gates**, but it does **not** authorize research promotion or confirmation execution.

The fixed log-HAR challenger reduced mean QLIKE by 15.55% versus the 20-session same-contract realized-variance baseline. The primary 40-session moving-block bootstrap remained positive with a 95% CI of 0.02275 to 0.07347 and two-sided p=0.002997. All three chronological periods and all three baseline-volatility regimes had positive mean QLIKE improvement.

The separate preregistered confirmation power gate fails. Using the consumed-history paired-loss scale, the planned 504-row confirmation has an estimated 80%-power relative MDE of 59.20%, well above the frozen 5% materiality threshold. The 504-row confirmation therefore remains locked and must not be opened.

## Authoritative evidence

Machine-readable result authority is:

- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/summary.json`
- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/predictions.csv`
- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/coverage.json`
- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/run-manifest.json`

The longitudinal research projection is `artifacts/research-metrics/longitudinal-ledger.json`.

## Execution provenance

The evaluator was committed before any real diagnostic metric was opened. The execution revision is `31d733eaa171573ad14da0cc68da1da38f1b33fa`.

The frozen coverage gate reconstructed all 456 candidate rows, with 252 initial training rows and exactly 204 scored rows. All candidates mapped to the selected contract, 24 contracts were represented, minimum same-contract history was 21 bars against a 20-bar requirement, and no target was missing, imputed, dropped, or substituted across contracts.

The diagnostic used the exact #191 contract and #193 release identities, frozen Phase-D dataset SHA `0c0a39b...`, and canonical market SHA `83faf07a...`. No tuning, feature selection, exogenous rescue, Kronos/HistGB rescue, paid acquisition, or post-result model change occurred.

A second execution of the same evaluator commit, data, and protocol produced byte-identical `predictions.csv` and `summary.json` outputs. Reproducibility is therefore recorded as passed.

## Research consequence

This is the first redesigned target in the current programme to show a material positive diagnostic result under its frozen primary loss and robustness rules. It is still consumed-history evidence, so it does not establish a promotable forecasting edge.

The next scientific step is a new preregistration that sizes an untouched volatility confirmation sample to the observed paired-loss scale before any confirmation outcomes are inspected. The existing 504-row confirmation remains locked under #191.

#51 remains operator-deferred and was untouched. No trading authority is created by #195.
