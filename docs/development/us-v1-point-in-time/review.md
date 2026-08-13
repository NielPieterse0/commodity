# U.S. V1 Point-in-Time Availability Review

## Scope

- Development level: **Medium**.
- Pull request: **#9 — Build U.S. V1 point-in-time availability layer**.
- Base: `main` at `7429a88b47235a98b27f537c840f7eee11374486`.
- Implementation reviewed through `bf0f771b53e7e056cc7625baabcb4f0d5b258b36` before this review-only commit.
- Review covered specification, plan, implementation, tests, source-policy configuration, documentation, licensing boundaries, and fresh CI evidence.
- The requested specialist review workflow was applied directly because no independent code-review subagent is exposed in this session.

## Requirement reconciliation

| Requirement | Implementation / evidence | Result |
|---|---|---|
| R1 — Availability contract | `commodity.availability` emits/validates `observed_for`, `available_at`, `availability_status`, and `revision_status`; tests reject unresolved/ineligible rows. | Pass |
| R2 — EIA-930 timing | Demand uses EIA hourly UTC **hour-ending** timestamps plus configured reporting lag; demand forecast and generation use DST-aware `America/New_York` cutoffs. Current historical values remain `current_snapshot_revised_history`. | Pass |
| R3 — WNGSR timing | Regular Thursday 10:30 Eastern releases and the published exception registry are configuration-owned. Coverage is bounded from 2025-01-01 through the currently published 2026-11-25 exception; dates outside coverage fail closed unless explicitly overridden. Current history remains revision-bearing. | Pass |
| R4 — Issued weather timing | `issued_at` remains separate from `available_at`; absent exact availability is conservatively reconstructed as 6 hours plus a 10-minute consistency margin. Issued runs are marked immutable; reconstruction alone is not canonical. | Pass |
| R5 — Evidence modes | `canonical`, `research_pit`, and `screening` enforce distinct availability/revision eligibility and carry `canonical_evidence` / `revision_leakage_risk` labels. | Pass |
| R6 — As-of joins | Backward `merge_asof` uses only rows available at or before prediction cutoff; tests prove future rows are not selected and risk metadata survives joins. | Pass |
| R7 — Configuration ownership | Source timing rules, exception bounds, and research eligibility are owned by `config/data_sources.json`; regression test checks ownership. | Pass |
| R8 — Massive remains gated | Regression test confirms `non_display_backtesting_rights_verified=false` and `backtest_evidence_allowed=false`; no redistribution or execution authority changed. | Pass |

## Findings closed during review

1. **Blocking — WNGSR exception coverage was initially too broad.** The first configuration extended exception-registry coverage through 2026-12-31 even though the currently published schedule only establishes exceptions through 2026-11-25. Added a failing regression, narrowed the bound, and kept explicit end-boundary overrides working.
2. **Blocking — EIA-930 demand initially treated the API timestamp as hour-start.** EIA documents EIA-930 hourly timestamps using the hour-ending convention. Added a failing regression and changed demand availability from `period + 1 hour + lag` to `period + configured lag`.
3. **Major — evidence metadata was initially dropped by as-of joins.** Added regression coverage and preserved availability/revision/evidence/risk metadata through the joined dataset.
4. **Major — WNGSR dates after known exception coverage were initially inferred.** Added bounded coverage and fail-closed behavior.
5. **Minor — Ruff import spacing and Markdown trailing whitespace.** Corrected and reverified.

No unresolved blocking finding remains in the reviewed implementation.

## Residual risks and explicit exclusions

- Current historical EIA-930 and WNGSR snapshots may contain values revised after their original publication. They remain **screening-only** and carry revision-leakage risk until original/revised vintages are reconstructed.
- Monthly EIA production, demand, trade, and spot publication/revision vintages remain unresolved.
- Exact historical Open-Meteo source availability is unverified. The 6-hour + 10-minute rule is a conservative research reconstruction for immutable issued runs, not canonical evidence.
- WNGSR schedule reconstruction outside the configured exception-registry coverage remains unresolved by design.
- Massive non-display/backtesting entitlement remains unresolved and independent of this availability layer.
- CI still reports pre-existing `src/commodity/massive.py` Pandas/NumPy timedelta deprecation warnings; they are unrelated to this slice and do not affect current test outcomes.

## Security, data handling, and recovery

- No credentials, raw Massive market values, or restricted data were added to Git.
- No raw snapshots, database state, schema migration, or execution policy were modified.
- Recovery is a normal PR/commit revert; the slice is additive and configuration-driven.

## Verification evidence

Fresh CI on implementation head `bf0f771b53e7e056cc7625baabcb4f0d5b258b36`:

- `python -m pytest -q` → **112 passed**, 12 pre-existing Massive deprecation warnings.
- `python -m ruff check .` → **All checks passed**.
- `git diff --check HEAD^1 HEAD` → **passed**.

A final CI run is required after this review record is committed; completion status should reference that final PR head rather than this earlier implementation head.
