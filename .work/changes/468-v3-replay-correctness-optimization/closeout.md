# Closeout: V3 Replay Correctness Optimization

## Implemented scope

- Corrected the full future-invariance proof boundary and preserved strict point-in-time semantics.
- Replaced repeated replay/dataframe work with cached score tensors, reusable candidate decision plans, compact NumPy replay inputs, incremental rich surfaces, and batched execution-scenario replay.
- Added a compact serial replay engine and removed the quadratic matured-outcome rescan with an order-preserving pending-outcome heap.
- Preserved exact replay semantics against the corrected reference path and kept later/protected data inaccessible.
- Retained reproducible performance and invariance evidence for the six-month development block.

## Implementation evidence

- Source parent: `c1c0ddbf3c0e01552c4722ece9ad4d2f90177e10`
- Verified staged tree: `52be4af88af052e62ae7abebcd2cfab6d936f4a5`
- Focused verification: 28/28 replay and runner tests passed.
- Full repository verification: 1,179 passed, 12 skipped; Ruff, git-whitespace, public-repository hygiene, documentation, experiment, programme-inference, research-metrics, and quantitative-research checks passed.
- Review closure: controller, runner/audit integration, test-quality, and replay-performance slices reviewed; the sole material performance finding was fixed and re-reviewed clean.
- Future invariance: PASS for all 288 candidate/scenario replays, structural phase prefixes, meta prefix, oracle predictor prefix, and primitive-oracle predictor prefix.
- Performance evidence: 96 candidates × 3 scenarios candidate replay benchmark completed in 135.12s after 96.58s preparation; single-candidate three-scenario batching measured 3.21x faster than legacy repeated replay.

## Provider and landing evidence

- Pull request exact head: pending publication.
- Provider-native GitHub Actions: pending publication.
- Merge / landed revision: pending publication.
- Documentation / Work reconciliation: pending merge.
- Cleanup: pending merge.

## Research return, when applicable

- This change optimizes and verifies the #465 V3 six-month replay engine without introducing additional December-driven controller tuning.
- Scientific controller changes remain separate; #470 owns the validated negative matured current-instance path-P&L add gate.
- Jump-regime research remains separate from #470 and from this closeout.

## Residual items

- No implementation or verification blockers remain before publication.
