# Canonical Roll Policy and History Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task in this isolated worktree. Behavior changes use `superpowers:test-driven-development`; completion uses `superpowers:verification-before-completion`.

**Goal:** Validate the live Massive account, replace the unusable OI-dependent canonical roll candidate with a deterministic prior-volume + DTE policy, generate an auditable derived continuous series, and open only the evidence gates that the verified data and license actually support.

**Architecture:** Keep Massive HTTP/provider semantics in `commodity.massive`, canonical readiness in `commodity.market_data`, and roll selection/ledger logic in `commodity.rolls`. Raw per-contract rows remain authoritative; derived path, ledger, and returns are separate artifacts. Configuration records the policy and evidence prerequisites.

**Tech Stack:** Python 3.11+, pandas, requests, pytest, Ruff, JSON configuration.

## Global Constraints

- Start from `dc344c0` in `feat/canonical-roll-policy-and-history-validation` under `.work/`.
- Never emit or persist `MASSIVE_API_KEY`.
- Do not commit Massive market values unless redistribution rights are verified.
- Databento remains excluded; LIVE trading remains prohibited.
- Do not start serious model training in this slice.

### Task 1: Provider security and account evidence

**Requirements:** R2, R3, R12, R13
**Files:** `tests/test_massive.py`, `src/commodity/massive.py`, `config/data_sources.json`, `docs/THIRD_PARTY.md`, `docs/development/canonical-roll-policy-and-history-validation/account-validation.json`
- [x] RED: add a request test proving credentials are sent as `Authorization: Bearer ...` and never as `apiKey` query parameters.
- [x] GREEN: change Massive request authentication and preserve bounded pagination/error handling.
- [x] Record the 2026-08-12 live probe: aggregate boundary `2024-08-13`, fields present, no historical OI, observed pagination, and row-count/session checks; record values only as non-price capability metadata.
- [x] Persist a local ignored canonical sample and metadata; commit only its deterministic hash, date/contract coverage, row counts, schema fields, and exact re-fetch command.
- [x] Update third-party/licensing documentation so non-display/backtesting rights remain an explicit fail-closed requirement.

### Task 2: Deterministic volume + DTE roll policy

**Requirements:** R4â€“R11
**Files:** `tests/test_rolls.py`, `src/commodity/rolls.py`, `config/assumptions.json`

- [x] RED: test two-session strict prior-volume crossover, tie reset, missing-volume reset, 3-calendar-DTE forced roll, observed-session holiday handling, missing-current fallback, and no-later-contract failure.
- [x] RED: test ledger rows contain `trade_date`, `old_contract`, `new_contract`, `trigger`, `old_contract_dte`, `prior_current_volume`, `prior_next_volume`, and confirmation count.
- [x] RED: test the continuous-series return is null on initialization and every roll boundary.
- [x] GREEN: implement `volume_crossover_dte_v1` without removing the legacy dual-liquidity helper behavior needed by existing tests.
- [x] GREEN: add a derived continuous-series API that returns selected rows plus an explicit roll ledger and within-contract return column.
- [x] Register the exact policy parameters and edge-case semantics in `config/assumptions.json`.

### Task 3: Canonical readiness and operational wiring

**Requirements:** R13, R14
**Files:** `tests/test_market_data.py`, `tests/test_pipeline.py`, `src/commodity/market_data.py`, `src/commodity/cli.py`, `config/data_sources.json`, `README.md`
- [x] RED: readiness passes the data/roll methodology checks for `volume_crossover_dte_v1` when history and required volume are verified, but remains blocked when licensing is unverified.
- [x] RED: readiness fails for missing verified account depth, missing historical volume, unsupported roll policy, or any attempt to allow cross-contract returns.
- [x] GREEN: make readiness consume the explicit roll-policy owner and evidence prerequisites instead of hard-coding `dual_liquidity_crossover`/OI.
- [x] Update `doctor` to distinguish source/history readiness, roll-method readiness, and licensing readiness rather than collapsing them into one opaque flag.
- [x] Update README current state: data contract and roll methodology validated; canonical backtest promotion remains blocked only by unresolved Massive non-display/backtesting entitlement unless that entitlement is independently verified during this slice.

### Task 4: Review, verification, and PR preparation

**Requirements:** R1â€“R14
**Files:** all changed files plus `docs/development/canonical-roll-policy-and-history-validation/review.md`

- [x] Run targeted tests after each RED/GREEN cycle and keep the exact evidence in the review artifact.
- [x] Run the repository code-review and modularity-assessment gates if available; otherwise execute the base `develop-code` review contract and record the missing specialist.
- [x] Run `python -m pytest -q`, `python -m ruff check .`, and `git diff --check` on the final worktree state.
- [x] Confirm `git status` contains no `.env`, API key, raw Massive market data, or unrelated worktree changes.
- [x] Commit the exact verified tree and prepare PR #3; do not merge without the repository PR-completion gate.

## Traceability

| Task | Requirements | Primary evidence |
|---|---|---|
| T1 | R2, R3, R12, R13 | live account manifest, auth tests, licensing docs |
| T2 | R4â€“R11 | roll edge-case tests, ledger tests, return tests |
| T3 | R13, R14 | readiness/doctor tests and config ownership |
| T4 | R1â€“R14 | review artifact, full verification, clean diff/status |

## Stop Conditions

Stop canonical-evidence promotion if licensing rights, provider history, required volume, roll determinism, provenance, or cross-contract return safety cannot be verified. The implementation may still land with the gate closed if it truthfully records the remaining blocker.

