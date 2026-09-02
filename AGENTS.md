# Commodity

`Commodity` is an experimental commodity-market research platform. The current reference market is CME Henry Hub Natural Gas futures, but reusable platform logic must remain instrument-independent unless a bounded adapter or configuration owns the market-specific difference.

## Repository

Local main `C:/Projects/commodity`

## Primary objective

Build a reproducible system that can:

1. screen tradable instruments and market states for economically plausible opportunities before committing deep research effort;
2. ingest and version market, fundamental, cross-market, and explanatory data with point-in-time controls;
3. produce complementary signal families from forecasting, regime/trend, technical, fundamental/event, volatility, and cross-market methods;
4. validate, calibrate, and combine signals without leakage, using appropriate baselines and governed model or ensemble selection;
5. translate validated evidence into bounded trade candidates, position/risk decisions, and realistic execution assumptions;
6. forward-test the complete decision process in simulation or paper execution; and
7. determine whether the integrated system remains robust after realistic costs, regime changes, uncertainty, and risk controls.

## Authority and ownership

Until the repository ownership model is deliberately simplified and migrated, retain this explicit ordered canonical-owner map. One governed fact has one canonical owner. When authorities conflict, the first applicable owner in this table wins; historical changes, conversations, issue comments, old experiment notes, remembered commands, and non-owning documentation are evidence or context only.

