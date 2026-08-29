# Commodity — AGENTS.md

## Repository Mandate

`Commodity` is an experimental trading research platform for discovering, forecasting, and validating tradable commodity-market opportunities and determining whether combined signals can produce useful trading decisions.

Initial implementation scope: **natural gas only**. The platform is designed to generalize across tradable instruments and, when later justified by evidence, additional commodity markets.

The first complete reference market is **CME Henry Hub Natural Gas futures**, with **Micro Henry Hub Natural Gas (`MNG`)** as the preferred eventual retail execution instrument, subject to broker/API verification. Henry Hub is the proving ground for the full research lifecycle, not a permanent hard-coded identity for reusable platform components.

## Primary Objective

Build a reproducible system that can:

1. screen tradable instruments and market states for economically plausible opportunities before committing deep research effort;
2. ingest and version market, fundamental, cross-market and explanatory data with point-in-time controls;
3. produce complementary signal families from forecasting models, regime/trend analysis, technical structure, fundamentals/events, volatility and cross-market relationships;
4. validate, calibrate and combine those signals without leakage, including simple baselines and governed tuning/ensembling;
5. translate validated evidence into bounded trade candidates, position/risk decisions and realistic execution assumptions;
6. forward-test the complete decision process through a simulated brokerage environment; and
7. measure whether the integrated system survives realistic costs, regime changes, uncertainty and risk controls.

## Repository Authority

`AGENTS.md` is the repository authority map: it assigns ownership but does not duplicate the values owned elsewhere. Use the following owner for each class of information.

| Authority | Owner |
|---|---|
| Repository mandate, initial research boundary, authority map, development governance | `AGENTS.md` |
| Binding trading/execution permissions and prohibitions | `config/policy.json` |
| Revisable research assumptions and decision-needed defaults | `config/assumptions.json` |
| Data providers, operational source status, availability rules, canonical-evidence gates | `config/data_sources.json` |
| Model enablement, model pins, hardware/runtime model settings | `config/models.json` |
| Completed V1/V2 legacy experiment definitions and evidence pointers | `config/experiment.json`, `config/experiment_candidates.json`, `contracts/experiment.schema.json` |
| New-research methodology activation/gates | `config/research_methodology.json` |
| Future confirmatory preregistration contract | `contracts/prereg.schema.json` |
| Future confirmatory results contract | `contracts/results.schema.json` |
| Future confirmatory experiment artifact directory (`prereg.json`, `results.json`, `interpretation.md`, generated `executive-summary.md`, freeze evidence) | `research/experiments/<experiment-id>/` |
| Programme evidence/feasibility map | `config/programme_evidence_map.json` |
| Programme inference ledger | `config/programme_inference_ledger.json` |
| Sealed confirmation registry | `config/sealed_windows.json` |
| Exploratory/diagnostic run contract and records | `contracts/exploratory_run.schema.json`, `research/exploratory/*.json` |
| Longitudinal research metrics contract | `contracts/research_metrics.schema.json` |
| Longitudinal stage metrics, comparison policy, and regression dispositions | `artifacts/research-metrics/longitudinal-ledger.json` |
| Research maturity stages | `config/research_stages.json` |
| Signal policy | `config/signal_policy.json` |
| Simulation assumptions | `config/simulation.json` |
| External development tools and LLM roles | `config/tools.json` |
| Third-party approval, licensing boundaries, GitHub API/MCP technical-source registry | `docs/THIRD_PARTY.md` |
| Security reporting and secret/local-state boundary | `SECURITY.md` |
| Public contribution and pull-request hygiene | `CONTRIBUTING.md` |
| Desired dataset and geographic/source acquisition architecture | `docs/data-manifest.md` |
| Research milestone sequence | `docs/roadmap.md` |
| Explanatory component and repository architecture | `docs/architecture/` |
| Legacy slice-specific plans/reviews/provenance evidence | `docs/development/<slice>/` (historical only; no new change docs) |
| Temporary change/slice working documentation | `.work/changes/<issue>-<slug>/` |
| Onboarding projection only | `README.md` |

### Single-owner rule

- Every mutable fact, decision, constraint, status, parameter, source approval, or policy has exactly one authoritative owner.
- Other files MUST reference the owner path or stable section instead of copying its values. A summary MAY state consequences at a high level, but MUST NOT become a second source of truth for details likely to drift.
- When information changes, update the owner first, then update only dependent references, tests, provenance, and summaries that are materially affected.
- If two documents conflict, the owner assigned above wins. Resolve the non-owner by replacing duplicated authority with a reference where practical.
- `docs/development/<slice>/` is legacy historical evidence only. Do not add new change/slice documentation there; new working notes belong under ignored `.work/changes/`.
- `.work/` is temporary and non-authoritative. Scientific evidence, machine authority, tests, runtime behavior, and maintained documentation MUST NOT depend on it.
- Raw/ignored snapshots are evidence inputs, not repository authority. Commit only safe provenance summaries needed to support authoritative decisions.

Completed V1/V2 experiment records remain legacy evidence under the contracts that governed them; do not retrospectively preregister or rewrite them. Any new or still-design-stage confirmatory experiment must use the future-methodology authorities above and pass the immutable preregistration gate before empirical execution.

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

