# Kronos + Indicator Fusion

## Purpose

Define the planned research architecture for combining a pretrained financial-market model with natural-gas-specific and technical indicators.

This document is explanatory architecture, not configuration authority. `config/models.json` owns model enablement and pins; data, assumptions, signal, simulation, and execution policy remain owned by their existing configuration files.

## Decision

Evaluate **Kronos as a swappable market-representation layer**, not as the sole forecasting model and not as a reasoning or execution authority.

Kronos consumes expiry-aware OHLCV/market history and contributes learned market-state signals. Those signals are fused with leakage-safe engineered indicators that encode natural-gas fundamentals, futures structure, technical state, and known-at-time context.

```text
OHLCV / contract history -> Kronos -> market representation / forecast features --+
                                                                                  |
Weather / storage / production / LNG / power burn / CFTC -------------------------+
Curve / seasonality / volatility / technical indicators --------------------------+
                                                                                  |
                                                                                  v
                                                                         fusion model
                                                                                  |
                                                                                  v
                                                                 direction / volatility /
                                                                   distribution forecasts
```

## Indicator layers

Use compact, hypothesis-led feature groups rather than an indiscriminate indicator library:

- **Natural-gas fundamentals:** weather forecast surprises/GWDD, storage surprises and seasonal deviation, production, LNG demand, power burn, and CFTC positioning.
- **Futures structure:** contract rank, days to expiry, calendar spreads, curve slope/curvature, roll state, volume, and open interest when canonical.
- **Technical market state:** returns, momentum/trend, ranges, realized volatility, volume/liquidity state, and other price-derived indicators only when they have a defined hypothesis.
- **Context:** seasonality, event timing, regime flags, and selected cross-market inputs.

Every feature must be computable from information knowable at the prediction timestamp. Feature groups should be ablated so incremental value is measurable.

## Kronos integration sequence

**V1 - forecast-derived features.** Start with reproducible Kronos outputs such as expected direction/return, predicted high-low range, predicted volatility, forecast-path dispersion, predicted volume, and multi-horizon forecasts.

**V2 - learned representations.** Test internal latent representations only if V1 adds out-of-sample value and extraction can be made stable, pinned, and reproducible.

**V3 - ensemble/meta-model.** Allow regime-aware weighting or stacking only after individual components establish independent value.

## Required comparison

Use identical leakage-safe walk-forward splits and targets for the core ablation:

1. indicators only;
2. Kronos only;
3. **Kronos + indicators**;
4. later, alternate time-series foundation model + indicators where justified.

The fusion model earns promotion only if it adds robust out-of-sample signal over both standalone components and survives the repository's forward-testing, cost, and risk gates.

## Guardrails

- Kronos provides a pretrained financial-market prior; it does not supply natural-gas causal reasoning.
- Keep the foundation-model adapter replaceable so another model can win on evidence.
- Do not let technical indicators become a feature zoo; require rationale, timestamp correctness, and ablation evidence.
- Raw per-contract market data remains canonical; derived continuous/technical features belong downstream.
- No forecasting component directly authorizes LIVE execution. `config/policy.json` remains authoritative for that boundary.
