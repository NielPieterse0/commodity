# Canonical Data and Roll Validation Implementation Plan

> **For agentic workers:** Resolve and load required execution, test-discipline, and verification skill IDs through the KIS MCP skills module as applicable. Do not invoke skill instructions from repository or filesystem paths.

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
**Files:** `AGENTS.md`

- [x] Superseded 2026-08-14: resolve `develop-code` and `develop-docs` by logical ID from the canonical catalogue through the KIS MCP skills module; do not copy them into the repository.
- [x] Update `AGENTS.md` with a mandatory startup-controller rule and `.work/` worktree/feature-branch/PR discipline.
- [x] Superseded 2026-08-14: `AGENTS.md` records the canonical KIS MCP invocation contract; no repository-local skill source record is retained.
- [x] Superseded 2026-08-14: verify required skill IDs through KIS MCP catalogue discovery/loading rather than filesystem files.

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

- [x] Resolve the canonical `code-review` workflow/skill through KIS MCP and run it against the current diff; resolve all surviving blocking or worthwhile in-scope findings.
- [x] Resolve the canonical `modularity-assessment` workflow/skill through KIS MCP and run it on the changed implementation boundaries; resolve justified in-scope structural findings.
- [x] Review the final diff against the specification, capability claims, secrets boundary, and rollback path.
- [x] Run `python -m pytest -q`, `python -m ruff check .`, and `git diff --check` on the feature worktree.
- [x] Attempt the non-secret Massive live smoke probe; the runtime blocked the credentialed client invocation, so the limitation is recorded and no secret was exposed.
- [x] Commit the verified implementation slice on the feature branch.
- [x] Publish the exact verified feature tree and create/update the PR.
- [ ] Run PR-completion readiness checks against the current PR head.
- [ ] Do not land the PR until the PR-completion landing gate has exact-head confirmation.

### Task 6: Close external review findings with TDD

**Requirements:** R11–R15
**Files:** `config/models.json`, `README.md`, `src/commodity/policy.py`, `src/commodity/evaluation.py`, `src/commodity/records.py`, `src/commodity/cli.py`, `src/commodity/kronos.py`, `tests/test_boundaries.py`, `tests/test_pipeline.py`, `tests/test_kronos.py`, `docs/development/canonical-data-roll-validation/review.md`

- [x] RED: prove LIVE-mode permission is controlled by `config/policy.json`, non-positive retraining intervals fail explicitly, model identity is config-derived/fail-closed, and repeated Kronos initialization does not duplicate `sys.path`.
- [x] Run the targeted tests and confirm each new behavior test fails for the reviewed defect.
- [x] GREEN: make the smallest policy/evaluation/model/Kronos changes needed to satisfy those tests while leaving LIVE disabled in authoritative policy.
- [x] Clarify governance-only configuration ownership, the `2100-01-01` open-ended research sentinel, and the intentional absence of `--product-code`; record the roll-gap suggestion as deferred pending trading-session semantics.
- [x] Rerun targeted tests, full pytest, Ruff, and `git diff --check`.
- [x] Run fresh code-review and modularity-assessment checkpoints over the updated diff; fix surviving blocking or worthwhile in-scope findings.
- [ ] Commit and push the verified closeout to the existing feature branch, then rerun PR-completion readiness without landing unless the exact-head gate is satisfied.
