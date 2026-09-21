# Change Specification: V2 Target Horizon Market State

- **Change ID**: `425-v2-target-horizon-market-state`
- **Status**: Active
- **Complexity**: `large` (live schema-v4 scope)

## Outcome

Execute V2.28 development-only optimization for target/horizon choices and market-state feature/transform families for Programme #393 from the frozen WORK-425 handoff, without opening protected 2023+ confirmation, prospective paper, Saxo SIM, or LIVE evidence.

## Authority and scope

- L3 registration authority: GitHub #399 comment `5657156330` (target/horizon/label space) and GitHub #400 comment `5657158817` (market-state feature/transform space).
- Executable registry authority: `config/v2_variable_registry.json`, registry `programme-393-v2-variable-registry-v1`.
- Pre-score execution contract: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue425-search-plan-v1.json`.
- Harness authority: landed #424 implementation on the verified Programme #393 development-harness tree.
- Owned/shared/excluded paths and integration ownership: `scope.json`.

## Requirements mapping

- `src/commodity/v2_optimization.py` executes only the registered #425 target/horizon, bounded market-state, transform, and material interaction search using nested chronological development evidence.
- `tests/test_v2_optimization.py` verifies evidence-boundary failure, plan/axis coverage, PIT-safe transforms, target translations, selection eligibility, and reusable harness behavior.
- Trial/result artifacts remain development-only, retain failures, and bind dataset/code/search-plan identity.

## Acceptance

1. Search space is frozen before scoring and validates against the landed V2 registry.
2. Candidate selection uses strictly prior chronological inner evidence; outer blocks are evaluation-only for that selection step.
3. All scoring is capped at `2022-12-31`; reserved confirmation, true-forward, prospective paper, Saxo SIM, and LIVE evidence remain unread.
4. Monthly net-return/risk diagnostics, simple controls, and the pre-2023 V1 development comparator are recorded with the trial ledger.
5. Focused verification and the live KIS lifecycle gates pass before promotion/landing.

## Risks and recovery

- Risk: research multiplicity or accidental leakage can create a false development winner; mitigated by preregistered bounded stages, chronological inner-only selection, immutable attempt history, and hard evidence cutoff.
- Risk: long optimization execution can be interrupted; mitigated by deterministic trial IDs, append-only resumable ledger, and repository-local checkpoints.
- Recovery: rerun from the same committed code/search-plan identity and retained ledger/checkpoints; never repair a failed configuration after observing its result.

## Out of scope

- Fundamentals/weather/cross-market optimization (#426), broad model/foundation-specialist optimization (#427), fusion (#428), trading structure (#429), sizing/risk (#430), and execution/adaptation (#431).
- Any confirmation, prospective paper, SIM, or LIVE promotion claim.
