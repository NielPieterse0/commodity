# Commodity Research Roadmap

> **North star:** demonstrate a robust, reproducible natural-gas forecasting advantage out of sample and in forward testing after realistic costs and risk constraints.

This file owns only the research milestone sequence. The repository authority map is in `AGENTS.md`; current operational gates remain in their assigned configuration owners. Geographic/data expansion is owned by `docs/data-manifest.md`: U.S. / Henry Hub first, then Global/Interconnect and Norway/Europe when incremental evidence justifies promotion.

**Current milestone:** the V1 empirical evidence baseline is complete with bounded caveats and concluded `no_robust_edge`. Issue #78 is closed/accepted and its governed longitudinal measurement/regression infrastructure is operational; the early-smoke → Phase-D result change is non-comparable and does not establish a software/data regression. V1 programme closure is through #15. Research promotion and trading authority remain false, and V2 empirical activation becomes eligible only after #15 itself is terminally closed and reconciled.

```text
DATA TRUTH  ->  BASELINES  ->  KRONOS + INDICATORS  ->  ROBUST ENSEMBLE  ->  FORWARD TEST  ->  APPROVED EXECUTION
   V0              V1                 V2                     V3                  V4                  V5
```

| Phase | Outcome | Promotion gate |
|---|---|---|
| **V0 - Data truth** | Provider-neutral per-contract data, deterministic roll/term structure, point-in-time fundamentals/weather, reproducible provenance | Data contract and leakage controls pass |
| **V1 - Evidence baseline** | Naive/statistical/tree-boosting benchmarks, volatility + direction targets, compact hypothesis-led indicator library | Full-V1 walk-forward, robustness, and ablation evidence is reproducible and supports a governed disposition; robust edge is required for an edge/promotion claim, not for V1 system completion |
| **V2 - Market-aware fusion** | Kronos market layer + fundamental, futures-structure and technical indicators; component ablations | Fusion adds robust incremental signal over Kronos-only and indicators-only |
| **V3 - Robust ensemble** | Calibrated uncertainty, regime testing, selective challenger models and evidence-based ensembling | Gains persist across regimes, horizons and realistic friction |
| **V4 - Forward validation** | Frozen forecasts, live vintage capture, broker simulation/paper execution, drift monitoring | Forward evidence confirms research assumptions and execution realism |
| **V5 - Controlled execution** | Replaceable broker adapter, explicit risk controls and human-governed deployment | Only after binding policy and explicit approval permit it |
