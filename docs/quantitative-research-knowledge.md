<!-- GENERATED FILE. DO NOT EDIT. Source: config/quantitative_research_knowledge.json, contracts/quantitative_research_knowledge.schema.json, AGENTS.md -->

# Quantitative Research Knowledge Router

Source: `config/quantitative_research_knowledge.json`

Route Commodity quantitative-research and engineering questions to authoritative sources and executable repository rules without replacing canonical methodology.

This router supplements canonical Commodity owners; it does not replace repository methodology, policy, contracts, or live KIS skills.

## External authorities

| ID | Tier | Source | Primary domains |
| --- | ---: | --- | --- |
| `ml4t3` | 1 | Machine Learning for Trading, 3rd edition repository | financial_ml_research, feature_engineering, model_selection_and_tuning, backtesting_and_trading |
| `fpp3` | 1 | Forecasting: Principles and Practice, 3rd edition | forecasting, feature_engineering, forecast_evaluation |
| `fde` | 1 | Fundamentals of Data Engineering | data_engineering |
| `dmls` | 1 | Designing Machine Learning Systems | temporal_integrity_and_leakage, model_selection_and_tuning, production_monitoring |
| `ddia2` | 2 | Designing Data-Intensive Applications, 2nd edition | data_infrastructure_deep_dive |

## Routing

| Domain | Primary | Secondary |
| --- | --- | --- |
| `data_engineering` | `fde` | `ddia2` |
| `forecasting` | `fpp3` | `ml4t3` |
| `financial_ml_research` | `ml4t3` | `fpp3`, `dmls` |
| `feature_engineering` | `ml4t3` | `fpp3`, `dmls` |
| `model_selection_and_tuning` | `ml4t3` | `dmls`, `fpp3` |
| `temporal_integrity_and_leakage` | `dmls` | `ml4t3`, `fde` |
| `backtesting_and_trading` | `ml4t3` | `fpp3` |
| `production_monitoring` | `dmls` | `fde`, `ddia2` |

## Executable playbooks

### Temporal Integrity

Make every model input reconstructable at the decision timestamp.

1. Record event time, availability time, source, version/as-of identity, and revision state for every forecast input whose publication can lag observation.
2. At each decision timestamp, join only records whose declared availability time is not later than that timestamp; fail closed when timing cannot be defended.
3. Fit scaling, imputation, encoding, feature selection, calibration, and learned transformations inside the active training fold only, then apply them forward.
4. Keep reserved-confirmation outcomes unread and unusable during design, fitting, tuning, calibration, model selection, threshold selection, and feature revision.

### Target Definition

Bind the forecast target to the intended trading decision and executable exposure.

1. Declare decision timestamp, target start/end, forecast horizon, target units, and contract/roll identity before model fitting.
2. Construct labels so no value published or realized after the decision timestamp enters a predictor or selection statistic.
3. Identify overlapping target windows and require purge, embargo, or dependence-aware evaluation whenever overlap can leak label information across folds.
4. Keep the statistical forecast target separate from signal policy and executable P&L accounting; document the translation explicitly.

### Feature Engineering

Create features whose timing, transformation, and missingness are reproducible out of sample.

1. For every feature family, record raw source, timing semantics, transformation, lag, revision behavior, and the decision-time availability rule.
2. Estimate data-dependent transformations and feature-selection decisions only on the training sample of the active fold.
3. Represent unavailable, not-yet-published, structurally absent, and genuinely missing values explicitly instead of silently forward filling across an information boundary.
4. Require simple feature-family baselines and controlled ablations before crediting a large feature set with incremental forecast value.

### Validation And Cross Validation

Estimate generalization using chronological, dependence-aware partitions.

1. Use chronological train/validation/test ordering; do not use random K-fold validation for temporally dependent forecast samples.
2. When comparing or tuning candidates, keep model selection inside inner walk-forward folds and reserve outer folds for unbiased selection-performance estimation.
3. Purge or embargo observations whose label windows or information sets overlap across fold boundaries, with the gap derived from the target construction.
4. Preserve all attempted candidates and fold-level scores, including failures, so the selection path and research multiplicity remain auditable.

### Model Selection And Tuning

Bound candidate search so selection evidence remains interpretable and reproducible.

