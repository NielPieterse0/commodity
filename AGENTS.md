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

## Repository Authority

`AGENTS.md` is the repository authority map: it assigns ownership but does not duplicate the values owned elsewhere. Use the following owner for each class of information.

| Authority | Owner |
|---|---|
| Repository mandate, initial research boundary, authority map, development governance | `AGENTS.md` |
| Binding trading/execution permissions and prohibitions | `config/policy.json` |
| Revisable research assumptions and decision-needed defaults | `config/assumptions.json` |
| Data providers, operational source status, availability rules, canonical-evidence gates | `config/data_sources.json` |
| Model enablement, model pins, hardware/runtime model settings | `config/models.json` |
| Active experiment definition | `config/experiment.json` |
| Candidate experiment definitions | `config/experiment_candidates.json` |
| Experiment-record contract | `contracts/experiment.schema.json` |
| Longitudinal research metrics contract | `contracts/research_metrics.schema.json` |
| Longitudinal stage metrics, comparison policy, and regression dispositions | `artifacts/research-metrics/longitudinal-ledger.json` |
| Research maturity stages | `config/research_stages.json` |
| Signal policy | `config/signal_policy.json` |
| Simulation assumptions | `config/simulation.json` |
| External development tools and LLM roles | `config/tools.json` |
| Third-party approval, licensing boundaries, GitHub API/MCP technical-source registry | `docs/THIRD_PARTY.md` |
| Desired dataset and geographic/source acquisition architecture | `docs/data-manifest.md` |
| Research milestone sequence | `docs/roadmap.md` |
| Explanatory component architecture | `docs/architecture/` |
| Slice-specific historical plans/reviews/provenance evidence | `docs/development/<slice>/` |
| Onboarding/current-state projection only | `README.md` |

### Single-owner rule

- Every mutable fact, decision, constraint, status, parameter, source approval, or policy has exactly one authoritative owner.
- Other files MUST reference the owner path or stable section instead of copying its values. A summary MAY state consequences at a high level, but MUST NOT become a second source of truth for details likely to drift.
- When information changes, update the owner first, then update only dependent references, tests, provenance, and summaries that are materially affected.
- If two documents conflict, the owner assigned above wins. Resolve the non-owner by replacing duplicated authority with a reference where practical.
- `docs/development/<slice>/` records evidence at a point in time. Historical evidence does not become current operational authority unless an authoritative owner explicitly adopts it.
- Raw/ignored snapshots are evidence inputs, not repository authority. Commit only safe provenance summaries needed to support authoritative decisions.

Research remains separated from trading authority; `config/policy.json` alone decides whether execution is permitted.

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

Every repository work run MUST source and invoke Agent Skills exclusively through the KIS MCP skills module before repository inspection or change.

- The canonical Agent Skill catalogue is currently rooted at `C:\Projects\.agents\skills`; treat that location as KIS-managed catalogue state, never as a filesystem invocation interface.
- Discover skills by logical ID through KIS MCP `runtime.search_skills`.
- Load skills only through KIS MCP `runtime.load_skill`; do not open, copy, vendor, mirror, or execute skill instruction files directly from any filesystem path.
- Read supporting skill references/assets only through KIS MCP `runtime.read_skill_file` after loading the owning skill.
- Load `kis-mcp` through `runtime.load_skill` for KIS repository, Work Management, Project, issue, change-control, review, publication, or closeout workflows.
- Load `develop-code` through `runtime.load_skill` for code, configuration, schema, tests, provider integrations, mixed work, or any run whose scope is not yet known.
- Load `develop-docs` through `runtime.load_skill` only for documentation-only work. If executable/configuration changes emerge, switch to `develop-code` through the same KIS MCP skill-loading path.
- Repository-local Agent Skill catalogues, copies, mirrors, or symlinked skill trees are forbidden. Skill IDs in repository documentation are references to the canonical KIS catalogue, not repository files.

The selected controller owns engineering-complexity classification, slice specification/planning, applicable supporting skills, review and verification. KIS owns repository-change effect classification and applies the current operation-specific mutation and consent controls within this repository mandate and `config/policy.json`. Use an ignored `.work/` linked worktree on a non-default branch for parallel or non-trivial development. Git publication, review, landing, cleanup, and any required consent follow the currently advertised KIS change workflow rather than a duplicated fixed sequence in this file. Any default-branch change remains subject to KIS exact-change verification and the applicable mutation controls. When KIS selects a `PR-completion workflow`, follow its exact-head controls as part of that live workflow.

## Work Management

KIS Work Management is the required operational projection for actionable project work. Register each new specification slice, task, research item, defect, review finding, decision, risk, hold, or approval that requires follow-up; roadmap prose or development notes do not substitute for a Work record.

- Work identity is repository-scoped. Commodity change IDs, GitHub issues, pull requests, and Work record IDs belong to `NielPieterse0/commodity`; never reuse or import a `kis-mcp` or other repository's change number.
- At intake, inspect the `commodity` Work inventory and use preview-first KIS reconciliation before apply. Use a Commodity GitHub issue as the source for work that exists before a pull request; use the Commodity pull request as implementation evidence or as the source when the slice already exists only as a PR.
- Keep the Work projection synchronized at meaningful lifecycle transitions and close it only when the authoritative issue/PR, verification, and required documentation evidence support closure.
- Work Management is tracking and portfolio projection, not product authority. Current research, policy, provider, data, model, and architecture facts remain owned by the authoritative artifacts assigned in `Repository Authority` above.
- Do not create a second Work record for the same actionable item. A newly discovered defect or finding that needs independent follow-up gets its own Commodity issue/record unless it is explicitly accepted into an existing slice.

## Repository Tools and Skills

This repository uses KIS MCP through `kis-op` or `kis-dev`. Agent Skill discovery, loading, and supporting-file access MUST use the KIS MCP skills module operations defined in `Mandatory Development Startup`; direct filesystem skill loading is not an approved interface.

Mandatory development-controller skill IDs: `develop-code`, `develop-docs`.

Shared ML research skill IDs: `data-engineer`, `dataset-auditor`, `experiment-designer`, `experiment-tracker`, `feature-engineer`, `model-trainer`, `model-evaluator`, `statistical-analyst`, `reproducibility-auditor`, `bayesian-modeler`, `hyperparameter-optimizer`, `neural-network-engineer`.

Commodity domain skill IDs: `commodity-market-data`, `time-series-research`, `forecast-backtesting`.

Resolve the relevant skill ID against the live canonical KIS catalogue before use. Skill instructions refine workflow only; they do not override this repository mandate, `config/policy.json`, or execution boundaries.

## Initial Research Boundary

Forecast the underlying natural-gas futures market; do not optimize initially for CFDs, leveraged certificates or other wrapper products.

Broker integration is an execution adapter, not part of the forecasting model. Saxo OpenAPI/SIM is the leading candidate and MUST be verified before becoming an approved interface.

## Success Criterion

The repository succeeds only if out-of-sample and forward-testing evidence shows a robust, reproducible forecasting/trading advantage after realistic costs and risk constraints. A high backtest score alone is not success.
