# Commodity — AGENTS.md

## Repository Mandate

`Commodity` is an experimental ML research repository for forecasting tradable commodity markets and validating whether those forecasts can produce useful trading decisions.

Initial scope: **natural gas only**.

The first target market is **CME Henry Hub Natural Gas futures**, with **Micro Henry Hub Natural Gas (`MNG`)** as the preferred eventual retail execution instrument, subject to broker/API verification.

## Primary Objective

Build a reproducible system that can:

1. ingest and version natural-gas market and explanatory data;
2. engineer predictive features from weather, storage, production, LNG, flows, seasonality and market structure;
3. train and compare forecasting models;
4. backtest decisions without leakage;
5. forward-test predictions through a simulated brokerage environment;
6. measure whether model signals survive realistic execution costs and risk controls.

## Assumptions and Policy

Revisable project assumptions live in `config/assumptions.json`. They are not immutable requirements: each assumption carries a status and review trigger and may be replaced by an explicit decision.

Binding execution boundaries live only in `config/policy.json`. Research remains separated from trading authority, and no model may directly authorize LIVE trades while that policy prohibits it.

## Experimental Progression

```text
Historical research
→ leakage-safe backtest
→ broker simulation / paper execution
→ forward evaluation
→ explicit human approval before any live trading
```

Research backtesting may use clearly labeled bootstrap or noncanonical inputs. Those runs are valid for pipeline development and hypothesis screening, but they MUST NOT be promoted as canonical market evidence until the canonical data gate passes.

Live trading is out of scope until simulation evidence, execution controls and an explicit approval decision exist.

## Architecture Rules

- Keep data, models, policy, execution and evaluation as separate modules with explicit interfaces.
- Keep model/tool/broker requirements in configuration or policy files; do not hard-code them into implementation logic.
- Treat authoritative ownership as the change boundary: update the owner first, then all dependants, tests, provenance and documentation.
- Prefer simple baselines before increasing model complexity.
- Record datasets, features, model parameters, predictions and evaluation results so experiments are reproducible.

## Working Area

Use `.work/` for local implementation scratch, probes, temporary scripts, and other non-authoritative work. It is ignored by Git; runtime code, configuration, tests, and authoritative documentation MUST NOT depend on it.

## Mandatory Development Startup

Every repository work run MUST load one primary development controller immediately after reading governing repository instructions and before any other repository inspection or change:

- Load `.agents/skills/develop-code/SKILL.md` for code, configuration, schema, tests, provider integrations, mixed work, or any run whose scope is not yet known.
- Load `.agents/skills/develop-docs/SKILL.md` only when the run is documentation-only. If documentation work discovers executable/configuration changes, switch to `develop-code` for that slice.

The selected controller owns engineering-complexity classification, slice specification/planning, applicable Superpowers sub-skills, review and verification. KIS owns repository-change effect classification and applies the current operation-specific mutation and consent controls within this repository mandate and `config/policy.json`. Use an ignored `.work/` linked worktree on a non-default branch for parallel or non-trivial development. Git publication, review, landing, cleanup, and any required consent follow the currently advertised KIS change workflow rather than a duplicated fixed sequence in this file. Any default-branch change remains subject to KIS exact-change verification and the applicable mutation controls. When KIS selects a `PR-completion workflow`, follow its exact-head controls as part of that live workflow.

## Repository Tools

This repo uses the `kis-mcp` tool:  `kis-op` or `kis-dev`
Load the `kis-mcp` tool skill at `C:\Projects\kis-mcp\.agents\skills\kis-mcp`

## Repository Skills

Repo-local Agent Skills are discoverable under `.agents/skills/<skill-name>/SKILL.md`.

Mandatory development controllers:
`develop-code`, `develop-docs`.

Shared ML research skills:
`data-engineer`, `dataset-auditor`, `experiment-designer`, `experiment-tracker`, `feature-engineer`, `model-trainer`, `model-evaluator`, `statistical-analyst`, `reproducibility-auditor`, `bayesian-modeler`, `hyperparameter-optimizer`, `neural-network-engineer`.

Commodity domain skills:
`commodity-market-data`, `time-series-research`, `forecast-backtesting`.

Load the relevant skill by task intent. Skill instructions refine workflow only; they do not override this repository mandate, `config/policy.json`, or execution boundaries.

## Initial Research Boundary

Forecast the underlying natural-gas futures market; do not optimize initially for CFDs, leveraged certificates or other wrapper products.

Broker integration is an execution adapter, not part of the forecasting model. Saxo OpenAPI/SIM is the leading candidate and MUST be verified before becoming an approved interface.

## Success Criterion

The repository succeeds only if out-of-sample and forward-testing evidence shows a robust, reproducible forecasting/trading advantage after realistic costs and risk constraints. A high backtest score alone is not success.
