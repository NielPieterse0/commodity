# V2.39 Jump × Curve Short-Regime Plan

**Goal:** Freeze the smallest Block-1-derived short-vs-flat edge candidate and test it without retuning on chronological Blocks 2-4.

## Sequence

1. Rebind P0-P9 evidence to the exact landed #470 generation and preserve L5 source hashes.
2. Close P8 conservatively: record the adaptive-search/multiplicity boundary and withhold Block-1 confirmatory significance.
3. Build one evaluator for A/B using the frozen PIT state semantics, continuous position path, roll turnover, costs, low-liquidity missed-fill stress, and 1.0/1.5 exposure diagnostics.
4. Require exact Block-1 reconstruction and economics before later-block scoring is possible.
5. Prove detector/lifecycle prefix future-invariance by mutating future state and execution inputs.
6. Freeze runner hash, block dates, A/B definitions, notable-edge gates, Candidate-B extra gates, and terminal dispositions in `design-freeze.json`.
7. Commit the pre-OOS freeze.
8. Execute Blocks 2, 3, and 4 once with no branch-specific retuning.
9. Apply the automatic frozen disposition: B, A, or reject/materially weaken.
10. Persist final research records, reconcile Programme 004 line/evidence/decision ledgers, verify, review, and publish through KIS.

## Constraints

- No protected 2023+ access.
- No interpreting Block 1 as independent confirmation.
- No outcome-driven change to the A/B evaluator or gates after the freeze commit.
- No broad V3 controller retuning in this slice.
