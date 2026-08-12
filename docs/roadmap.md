# Commodity Research Roadmap

> **North star:** demonstrate a robust, reproducible natural-gas forecasting advantage out of sample and in forward testing after realistic costs and risk constraints.

This is the destination sequence, not the current-status owner. `README.md` reports current state; authoritative configuration and policy own their respective gates.

```text
DATA TRUTH  ->  BASELINES  ->  KRONOS + INDICATORS  ->  ROBUST ENSEMBLE  ->  FORWARD TEST  ->  APPROVED EXECUTION
   V0              V1                 V2                     V3                  V4                  V5
```

| Phase | Outcome | Promotion gate |
|---|---|---|
| **V0 - Data truth** | Canonical per-contract market data, deterministic roll/term structure, point-in-time fundamentals/weather, reproducible provenance | Data contract and leakage controls pass |
| **V1 - Evidence baseline** | Naive/seasonal/Ridge benchmarks, volatility + direction targets, compact hypothesis-led indicator library | Walk-forward OOS evidence beats appropriate baselines |
| **V2 - Market-aware fusion** | Kronos market layer + fundamental, futures-structure and technical indicators; component ablations | Fusion adds robust incremental signal over Kronos-only and indicators-only |
| **V3 - Robust ensemble** | Calibrated uncertainty, regime testing, selective challenger models and evidence-based ensembling | Gains persist across regimes, horizons and realistic friction |
| **V4 - Forward validation** | Frozen forecasts, live vintage capture, broker simulation/paper execution, drift monitoring | Forward evidence confirms research assumptions and execution realism |
| **V5 - Controlled execution** | Replaceable broker adapter, explicit risk controls and human-governed deployment | Only after binding policy and explicit approval permit it |
