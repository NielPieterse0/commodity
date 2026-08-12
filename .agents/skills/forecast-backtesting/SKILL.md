---
name: forecast-backtesting
description: Use when evaluating how Commodity forecasts translate into signals, strategy rules, or execution-aware simulation while preserving the separation between predictive model evaluation and trading authority.
---
# Forecast Backtesting

## Purpose
Own the downstream evaluation chain from immutable forecasts to decision rules and execution-aware simulation without granting the forecasting model trading authority.

## Evaluation Layers
```text
forecast evaluation
        ↓
signal / policy evaluation
        ↓
execution-aware simulation
```

1. Forecast evaluation uses shared `model-evaluator` and predictive metrics only.
2. Signal/policy evaluation applies an explicit, versioned mapping from forecasts to decisions; never infer that prediction sign is the canonical policy.
3. Execution-aware simulation applies instrument, contract, costs, slippage, fills, sizing, risk, and exit assumptions through separate versioned policy/configuration.
4. Report forecast quality, signal quality, strategy performance, and executable performance separately.
5. Use point-in-time contracts, rolls, calendars, and prices from `commodity-market-data`.
6. Reject backtests that use future-known fills, costs, contract selection, revisions, or policy changes.
7. Record all downstream assumptions and artifacts so the simulation can be rerun from stored forecasts.

## Boundary
This skill evaluates hypothetical decisions. It does not submit orders, approve LIVE trading, or move research stages. `config/policy.json` remains the sole execution-permission authority.
