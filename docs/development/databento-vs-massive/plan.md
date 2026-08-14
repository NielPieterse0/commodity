# Databento vs Massive Futures Evaluation Implementation Plan

> **For agentic workers:** Resolve and load applicable execution, test-discipline, and verification skill IDs through the KIS MCP skills module; do not invoke skills through provider-specific or filesystem syntax.

**Goal:** Add a removable Databento historical-futures adapter and establish bounded, reproducible evidence for whether Databento materially improves the current Massive-based NG research data path.

**Architecture:** Keep `commodity.cli` and `commodity.market_data` unchanged. Add a provider-specific HTTP client/adapter at `commodity.databento_futures_provider`, use free metadata endpoints before any billable time-series request, normalize official CME statistics/definitions into the existing canonical contract schema, and keep provider-comparison evidence separate from canonical-provider selection.

**Tech stack:** Python 3.11+, requests, pandas, pytest, JSON/Markdown evidence; no new runtime dependency.

## Global constraints

- Use only `DATABENTO_API_KEY`; never copy/read it into committed files or logs.
- Local Work outbound networking remains prohibited; authenticated live probing must use an approved connector if one exists.
- No canonical-provider switch, licensing promotion, raw-value commit, model training, or LIVE execution change.
- Do not overwrite PR #9 point-in-time configuration when reconciling the stale local base; final PR must be rebased/reconciled onto current remote `main` through the KIS reviewable-PR workflow.

### Task 1 — Provider contract tests and HTTP client

**Requirements:** R1, R2, R3, R9
**Files:**
- Create `tests/test_databento_futures_provider.py`
- Create `src/commodity/databento_futures_provider.py`

**Test-first evidence:**
- missing `DATABENTO_API_KEY` fails without disclosing any key;
- HTTP Basic auth uses key as username with blank password and never puts the key in query data;
- metadata probe calls only free metadata endpoints and returns dataset/schema range plus bounded cost/count estimates;
- 401/402/403 fail closed with redacted provider errors.

**Checkpoint:** Run targeted tests RED, then minimal implementation GREEN.

### Task 2 — Databento statistics/definition normalization

**Requirements:** R4, R5, R9
**Files:** same adapter/test files.

**Test-first evidence:**
- definition rows resolve NG outrights with raw symbol + expiration;
- settlement `stat_type=3` uses `ts_ref` as canonical trade date;
- final settlement flag is preferred over preliminary messages for the same contract/session;
- cleared volume `stat_type=6` can join to the settlement session;
- missing final/usable settlement or expiration fails closed;
- canonical output validates with existing `validate_contract_history` / metadata contract.

**Checkpoint:** Targeted normalization tests GREEN without changes to provider-neutral core.

### Task 3 — Provider factory and bounded acquisition path

**Requirements:** R1, R3, R6, R7
**Files:**
- Modify `.env.example`
- Optionally add only additive provider-evaluation configuration that does not replace `market_canonical.provider`.
- Extend Databento adapter/tests.

**Test-first evidence:**
- `load_canonical_provider("databento_futures")` resolves through convention;
- provider factory implements both canonical protocol methods;
- archive/capture refuses billable retrieval unless a metadata cost probe is available and the requested scope is bounded;
- manifests contain source hashes/metadata but never credentials.

**Checkpoint:** Provider loader + Databento tests + existing Massive/provider suites GREEN.

### Task 4 — Account probe and provider benchmark evidence

**Requirements:** R3, R6, R7
**Files:**
- Create `docs/development/databento-vs-massive/evidence.json`
- Later create/update `review.md`.

**Steps:**
1. Verify an approved connector exists for authenticated Databento calls. If none exists, record `live_account_probe_status=blocked_runtime_network_boundary`; do not fabricate entitlement evidence.
2. Record official public capability evidence for `GLBX.MDP3`, definitions, statistics, settlement, cleared volume, open interest, date-range metadata, symbology, and cost estimation.
3. If authenticated connector access is available, run metadata-only calls first: datasets, schemas, dataset range, cost and record count for a tiny NG request.
4. Only after a successful near-zero/bounded cost estimate, capture the smallest useful NG sample and compare field/contract/session coverage against preserved Massive evidence.
5. Keep provider decision as `evaluate`, not `switch`, unless a later explicit user decision changes it.

**Checkpoint:** Evidence distinguishes public capabilities, account-specific observations, and unresolved licensing rights.

### Task 5 — Documentation and stale-state reconciliation

**Requirements:** R6, R7, R8
**Files:**
- Add concise current-state update to README/data manifest only if needed.
- Create `docs/development/databento-vs-massive/review.md`.

**Review gate:** No stale claim says Databento is canonical, entitlement-tested, free, or licensing-approved unless exact evidence proves it. PR #9 availability-layer documentation must survive final reconciliation unchanged except intentional additions.

### Task 6 — Review, verification, exact-main PR

**Requirements:** R8, R9

1. Run targeted Databento + canonical provider + Massive regression suites.
2. Run full pytest and Ruff.
3. Run `git diff --check` and a credential/secret-pattern scan.
4. Run KIS code-quality and architecture/modularity reviews; fix all blocking findings and rerun affected checks.
5. Resolve and load the canonical verification skill through the KIS MCP skills module, then verify the exact commit.
6. Commit on the isolated branch.
7. Use KIS `prepare_reviewable_pull_request` so the exact local tree is reconciled onto verified current remote `main`; verify the resulting PR diff contains only this Databento slice.
8. Verify fresh GitHub CI on the exact PR head and stop for review/merge approval.

## Integration sequence

T1 -> T2 -> T3 -> T4 -> T5 -> T6.

## Recovery

All changes are additive/provider-specific. Revert the PR to remove Databento. No database migration, canonical-provider switch, execution-policy mutation, or committed raw licensed data is introduced.

## Plan review approval

The user approved execution of this deterministic Databento-vs-Massive slice after PR #10 merge. Material scope expansion beyond this plan requires a new explicit decision.
