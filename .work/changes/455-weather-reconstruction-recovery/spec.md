# Change Specification: Weather Successor Baseline

- **Change ID**: `455-weather-reconstruction-recovery`
- **Status**: Active
- **Complexity**: use live KIS schema-v4 classification

## Outcome

Preserve #426 as historical weather evidence that is not exactly reproducible from the recovered archive. Freeze the current complete PIT-safe NCAR/GDEX GFS 0.25-degree reconstruction as the #455 successor weather baseline, establish a new development-only weather result from it, and test whether the already-admitted MISO power signal adds matched marginal value to that successor baseline.

## Scientific authority

- Historical recovery evidence remains `issue455-recovery-plan-v1.json` plus `issue455-weather-replay-validation-v1.json`; neither is rewritten to imply exact #426 reproduction.
- New pre-score authority is `issue455-successor-baseline-plan-v1.json`.
- Frozen inherited semantics remain `issue426-search-plan-v1.json`, `issue426-optimization-plan-v3.json`, `issue426-weather-feature-contract-v1.json`, the exact reconstructed #426 market inputs, and the #425 matched controls.
- Power source/selection authority remains the closed #452 MISO evidence and `issue452-result-v1.json`; no new power-source search is authorized.
- Successor weather identity is the complete 2,908-day GDEX archive bound by manifest/lineage hashes in the new plan. Twenty-three unavailable archive leads remain explicit omissions with no fill.

## Requirements and acceptance

1. Successor scoring must reject any weather archive whose frozen manifest, lineage, source, support, extraction, omission, or protected-evidence identity differs from the preregistration.
2. Rerun the registered weather-family development search and outer evaluation against the successor archive, preserving every attempted trial and matched control.
3. Persist successor baseline PnL, trade count, forecast diagnostics, selected representations/roles, dataset identity, code identity, and trial-ledger hash.
4. Reacquired MISO inputs, if required for execution, must reproduce the tracked #452 144-month archive/member lineage and 4,374 usable-day/9-exclusion PIT audit before interaction scoring.
5. Execute power × weather only after the successor weather baseline is frozen and complete; compare it with its matched successor-weather control on the same chronological outer blocks.
6. Keep protected confirmation, true-forward, prospective paper, Saxo SIM, and Saxo LIVE evidence unopened. This change may establish only development matched marginal value, not a confirmed edge.
7. Focused tests, governed change checks, KIS-required reviews, and exact-head verification must pass before promotion.

## Out of scope

- Further exact #426 weather archaeology as a prerequisite for new research.
- Rewriting #426 as if its original effective weather archive had been recovered.
- New power-source discovery, performance-based publication timing changes, post-2022 tuning, or protected/live evaluation.