| # | Information | Canonical owner |
| ---: | --- | --- |
| 1 | Durable repository mandate, authority routing, and agent invariants | `AGENTS.md` |
| 2 | Exact executable facts, interfaces, and machine-enforced requirements | implementing source code; `config/*.json` configuration and policy files; `data/acquisition-recipes/*.json` reusable acquisition definitions; `contracts/*.schema.json` contracts and schemas; governed `research/**` records; generated or durable `artifacts/**` evidence where designated below; verification and boundary tests under `tests/**`; repository enforcement scripts under `scripts/**`; `.gitattributes`, `.gitignore`, `SECURITY.md`, and `CONTRIBUTING.md` where specifically designated below |
| 3 | Change-specific scope, reasoning, plan, tasks, decisions, evidence, findings, interpretation, and closeout history | `.work/changes/<change-id>/` |
| 4 | Current executable lifecycle, state, legal next actions, evidence freshness, review/verification requirements, and governed Git/GitHub effects | live `kis-mcp` workflow/capability discovery and execution; live KIS Work Management for configured operational state; live KIS Git/GitHub operations for claims, verification, publication, PR, merge, recovery, and closeout effects |
| 5 | Binding trading and execution permissions/prohibitions | `config/trading-policy.json` |
| 6 | Revisable research assumptions and decision-needed defaults | `config/assumptions.json` |
| 7 | Data-provider implementation, research-dataset construction settings, governance/status, reusable deterministic acquisition recipes, and acquired durable datasets | `src/commodity/providers/` owns provider clients, adapters, and canonical provider loading; `config/data_sources.json` owns source status, availability, and evidence gates; `config/research_dataset.json` owns reusable PIT dataset construction and walk-forward defaults; `data/acquisition-recipes/` owns reusable fetch definitions; acquired durable datasets live under the applicable `data/raw/`, `data/interim/`, or `data/processed/` layer |
| 8 | Commodity-owned model implementations plus model enablement, pins, and runtime settings | `src/commodity/models/` owns Commodity-developed model implementations; `config/models.json` owns enablement, parameters, pins, and runtime settings |
| 9 | New-research methodology activation and gates | `config/research_methodology.json` |
| 10 | Confirmatory preregistration and results contracts | `contracts/prereg.schema.json`, `contracts/results.schema.json` |
| 11 | Confirmatory experiment evidence and durable knowledge | `research/experiments/<experiment-id>/` |
| 12 | Durable programme decisions | `research/programme/programme-decisions.json` |
| 13 | Open research recommendations and questions | `research/programme/research-backlog.json` |
| 14 | Documentation generation registry, generated-page sources, and projection boundaries | `config/documentation_authority.json`, `config/documentation.json`; `scripts/docs/generate_docs.py` deterministically projects all `docs/**/*.md` and verification rejects drift |
| 15 | Programme evidence and feasibility state | `research/programme/programme_evidence_map.json` |
| 16 | Programme inference ledger | `research/programme/programme_inference_ledger.json` |
| 17 | Sealed confirmation windows | `research/programme/sealed_windows.json` |
| 18 | Exploratory/diagnostic run contract | `contracts/exploratory_run.schema.json`; individual change-specific records belong to the governed change record |
| 19 | Literature snapshot contract and cross-change methodology canon | `contracts/literature_snapshot.schema.json`, `research/methodology/`; change-specific literature belongs to the governed change record |
| 20 | HOLD/DEFER scientific revisit triggers and evaluation history | `contracts/revisit_triggers.schema.json`, `research/programme/research_revisit_triggers.json` |
| 21 | Research metrics contract and longitudinal evidence | `contracts/research_metrics.schema.json`, `artifacts/research-metrics/longitudinal-ledger.json` |
| 22 | Research maturity stages and signal policy | `config/research_stages.json`, `config/signal_policy.json` |
| 23 | Simulation assumptions | `config/simulation.json` |
| 24 | External development tools and LLM roles | `config/tools.json` |
| 25 | Pinned third-party source checkouts and third-party runtime assets | `vendor/<project>/` owns third-party source checkouts declared in `.gitmodules`, with the exact source revision pinned by the Git submodule gitlink; consuming configuration/contracts pin applicable model/runtime revisions and assets; model weights, downloaded checkpoints, package caches, and generated third-party outputs remain outside `vendor/` in approved ignored repository-local cache/state locations |
| 26 | Live reusable verification tests | `tests/<domain>/` grouped by current repository domain; `tests/fixtures/` owns reusable test fixtures; tests that only preserve a completed historical change belong with historical change evidence rather than the live suite |
| 27 | Live reusable repository tooling | `scripts/checks/`, `scripts/environment/`, `scripts/data/`, `scripts/models/`, `scripts/docs/`, plus `scripts/verify.ps1` as the canonical verification entry point; one-change experiment/replay scripts belong to that change record or historical change evidence |
| 28 | Third-party approval, licensing, redistribution, and trust boundaries | `config/third_party.json`; projected for humans as generated `docs/THIRD_PARTY.md` |
| 29 | Security reporting and secret/local-state boundary | `SECURITY.md` |
| 30 | Contribution and pull-request hygiene | `CONTRIBUTING.md` |
| 31 | Dataset/source architecture and current source contract | `config/data_sources.json`, `config/research_dataset.json`, `data/acquisition-recipes/`; projected for humans as generated `docs/data-manifest.md` and `docs/reference/data/**` |
| 32 | Research maturity sequence | `config/research_stages.json`, `config/signal_policy.json`; projected for humans as generated `docs/roadmap.md` |
| 33 | Human-readable research methodology projection | `config/research_methodology.json`, applicable `contracts/*.schema.json`, `research/methodology/`; projected as generated `docs/research-methodology.md` |
| 34 | Programme big-picture state and narrative projection | `research/programme/programme_evidence_map.json`; projected as generated `docs/big-picture.md` |
| 35 | Legacy completed experiment definitions/evidence pointers | `.work/historical/config/`, `.work/historical/contracts/` |
| 36 | Historical slice-specific development evidence | `.work/historical/docs/development/` |
| 37 | Isolated implementation worktrees | `.work/worktrees/` |
| 38 | Preserved non-authoritative legacy/scratch/audit working material | `.work/historical/` |
| 39 | Human onboarding/orientation | `README.md` |
| 40 | Binding repository rule-to-verifier registry and generated verification projection | `config/rule_verification.json`; projected through the documentation generator as `docs/rule-verification.md` |

When information changes, update its canonical owner first. Do not create another competing ownership registry elsewhere.

Every repository-local binding rule that can be decided deterministically from repository state MUST be declared in `config/rule_verification.json` with its authoritative source and executable verifier. The registry is the machine-readable rule-to-verification map. Repository-local deterministic rules MUST execute through `scripts/verify.ps1` before CI and be repeated in CI. A binding rule that genuinely depends on external lifecycle state MUST be explicitly classified in the registry as non-local with its reason and live enforcement authority; documentation or operator discipline alone is not sufficient for a repository-local deterministic rule.

## Repo change and development workflow

Every bounded unit of work in this repository is a governed **change**, including research and experiments as well as engineering, documentation, data, audit, maintenance, configuration, and policy work. A change keeps one identity and one history even when it concludes that no repository mutation is required.

For each governed change, keep its scope, plan, tasks, hypotheses where applicable, decisions, implementation notes, review findings, verification evidence, interpretation, and closeout in one change-local record under `.work/changes/<issue>-<slug>/`. Active, closed, held, and deferred are lifecycle states, not directory classes: closing a governed change does not relocate its record. When an associated implementation worktree is retained, it belongs under `.work/worktrees/<issue>-<slug>/`; safe worktree cleanup may remove the physical checkout later without removing the change record.

