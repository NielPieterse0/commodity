# Closeout: Pit Physical Balance

## Implemented scope

- Added predictor-only BHLR real-time-vintage extraction for dry production, working storage and total consumption with exact member-hash validation and strict month-end PIT availability.
- Added a Phase-3 runtime that reuses Phase-2 market/execution semantics, proves the frozen baseline replay, scores the single frozen challenger, and runs diagnostic-only remove-one sensitivities.
- Added canonical Programme-003 development evidence while keeping 2023+ protected confirmation unopened.

## Implementation evidence

- Frozen Phase-2 replay: +$26,040 aggregate net P&L with exact block-by-block identity/P&L match.
- PIT physical challenger: +$18,500; incremental -$7,540. Block deltas: 2017–18 -$11,250; 2019–20 $0; 2021–22 +$3,710.
- Challenger max drawdown 5.05% versus baseline 7.66%; P&L remained below the 95% risk-survival floor.
- Winter Nov–Mar incremental P&L -$7,050; non-winter -$490. Frozen volatility-regime deltas: low +$185; mid -$4,275; high -$3,065.
- PIT coverage 100% over 3,088 market-feature rows with zero missing physical rows.
- Disposition: not retained; both predeclared survival routes failed. Protected confirmation accessed: false.
- Governed repository verification: passed on the full working tree (`scripts/verify.ps1`): 598 passed, 7 skipped; documentation, research-integrity, data-authority, hygiene and git-whitespace checks passed.
- Specialist review closure: passed with no material findings. Exact implementation commit `fce8c8480dfe9d569a1f3a000e679cbc86bf106c` received complete code-quality review; full behavioral surface received complete test-quality review; documentation received complete documentation review.

## Provider and landing evidence

- Pull request exact head:
- Provider-native GitHub Actions:
- Merge / landed revision:
- Documentation / Work reconciliation:
- Cleanup:

## Research return, when applicable

- Upstream L3 authority: GitHub issue #357 comment `5626442162`.
- Canonical result: `research/programmes/003-natural-gas-trading-decision-system/phase3-pit-fundamentals-v1.json`.
- Programme decision: reject the compact PIT physical block and continue with the frozen Phase-2 market-only baseline.
- Scientific escape/re-entry: none; implementation stayed inside the L3 source, feature, timing, target, risk and protected-data contract.

## Residual items

- The final scope-only Work Management identity repair is committed as `b89606fc8fc0a6c2df57b5cd40ae71b3b5884ac3` and passed canonical repository verification (598 passed, 7 skipped) plus a no-findings code-quality review.
- Publication is blocked by a KIS project-routing defect, not by Phase-3 science or implementation. `derive_promotion_ready(WORK-357)` resolves the registered Commodity worktree beneath the `kis-mcp` project root instead of the Commodity project root and fails because the resulting candidate scope does not exist. `bind_task_handoff_change` also rejects the actual registered Commodity worktree, while Work Management still reports the frozen handoff with `change_id=null`.
- The supported sync PR workflow therefore reports `PROMOTION_HANDOFF_MISSING`; no raw Git/GitHub bypass was used. Retry the KIS handoff binding/PromotionReady derivation when project routing is corrected, then create the exact-head PR, pass CI, merge, reconcile WORK-357/#357 and clean the worktree.
- Phase 4 / #358 depends on #357, so it must not be activated before this closeout dependency is satisfied.
