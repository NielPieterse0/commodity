# Integrated Trading Research System

## Purpose

The repository is building a reusable research and decision platform whose eventual goal is a robust trading system, subject to the binding execution policy. Forecasting models are one evidence-producing component of that system.

Henry Hub is the first complete reference implementation. It is used to prove the research lifecycle, interfaces, controls and execution path before the same machinery is replicated onto other justified instruments.

## System layers

```text
Tradable universe / instrument feasibility
        -> market + point-in-time data truth
        -> market state / regime / trend context
        -> complementary signal engines
        -> validation, calibration and signal fusion
        -> trade candidate / position decision
        -> risk controls and portfolio constraints
        -> broker/execution adapter + realistic costs
        -> paper/forward validation + drift monitoring
        -> explicit promotion / human approval
```

Signal engines may include forecasting models, technical structure, fundamental/event surprises, futures-curve information, volatility/uncertainty, positioning and cross-market relationships. A signal family earns influence through out-of-sample evidence; complexity alone gives it no priority.

## Instrument boundary

Reusable core components should consume an explicit instrument contract instead of assuming Henry Hub. Instrument-specific concerns belong in configuration or bounded adapters.

| Reusable core | Instrument-specific boundary |
| --- | --- |
| walk-forward evaluation and statistical tests | contract identifiers, expiry and roll conventions |
| generic feature/signal interfaces | source mappings and market calendars |
| model/challenger interfaces | tick size, contract multiplier and currency |
| calibration and ensemble logic | local fundamentals, events and physical-market drivers |
| trade/risk abstractions | broker symbol/product mapping and execution constraints |
| provenance and experiment governance | licensing/entitlement rules for instrument data |

## Reference then replicate

Henry Hub should continue through the current A-to-Z methodology. During that work, new generic components should remain replaceable so another instrument can be onboarded without copying the research system.

After the reference implementation, a new instrument is expected to follow: feasibility and tradability check -> instrument/data configuration -> PIT data validation -> naive baselines -> existing model/signal ladder -> instrument-specific signals -> governed decision-system evaluation -> forward/execution validation.

Cross-instrument work must distinguish replication from discovery. A result observed on Henry Hub is Henry-Hub evidence until independently tested elsewhere; a failed Henry Hub model does not become a model-wide verdict, and a positive result elsewhere does not retroactively promote Henry Hub.

## Safety and evidence boundary

Market screening, models, indicators and decision logic remain research outputs. They cannot override leakage controls, experiment freezes, statistical gates, risk constraints, or `config/policy.json`. Live trading remains prohibited until the existing staged evidence and explicit approval requirements are satisfied.
