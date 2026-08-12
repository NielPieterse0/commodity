# ML Research Core

Domain-agnostic ML research architecture and experiment contract. Runtime skill discovery is owned by [`../AGENTS.md`](../AGENTS.md).

## Core Flow
`data-engineer → dataset-auditor → experiment-designer → feature-engineer → model-trainer / neural-network-engineer → hyperparameter-optimizer → model-evaluator → reproducibility-auditor`

`experiment-tracker` spans the lifecycle. `bayesian-modeler` is optional.

Model evaluation includes parallel evidence work:

```text
model evaluation
├─ statistical analysis
├─ robustness analysis
└─ research promotion decision
        ↓
reproducibility audit
```

## Responsibility Boundaries
- Data engineering owns provenance, grain, transformations, joins, lineage, and versioned datasets.
- Dataset audit owns fitness, integrity, leakage, labels, and drift.
- Experiment design owns hypotheses, point-in-time boundaries, splits, baselines, controls, metrics, budgets, and research promotion criteria.
- Training owns controlled fitting and checkpoint lineage; neural engineering owns architecture, stability, and adaptation.
- Optimization owns bounded configuration search; evaluation owns forecast/model scoring, robustness, errors, and research promotion evidence.
- Statistical analysis owns uncertainty and significance; reproducibility audit owns independent reconstruction and run variance.
## Canonical Experiment Record
Use `contracts/experiment.schema.json` (schema v2). A run must identify forecast timing, point-in-time datasets/vintages, temporal split boundaries, feature/preprocessing definitions, model configuration, baselines, artifacts, environment, and lineage.

`decision.disposition=promote` means **research promotion only**. It never authorizes deployment, execution, or trading.

## Domain Boundary
Core skill bodies contain no market-specific rules. Domain packs may add targets, release/vintage rules, exchange calendars, roll methodology, cost models, regimes, research maturity states, or evaluation rubrics without forking the shared discipline.

## Safety Boundary
This pack contains Markdown and JSON only: no imported executable code, binaries, encoded assets, package-install steps, credentials, network clients, or automatic execution hooks. External tools remain optional adapters behind normal dependency and trust controls.
