# Trading Platform Generalization — #230

## Outcome

Treat CME Henry Hub as the first complete reference implementation of a reusable trading research platform rather than as the permanent identity of the repository.

The long-term system objective is a robust, reproducible trading advantage after costs and risk controls. Forecasting models are one signal family inside that system, not the system itself.

## Scope

This slice changes architecture and roadmap documentation only. It does not change empirical results, activate another instrument, authorize trading, or modify experiment decisions.

## Required architecture

1. Finish the existing Henry Hub programme A-to-Z as the reference implementation and proving ground.
2. Separate instrument-independent framework logic from instrument-specific configuration, data sources, calendars, roll rules, fundamentals and execution adapters.
3. Avoid new Henry-Hub-specific assumptions in reusable core modules.
4. Make post-reference instrument replication a first-class workflow using the same governed research machinery.
5. Preserve PIT, leakage, reproducibility, statistical, promotion and live-trading controls.