### KIS operation rules

- Operate repository changes through the live `kis-mcp` workflow and use its current lifecycle state, legal next actions, evidence, review, verification, Git/GitHub, recovery, and closeout rules.
- Do not reproduce or substitute the evolving KIS lifecycle with remembered steps, manual lifecycle actions, or historical commands.
- Work Management owns configured operational tracking such as priority, readiness, hold/defer state, scheduling, and claims; it does not own repository, scientific, policy, or KIS workflow truth.

## Skills

Reusable skills must be discovered and loaded through the live KIS Skills module. Do not vendor or maintain a repository-local reusable skill catalogue.

| Skill / skill family | MUST load when |
| --- | --- |
| `data-engineering` | Any change that reads, acquires, imports, transforms, validates, reconstructs, normalizes, audits, interprets, or otherwise relies on repository data or data lineage. |
| `kis-mcp` | Operating, planning, claiming, verifying, publishing, merging, recovering, or closing a governed repository change. |
| `develop-code` | Changing code, tests, schemas, generators, executable configuration, or other implementation logic. |
| `develop-docs` | Changing maintained documentation or documentation governance. |
| All applicable live KIS data-engineering skills | Acquiring, importing, transforming, validating, reconstructing, normalizing, or auditing data. |
| All applicable live KIS model/research/statistics skills | Designing or executing experiments, modelling, forecasting, statistical analysis, calibration, evaluation, or literature-driven research. |
| `code-review` and `code-verification` | Reviewing or verifying implementation changes where those skills apply. |
| `modularity-assessment` / architecture skills | Assessing or changing architecture, module boundaries, interfaces, or dependency direction. |
| `security-guide` and other applicable specialist skills | Work touches security, secrets, permissions, external effects, or another specialist domain. |
| Any other skill selected by live KIS for the bounded change | When the live workflow or discovered task scope declares it applicable. |

For mixed changes, load every applicable skill against the same governed change record. Skills provide procedure, not authority and cannot expand repository or external-effect permissions.

## Repository standards

- Write only within `C:/Projects/commodity`.
- Never permanently delete repository artifacts; use recoverable quarantine for delete-like intent.
- Keep temporary/generated state in KIS-managed state or approved ignored repository-local temporary locations.
- Do not commit secrets, tokens, machine-specific credentials, caches, provider installations, generated runtime state, or quarantine contents; follow `SECURITY.md` for the authoritative security boundary.
- Treat `.gitattributes` as tracked line-ending authority and preserve its explicit CRLF/binary exceptions.
- Use `scripts/verify.ps1` as the canonical repository verification entry point when repository verification is required by live KIS.
- Do not describe target behavior as implemented without fresh applicable evidence.
- Execute repository Python and project tooling from the active checkout/worktree's own `.venv`. A worktree must not borrow another checkout's `.venv`. Create the worktree-local `.venv` from an explicitly repository-approved Python runtime under `C:/Projects` when needed; do not invoke Python executables, packages, caches, or tool installations from user-profile or unrelated checkout locations. CI may use its repository-pinned runner interpreter only to bootstrap a checkout-local `.venv`; after that bootstrap, every repository Python/tool invocation must use that `.venv`.

## Historical and legacy material

The repository was restructured so current durable owners remain at the repository top level while retired and non-authoritative material is preserved under `.work/historical/` rather than deleted.

- `.work/historical/config/` — retired configuration and policy material, preserving the old relative path where practical.
- `.work/historical/contracts/` — retired contracts and schemas.
- `.work/historical/docs/` — retired documentation, including the legacy `docs/development/` tree.
- `.work/historical/research/` — research records that were removed from the durable research tree because they belong to historical, change-specific work.
- `.work/historical/src/` — retired experiment- or change-specific executable code that is no longer part of the live reusable package.
- `.work/historical/tests/` — verification retained only for retired historical behavior rather than the current repository contract.
- `.work/historical/scripts/` and `.work/historical/workflows/` — retired one-change runners, hashes, and automation that must not participate in current execution or CI.
- Other pre-governance or non-governed legacy scratch, audit, probe, cache, quarantine, orphaned experiment, and non-authoritative working material may remain elsewhere under `.work/historical/` when it does not correspond to one of the mirrored durable owners above. Governed change records do not move to `.work/historical/` merely because they are closed, and directories that are still identifiable as Git worktrees belong under `.work/worktrees/`.

Historical material is evidence or context only. Do not treat `.work/historical/**` as current authority, and do not recreate retired top-level paths from it.