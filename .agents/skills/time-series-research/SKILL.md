---
name: time-series-research
description: Use when designing Commodity forecasting experiments, temporal splits, feature availability rules, or research promotion decisions for ordered natural-gas data where leakage-safe point-in-time validation is mandatory.
---
# Time-Series Research

## Purpose
Extend `experiment-designer`, `feature-engineer`, and `reproducibility-auditor` with Commodity temporal-research constraints.

## Workflow
1. Define prediction timestamp, target observation timestamp, forecast horizon, and information cutoff explicitly.
2. Build features only from observations whose publication/availability time is at or before the information cutoff.
3. Use chronological, expanding-window, or rolling-window validation; random row splits are prohibited for ordered market forecasting unless explicitly justified as a non-forecast diagnostic.
4. Fit scalers, encoders, imputers, feature selection, dimensionality reduction, and learned transforms on training data only within each split.
5. Keep validation/test periods temporally isolated from feature design and model-selection decisions.
6. Evaluate across multiple market regimes and report period sensitivity rather than relying on one favorable interval.
7. Bind each run to schema-v2 forecast, dataset, split, feature/preprocessing, model, environment, and lineage identities.
8. Use `config/research_stages.json` for Commodity research maturity; stage progression is evidence status, never trading authorization.

## Failure Conditions
Future publication data; revised-vintage substitution; overlapping labels without control; leakage through global preprocessing; hidden roll/calendar lookahead; test-period tuning; undocumented cutoff changes.

## Boundary
Own leakage-safe temporal research design. Trading permission remains exclusively under `config/policy.json`.
