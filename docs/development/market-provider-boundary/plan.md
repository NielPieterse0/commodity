# Canonical Market Provider Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each behavior change and superpowers:verification-before-completion before closeout.

**Goal:** Make canonical futures acquisition provider-neutral, enforce true per-session M1-M12 preservation, and record a bounded Massive subscription-value audit.

**Architecture:** Core CLI loads a canonical futures provider through a tiny convention-based loader and consumes a two-method protocol. Expiry-rank capture-window calculation lives in provider-neutral market-domain code. Massive authentication, REST behavior, normalization, retries, and snapshot plumbing live in a single adapter module.

**Tech Stack:** Python 3.11+, pandas, requests, scikit-learn for local screening evidence only, pytest, Ruff.

## Global Constraints

- Raw Massive values remain ignored and outside Git.
- No licensing/evidence promotion and no LIVE-trading authority change.
- No new dependency.
- New provider-specific runtime code must be removable without editing `commodity.cli` or `commodity.market_data`.

---

### Task 1: Provider-neutral contract and loader

**Files:**
- Create: `src/commodity/canonical_provider.py`
- Modify: `src/commodity/cli.py`
- Test: `tests/test_canonical_provider.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `CanonicalFuturesProvider` protocol and `load_canonical_provider(provider_id: str)`.
- Loader convention: provider id `x` resolves module `commodity.x_provider`, which must expose `create_provider()`.

- [ ] Write failing tests proving the loader resolves by convention, rejects an invalid provider id, and the canonical CLI parser exposes provider-neutral `capture-canonical-market-v1 --curve-contracts 12` with no provider pacing option.
- [ ] Run targeted tests and verify RED.
- [ ] Implement the protocol/loader and migrate CLI handlers to provider-neutral methods.
- [ ] Run targeted tests to GREEN.

### Task 2: Provider-neutral rank-bounded capture windows

**Files:**
- Modify: `src/commodity/market_data.py`
- Test: `tests/test_market_data.py`

**Interfaces:**
- Produces: `build_contract_rank_windows(contracts, start_trade_date, end_trade_date, max_contracts)` returning `(contract, fetch_start, fetch_end)` rows.

- [ ] Write failing tests for M1-M2 membership windows across four sequential expiries, invalid `max_contracts`, missing expiry metadata, and first-trade-date clipping.
- [ ] Run targeted tests and verify RED.
- [ ] Implement deterministic expiry-sorted windows: contract `i` becomes eligible after contract `i-max_contracts` expires; clip to requested range and first/last trade dates.
- [ ] Run targeted tests to GREEN.

### Task 3: Isolate and bound the Massive adapter

**Files:**
- Create: `src/commodity/massive_futures_provider.py` from the existing provider implementation.
- Delete: `src/commodity/massive.py`
- Modify: `tests/test_massive.py`

**Interfaces:**
- Produces: `create_provider()` returning an adapter that implements `CanonicalFuturesProvider`.
- Adapter `capture_archive(...)` accepts `max_contracts`, uses `build_contract_rank_windows`, and records `max_contracts` plus `curve_selection=expiration_rank_per_trade_date` in its request/manifest.

- [ ] Write failing tests proving the adapter fetches each contract only during its rank-eligible window and its manifest records rank-bounded semantics.
- [ ] Run targeted tests and verify RED.
- [ ] Move provider implementation into the adapter module, add the two-method adapter class/factory, replace the absolute expiry cutoff with rank windows, and preserve checkpoint/hash/fail-closed behavior.
- [ ] Run Massive tests to GREEN.

### Task 4: Neutralize current core/provider coupling

**Files:**
- Modify: `src/commodity/market_data.py`
- Modify: `README.md`
- Test: `tests/test_market_data.py`

**Interfaces:**
- Core readiness messages refer to the configured canonical provider rather than Massive by name.

- [ ] Write a failing assertion that readiness reasons contain no concrete provider name.
- [ ] Run targeted test and verify RED.
- [ ] Make readiness wording provider-neutral and update the current preservation command in README.
- [ ] Run targeted tests to GREEN.

### Task 5: Persist subscription-value evidence and removal boundary

**Files:**
- Create: `docs/development/market-provider-boundary/evidence.json`
- Create: `docs/development/market-provider-boundary/review.md`

**Evidence:**
- Snapshot SHA-256 from the existing ignored manifest/canonical artifact.
- 500 sessions; 11,200 rows; 5,988/6,000 M1-M12 coverage; 5,209 extra rows beyond M12.
- Settlement-vs-close difference statistics.
- Leakage-safe next-session return/direction and absolute-return screening metrics, explicitly `screening` only.
- Current official plan comparison: Basic free/2y; Starter $29/2y; Developer $79/5y; Advanced $199/7+y; NYMEX session flat-file history starts 2017.
- Decision: do not pay for Starter for research history; Developer is the only next plan worth a bounded history-depth test; Advanced is not justified yet.

- [ ] Write evidence without raw licensed values or credentials.
- [ ] Record runtime removal surface and distinguish it from immutable historical development records.

### Task 6: Review and verification

**Files:** all changed files.

- [ ] Run targeted suites for provider loader, market data, Massive adapter, and CLI.
- [ ] Run full `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check` and a secret-pattern scan.
- [ ] Run code review and modularity review; fix all blocking findings and rerun affected tests.
- [ ] Publish only onto a GitHub branch created from current remote `main`, because the local Work runtime cannot network-fetch the post-PR-9 merge commit. Verify the remote PR diff contains only this slice and CI passes on the exact head.
