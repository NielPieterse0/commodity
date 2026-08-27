# Commodity Research Roadmap

> **North star:** demonstrate a robust, reproducible trading advantage out of sample and in forward testing after realistic costs and risk constraints.

Henry Hub remains the first complete reference implementation. Its purpose is to take one market through the full research lifecycle while building reusable platform machinery. After that reference path is complete, additional instruments enter a governed replication workflow rather than rebuilding the research stack.

Geographic/data expansion is owned by `docs/data-manifest.md`. System component architecture is described in `docs/architecture/trading-system.md`.

**Current milestone:** the Henry Hub V1 empirical evidence baseline is complete with bounded caveats and concluded `no_robust_edge`. Current experiment decisions remain owned by their assigned configuration and immutable evidence; this roadmap does not reinterpret them.

## Reference implementation — Henry Hub

```text
DATA TRUTH -> BASELINES -> MODEL + SIGNAL FAMILIES -> ROBUST DECISION SYSTEM -> FORWARD TEST -> APPROVED EXECUTION
   V0             V1                  V2                        V3                   V4                 V5
```

| Phase | Outcome | Promotion gate |
| --- | --- | --- |
| **V0 - Data truth** | Provider-neutral per-contract data, deterministic roll/term structure, point-in-time fundamentals/weather, reproducible provenance | Data contract and leakage controls pass |
| **V1 - Evidence baseline** | Naive/statistical/tree-boosting benchmarks, volatility + direction targets, compact hypothesis-led indicator library | Full-V1 walk-forward, robustness, and ablation evidence is reproducible and supports a governed disposition |
| **V2 - Market-aware signals** | Forecast-model challengers plus fundamental, futures-structure, technical, regime/trend and cross-market signal families; component ablations | Added signal families provide robust incremental information over the strongest component controls |
| **V3 - Robust decision system** | Calibrated uncertainty, selective challengers, evidence-based ensembling and bounded trade-decision rules | Gains persist across regimes, horizons and realistic friction |
| **V4 - Forward validation** | Frozen decisions, live vintage capture, broker simulation/paper execution and drift monitoring | Forward evidence confirms research assumptions and execution realism |
| **V5 - Controlled execution** | Replaceable broker adapter, explicit risk controls and human-governed deployment | Only after binding policy and explicit approval permit it |

## Post-reference replication

Once the Henry Hub reference path has reached the appropriate completion gate, additional tradable instruments follow a bounded replication sequence:

```text
INSTRUMENT FEASIBILITY
-> instrument/data adapter
-> data truth + naive baselines
-> existing model/signal ladder
-> instrument-specific fundamentals
-> decision/risk/execution validation
-> cross-instrument comparison
```

Replication is not permission to mine many markets for the best historical backtest. Candidate instruments and targets must pass cheap feasibility screens, then serious empirical tests remain preregistered and leakage-safe.

The purpose of replication is to learn which findings transfer and which are market-specific: baseline difficulty, model usefulness, signal families, horizons, calibration, costs and execution viability.

## Integrated system direction

Forecasting models are one branch of the platform. The intended system combines instrument selection, market-state/regime analysis, technical structure, fundamentals/events, cross-market information, model forecasts, uncertainty, signal fusion, trade decisions, risk controls and execution evidence.

No roadmap stage grants trading authority. `config/policy.json` remains the sole binding owner of execution permission.
