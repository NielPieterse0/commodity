# V1 Research Completion — Phase A Review

Program: GitHub issue #15. Phase A: #17. Baseline: `7b8546a3273a6c662848e0e285ca70559a2f7921`.

## Verdict

Phase A implementation is complete for the repository contract. Canonical per-contract history now has deterministic roll/curve derivation, PIT-safe availability handling, complete M1–M4 market-structure admission, roll-boundary-safe targets, and deterministic market-semantics lineage.

This does **not** promote Massive data to canonical backtest evidence. `non_display_backtesting_rights_verified=false` and `backtest_evidence_allowed=false` remain authoritative, so production canonical dataset construction continues to fail closed at the licensing/promotion gate.

## Requirement closeout

- **R1 — PIT contract panel:** source timestamps are preserved when present; otherwise only the explicitly configured conservative `trade_date_2359_utc` rule may reconstruct availability. Late curve quotes are masked without shifting later contracts into earlier ranks.
- **R2 — deterministic roll:** `config/assumptions.json` remains the only roll-policy owner. Selected-path and roll-ledger artifacts retain contract/trigger/prior-session evidence, and targets spanning a contract change are excluded.
- **R3 — market structure:** M1–M4 settlement/DTE plus adjacent spreads, M1–M4 slope and M1/M2 volume ratio are deterministic. Canonical family admission requires complete four-rank settlement/DTE evidence plus usable front-volume and derived curve fields.
- **R4 — dataset integration:** canonical mode adds `market_structure`; research-PIT proxy mode does not claim canonical market structure.
- **R5 — lineage:** manifests hash canonical input, selected path, roll ledger, curve features/audit, roll policy and market semantics. Representation metadata names exchange, product, session timezone, calendar, raw storage and no-adjustment semantics. The synthetic index is explicitly non-tradable.
- **R6 — provider neutrality:** core market/dataset code remains provider-neutral; no Massive/Databento adapter implementation is imported by the new logic.
- **R7 — cross-source honesty:** Databento remains quarantined. Its integrity-verified statistics stop at 2018-12-31 while Massive verified history begins in 2024, so no integrity-verified overlap exists and no cross-source agreement claim is made.

## Preserved-snapshot evidence

- Massive snapshot: 11,200 per-contract rows, 500 sessions, 2024-08-14 through 2026-08-12.
- Deterministic derivation: 500 selected-path rows, 24 roll events, 500 market-structure rows.
- Complete required M1–M4 market-structure rows: 500/500; zero missing required settlement, front-volume, ratio, spread or slope fields.
- Two derivation runs produced identical input/path/ledger/curve/audit/policy hashes. Exact hashes are recorded in `phase-a-evidence.json`.
- Availability is reconstructed only in memory for the preserved Massive CSV; raw snapshot files are unchanged.

## Review findings closed

1. **Important — incomplete family promotion:** canonical mode could initially claim `market_structure` with only M1–M2 evidence. Fixed by requiring complete M1–M4 settlement/DTE plus required volume/derived curve fields; regression tests cover missing ranks and missing volume evidence.
2. **Important — availability provenance:** pre-reconstructed rows with an explicit `availability_status` could be relabeled as source timestamps. Fixed by preserving a supported uniform existing status and failing closed on invalid/ambiguous status metadata.
3. **Correctness — cross-roll target:** the earlier generic close-return target could span a futures roll. Canonical targets now use the selected path's within-contract return and drop the predecessor observation when the next selected row is a roll boundary.
4. **Repository gate hygiene:** full Ruff exposed two pre-existing Phase 0 style findings in `evaluation.py` and `policy.py`; both received behavior-preserving cleanups and their affected tests passed.

## Review execution

Configured independent review backends were attempted on the final code shape. NVIDIA NIM failed with its backend error and Codex CLI failed with the existing `UnicodeEncodeError`; no automated-review approval is claimed. Manual exact-diff review therefore remained mandatory and produced the findings above. No blocking or important finding remains after remediation.

## Verification

- Focused market/dataset/roll suite: 52 passed before the final full gate.
- Full repository: **181 passed**.
- Ruff: passed.
- `git diff --check`: passed; Windows line-ending advisories only.
- Changed-file secret-pattern scan: 11 changed files scanned, 0 hits.

## External blocker retained

Canonical source mechanics are ready, but canonical backtest promotion remains blocked by the configured licensing/rights gate. Phase B may proceed on PIT-admissible research evidence without weakening that gate; no LIVE execution authority changes are part of Phase A.