1. Before selection, declare the candidate families, hyperparameter ranges, objective, calibration choices, and compute/search budget.
2. Include naive, seasonal, linear, and other decision-relevant simple baselines appropriate to the target before promoting more complex candidates.
3. Choose hyperparameters, model family, calibration, thresholds, and feature subsets using training/inner-validation evidence only.
4. Fit calibrators and stackers from out-of-fold base-model predictions and treat their fitting as a separate selection boundary with its own timing controls.

### Forecast Evaluation

Judge forecasts against target-matched baselines with uncertainty and diagnostic context.

1. Score against target-matched naive, seasonal, simple statistical, and market-implied baselines where each comparator is defensible and available at forecast time.
2. Choose primary and secondary metrics from the target units and downstream decision; do not substitute an easier metric after outcomes are observed.
3. Report residual/error diagnostics by horizon and predeclared market state, including bias, scale, autocorrelation/dependence, and failure concentration.
4. When probabilistic forecasts are used, evaluate interval or quantile calibration and sharpness, and use dependence-aware uncertainty for comparative claims.

### Backtesting

Translate forecast information into auditable, executable trading outcomes without timing or accounting shortcuts.

1. Record signal timestamp, earliest executable fill timestamp, execution rule, and actual held contract; reject same-bar fills unless market timing makes them defensible.
2. Apply declared spread, slippage, fees, contract sizing/rounding, margin/capital constraints, and roll costs before evaluating trading value.
3. Carry positions across bars explicitly, account for entries, exits, rolls, and flat states, and derive P&L from the instrument actually held rather than a proxy target series.
4. Preserve signal, order/fill assumption, position, contract, cost, and equity ledgers while keeping reserved-confirmation outcomes outside policy optimization.

## Methodology coverage

| Control | Status | Gap |
| --- | --- | --- |
| `point-in-time-data-and-availability` | `covered` | — |
| `protected-confirmation` | `covered` | — |
| `attempt-history-and-reproducibility` | `covered` | — |
| `target-matched-benchmarks` | `partial` | Formalize a reusable baseline ladder per target/horizon and require forecast residual diagnostics. |
| `nested-walk-forward-selection` | `missing` | Implement nested walk-forward outer evaluation with inner-only tuning, purge/embargo rules, and retained fold evidence. |
| `execution-accounting` | `partial` | Complete and verify signal timestamp, fill timestamp, held contract, position persistence, roll, cost, and P&L accounting as one baseline path. |
| `probabilistic-forecast-evaluation` | `partial` | Require calibration and coverage checks whenever a candidate emits probabilistic forecasts. |
| `training-serving-skew` | `missing` | Add feature freshness, schema parity, training-serving skew, and inference-input audit checks before production hardening. |
| `pipeline-observability` | `partial` | Define production freshness, completeness, lineage, failure, and recovery telemetry only when Phase 8 is justified. |
| `drift-retraining-policy` | `missing` | Define drift detection, retraining authority, rollback, and model suspension rules after prospective edge exists. |

## Deferred controls

| Control | Target phase | Requirement |
| --- | ---: | --- |
| `baseline-ladder-and-residual-diagnostics` | 1 | Define target/horizon-specific naive, seasonal, statistical, and market-implied baselines plus residual diagnostics. |
| `nested-walk-forward-model-selection` | 2 | Implement outer chronological evaluation with inner-only tuning and target-derived purge/embargo. |
| `complete-execution-ledger` | 1 | Complete signal-to-fill-to-held-contract-to-cost-to-P&L accounting in one auditable path. |
| `probabilistic-calibration` | 4 | Evaluate interval/quantile calibration and coverage for probabilistic specialist forecasts. |
| `training-serving-skew-and-drift` | 8 | Add feature freshness, schema parity, skew, drift, retraining, rollback, and model suspension controls. |
| `data-pipeline-observability` | 8 | Define freshness, completeness, lineage, failure, recovery, and serving observability after prospective edge is demonstrated. |

## Boundaries

- External copyrighted book prose is not copied into Commodity; only source metadata, original distilled principles, executable Commodity rules, and citations are retained.
- Third-party code requires explicit license review before import; Phase 0 imports no third-party code.
- Reserved-confirmation outcomes remain unread and cannot influence design, fitting, tuning, calibration, selection, or feature revision.