- Keep market/instrument discovery, data, signal generation, model research, decision logic, risk, policy, execution and evaluation as separate modules with explicit interfaces.
- Treat forecasting models as signal producers and challengers, not as trading authority or the complete trading system.
- Keep reusable framework logic instrument-independent. Put contract metadata, calendars, roll rules, currencies, source mappings, instrument-specific fundamentals and broker mappings in configuration or bounded adapters.
- Do not introduce new Henry-Hub-specific assumptions into generic modules when an instrument contract or adapter can express the difference.
- Keep model/tool/broker requirements in configuration or policy files; do not hard-code them into implementation logic.
- Treat authoritative ownership as the change boundary: update the owner first, then all dependants, tests, provenance and documentation.
- Prefer simple baselines before increasing model complexity, and prefer cheap instrument/target screening before expensive model or data acquisition work after the Henry Hub reference implementation is complete.
- Record datasets, features, model parameters, predictions and evaluation results so experiments are reproducible and comparable across instruments.
- Every new confirmatory experiment runner MUST call the #249 execution gate and prove an exact remote-bound preregistration, programme-inference registration, and any required sealed-window eligibility before it can access protected outcomes or produce confirmatory results.

## Working Area

Use `.work/` for local implementation scratch, probes, temporary scripts, and non-authoritative change documentation. New slice/change notes belong under `.work/changes/<issue>-<slug>/`. The directory is ignored by Git and disposable after closeout; runtime code, configuration, tests, governed research records, artifacts, and maintained documentation MUST NOT depend on it.

## Mandatory Development Startup

Every repository work run MUST use the live KIS MCP capability and workflow authority before repository change.

- Discover the relevant workflow, capability, and supporting skill through the operations exposed by the connected KIS runtime at the time of the run.
- Treat the workflow/capability contract returned by KIS as authoritative for operation names, required steps, effects, approvals, verification, publication, landing, and cleanup.
- Do not encode KIS catalogue filesystem locations, operation names, provider inventories, or current tool surfaces as repository truth; those are external runtime state and may evolve independently of this repository.
- Do not open, copy, vendor, mirror, symlink, or execute KIS-managed skill/catalogue files directly from filesystem locations. Repository-local Agent Skill catalogues remain forbidden.
- If KIS exposes or selects a development controller or supporting skill, resolve and use it through the live KIS interface rather than a repository-pinned invocation sequence.

The selected live KIS workflow owns engineering-complexity classification, slice specification/planning, applicable supporting skills, review and verification. KIS owns repository-change effect classification and applies the current operation-specific mutation and consent controls within this repository mandate and `config/policy.json`. Use an ignored `.work/` linked worktree on a non-default branch for parallel or non-trivial development. Git publication, review, landing, cleanup, and any required consent follow the currently advertised KIS change workflow rather than a duplicated fixed sequence in this file. Any default-branch change remains subject to KIS exact-change verification and the applicable mutation controls. When KIS selects a PR-completion workflow, follow its exact-head controls as part of that live workflow.

## Work Management

KIS Work Management is the required operational projection for actionable project work. Register each new specification slice, task, research item, defect, review finding, decision, risk, hold, or approval that requires follow-up; roadmap prose or development notes do not substitute for a Work record.

- Work identity is repository-scoped. Commodity change IDs, GitHub issues, pull requests, and Work record IDs belong to `NielPieterse0/commodity`; never reuse or import a `kis-mcp` or other repository's change number.
- At intake, inspect the `commodity` Work inventory and use preview-first KIS reconciliation before apply. Use a Commodity GitHub issue as the source for work that exists before a pull request; use the Commodity pull request as implementation evidence or as the source when the slice already exists only as a PR.
- Keep the Work projection synchronized at meaningful lifecycle transitions and close it only when the authoritative issue/PR, verification, and required documentation evidence support closure.
- Work Management is tracking and portfolio projection, not product authority. Current research, policy, provider, data, model, and architecture facts remain owned by the authoritative artifacts assigned in `Repository Authority` above.
- Do not create a second Work record for the same actionable item. A newly discovered defect or finding that needs independent follow-up gets its own Commodity issue/record unless it is explicitly accepted into an existing slice.

## Repository Tools and Skills

This repository uses KIS MCP through the runtime surfaces available to the active agent. External KIS operations, workflow IDs, provider inventories, skill IDs, and catalogue locations are runtime-owned and MUST NOT be duplicated here as a fixed repository interface.

Resolve development controllers, supporting skills, provider actions, and change workflows from live KIS discovery for each run. KIS instructions refine workflow only; they do not override this repository mandate, `config/policy.json`, or execution boundaries.

## Initial Research Boundary

Forecast the underlying natural-gas futures market; do not optimize initially for CFDs, leveraged certificates or other wrapper products.

Broker integration is an execution adapter, not part of the forecasting model. Saxo OpenAPI/SIM is the leading candidate and MUST be verified before becoming an approved interface.

## Success Criterion

The repository succeeds only if out-of-sample and forward-testing evidence shows a robust, reproducible forecasting/trading advantage after realistic costs and risk constraints. A high backtest score alone is not success.
