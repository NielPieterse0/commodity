# Commodity Research Roadmap

> **North star:** demonstrate a robust, reproducible trading advantage out of sample and in forward testing after realistic costs and risk constraints.

Henry Hub is the first complete reference implementation. It is the proving ground for the full research lifecycle and reusable platform interfaces, not the permanent identity of the system.

```text
DATA TRUTH -> BASELINES -> SIGNAL FAMILIES -> DECISION SYSTEM -> FORWARD TEST -> CONTROLLED EXECUTION
   V0             V1             V2                 V3               V4                  V5
```

| Phase | Durable outcome | Promotion gate |
| --- | --- | --- |
| **V0 — Data truth** | Provider-neutral contract data, point-in-time controls, reproducible provenance | Data and leakage controls pass |
| **V1 — Evidence baseline** | Simple benchmarks and a reproducible evaluation baseline | Evaluation evidence supports an explicit disposition |
| **V2 — Market-aware signals** | Complementary model, fundamental, curve, technical, regime and cross-market signal families | Incremental information survives controlled comparison |
| **V3 — Decision system** | Calibration, uncertainty, signal combination, position and risk rules | Gains persist across regimes, horizons and realistic friction |
| **V4 — Forward validation** | Frozen decisions, live-vintage capture, simulation/paper execution and drift monitoring | Forward evidence supports the research assumptions |
| **V5 — Controlled execution** | Replaceable broker adapter and explicit operating controls | Binding policy and explicit human approval permit it |

## System flow

The reusable system progresses through instrument feasibility, point-in-time data truth, market context and complementary signal producers, validation/calibration and signal combination, bounded trade/risk decisions, execution adapters with realistic costs, then forward monitoring and explicit promotion. Instrument-specific calendars, roll rules, source mappings, fundamentals and broker mappings stay behind configuration or bounded adapters rather than entering reusable core logic.

## Replication after the reference market

New instruments enter through feasibility screening, instrument/data adapters, point-in-time validation, simple baselines, the existing signal ladder, instrument-specific hypotheses, decision/risk evaluation, and forward validation. Replication is not permission to search many markets for the best historical backtest.

Forecasting models remain one signal family inside the larger system. No roadmap stage grants execution authority; `config/policy.json` is the sole binding owner of that permission.