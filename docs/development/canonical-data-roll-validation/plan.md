# Canonical Data and Roll Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task in an isolated worktree. Behavior changes use `superpowers:test-driven-development`; completion uses `superpowers:verification-before-completion`.

**Goal:** Make repo development workflow mandatory and add a truthful Massive-based canonical Henry Hub contract-price ingestion path without prematurely unlocking canonical evidence.

**Architecture:** `AGENTS.md` owns startup workflow. `config/data_sources.json` owns Massive provider/source capability. `commodity.massive` owns Massive HTTP acquisition and normalization; `commodity.market_data` owns provider-neutral canonical validation/evidence gates; `commodity.rolls` owns roll selection. Provider-specific raw responses are normalized before entering canonical market semantics.

**Tech Stack:** Python 3.11+, pandas, requests, pytest, Ruff, JSON configuration.

## Global Constraints

- Databento remains excluded for now.
- Raw per-contract rows remain canonical; continuous series remain derived-only.
- No historical per-contract open interest may be fabricated or inferred from volume.
- LIVE trading authority does not change.
- Secrets remain in environment variables only.

### Task 1: Adopt repository development controllers

**Requirements:** R1, R2, R3
**Files:** `.agents/skills/develop-code/**`, `.agents/skills/develop-docs/**`, `.agents/skills/SOURCES.md`, `AGENTS.md`

- [x] Copy the complete reviewed `develop-code` and `develop-docs` skill directories from `C:\Projects\.agents\skills\` into repo-local `.agents/skills/`.
- [x] Update `AGENTS.md` with a mandatory startup-controller rule and `.work/` worktree/feature-branch/PR discipline.
- [x] Record the local adoption source in `.agents/skills/SOURCES.md`.
- [x] Verify both repo-local `SKILL.md` files and referenced assets/references exist.

### Task 2: Specify Massive source capabilities and evidence separation

**Requirements:** R4, R7, R8
**Files:** `config/data_sources.json`, `config/assumptions.json`, `README.md`

- [x] Add `massive_futures` provider configuration using `MASSIVE_API_KEY`.
- [x] Select Massive for `market_canonical` price/settlement ingestion with current history/plan limitations recorded.
- [x] Record `historical_open_interest: false` and keep the dual-liquidity roll-policy decision unresolved.
- [x] Ensure overall canonical evidence remains blocked until an explicit default roll policy is configured and usable.

### Task 3: Implement Massive acquisition with TDD

**Requirements:** R5
**Files:** `tests/test_massive.py`, `src/commodity/massive.py`

- [x] RED: add tests for missing `MASSIVE_API_KEY`, pagination, outright-contract filtering, and session-aggregate requests.
- [x] Run targeted provider tests and confirm failure for missing implementation.
- [x] GREEN: add `MassiveFuturesClient` with bounded pagination and environment-only authentication.
- [x] Run targeted tests to green; refactor without changing behavior.

### Task 4: Normalize canonical contract history and tighten readiness gate with TDD

**Requirements:** R6, R7, R8, R9
**Files:** `tests/test_massive.py`, `tests/test_market_data.py`, `tests/test_pipeline.py`, `tests/test_rolls.py`, `src/commodity/massive.py`, `src/commodity/market_data.py`, `src/commodity/cli.py`

- [x] RED: add normalization tests mapping Massive `session_end_date`, `ticker`, `last_trade_date`, and `settlement_price` to canonical fields.
- [x] RED: add ingestion/CLI tests that combine overlapping outright contracts into the canonical grain.
- [x] RED: add readiness tests showing source approval alone still fails when `default_roll_policy` is null or required historical OI is unavailable.
- [x] Run targeted tests and confirm expected failures.
- [x] GREEN: implement normalization/provenance, canonical multi-contract ingestion, and `fetch-canonical-market` CLI wiring.
- [x] GREEN: require an explicit usable continuous-series default roll policy in `assert_canonical_market_ready`.
- [x] Run targeted market/roll/CLI tests to green; preserve existing roll-boundary behavior.

### Task 5: Review, verify, commit, and prepare PR

**Requirements:** R1–R10
**Files:** all changed files

- [x] Run the repo-local `code-review` workflow against the current diff and resolve all surviving blocking or worthwhile in-scope findings.
- [x] Run the repo-local `modularity-assessment` workflow on the changed implementation boundaries and resolve justified in-scope structural findings.
- [x] Review the final diff against the specification, capability claims, secrets boundary, and rollback path.
- [x] Run `python -m pytest -q`, `python -m ruff check .`, and `git diff --check` on the feature worktree.
- [x] Attempt the non-secret Massive live smoke probe; the runtime blocked the credentialed client invocation, so the limitation is recorded and no secret was exposed.
- [x] Commit the verified implementation slice on the feature branch.
- [ ] Push the feature branch, create/update a PR, and run PR-completion readiness checks.
- [ ] Do not land the PR until the PR-completion landing gate has exact-head confirmation.
