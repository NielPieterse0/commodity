# Canonical Data and Roll Validation Specification

> Historical implementation record for the 2026-08-12 slice. For current work, consult `AGENTS.md`, the named configuration owners, and the live KIS change workflow in addition to this record; current safety and execution controls remain applicable.

**Status:** approved direction from user request on 2026-08-12
**Development level:** Complex

## Outcome

Adopt the repository development-controller skills, select Massive Futures as the expiry-aware Henry Hub price-source candidate, implement a canonical per-contract ingestion adapter, and tighten the canonical-evidence gate so source approval cannot bypass unresolved roll methodology.

## Requirements

- **R1 — Startup controller:** Every repository work run MUST load one primary controller before repository work: `develop-code` for code/config/schema/test/mixed work, or `develop-docs` for documentation-only work. Mixed or uncertain work defaults to `develop-code`.
- **R2 — Local skill ownership:** Complete repo-local copies of `develop-code` and `develop-docs`, including their assets and references, MUST live under `.agents/skills/` and be discoverable from `AGENTS.md`.
- **R3 — Isolation and landing:** Development MUST use an ignored `.work/` worktree on a non-default branch, then normal commit/push/PR flow. PR landing remains subject to the repository/PR-completion approval gate.
- **R4 — Canonical source selection:** Massive Futures REST is the selected expiry-aware per-contract price/settlement source for the next canonical slice. Databento remains excluded for now.
- **R5 — Provider adapter:** The adapter MUST use `MASSIVE_API_KEY` from the environment, never log it, paginate provider responses safely, distinguish outright NG contracts from combinations, and fetch session aggregates per contract.
- **R6 — Canonical normalization:** Provider rows MUST normalize to the canonical contract grain with `trade_date`, `contract_id`, `expiration`, `settle`, OHLCV where available, and required dataset provenance/session metadata.
- **R7 — Capability truth:** Massive historical aggregates MUST NOT be represented as providing historical per-contract open interest unless the provider exposes and the adapter ingests it. The current documented capability is settlement + OHLCV, not historical OI.
- **R8 — Evidence gate:** Canonical evidence MUST remain blocked while the continuous-series default roll policy is unset or its required inputs are unavailable, even if the market source itself is approved.
- **R9 — Roll safety:** `dual_liquidity_crossover` MUST continue to require both volume and open interest, use only prior-session liquidity, and keep returns `NaN` across roll boundaries.
- **R10 — Closeout review:** Before PR readiness, run the repo-local `code-review` and `modularity-assessment` workflows against the current change boundary. Resolve all blocking and worthwhile in-scope findings, then rerun affected verification.
- **R11 — Policy authority:** `assert_execution_mode` MUST derive LIVE-mode permission from `config/policy.json`; the current policy remains fail-closed with LIVE disabled.
- **R12 — Evaluation validation:** Walk-forward evaluation MUST reject `retrain_every < 1` with an explicit validation error.
- **R13 — Baseline model identity:** Baseline model dispatch and experiment-record architecture MUST fail closed for unknown implementations and derive model identity from `config/models.json` rather than a two-way model-name fallback.
- **R14 — Kronos import hygiene:** Repeated `KronosMiniAdapter` construction MUST NOT add duplicate vendor paths to `sys.path`.
- **R15 — Review disposition clarity:** Documentation/tests MUST make intentional governance-only config ownership, the far-future research-period sentinel, and the deliberate absence of a canonical product-code CLI override explicit. The no-active-contract roll-gap suggestion remains deferred until trading-session gap semantics are specified.

## Acceptance Evidence

- Unit tests demonstrate authentication failure, contract pagination/filtering, canonical normalization, metadata validation, and the roll-evidence gate.
- Existing roll tests continue proving prior-session liquidity and `NaN` roll-boundary returns.
- A live credentialed smoke probe may verify Massive access without emitting secrets; live network access is not required for unit tests.
- Full `pytest`, Ruff, and `git diff --check` pass on the current feature branch.
- Documentation states Massive's current plan/history limitation and missing historical per-contract OI capability.
- Code-review and modularity-assessment outputs have no unresolved blocking or worthwhile in-scope findings.

## Exclusions

- Do not add Databento.
- Do not weaken `config/policy.json` or enable LIVE trading.
- Do not invent open interest, settlement timestamps, or provider capabilities.
- Do not optimize model performance in this slice.
- Weather and deeper EIA vintage adapters remain the next independent point-in-time data slice after canonical price ingestion/roll validation.

## Recovery

All changes are additive/reversible on a feature branch. Roll back by reverting the PR; secrets remain external in `.env` and are never committed.
