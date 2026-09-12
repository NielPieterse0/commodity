# Change Specification: Phase 7 Frozen Evaluation

- **Change ID**: `361-frozen-evaluation`
- **Status**: Active
- **Complexity**: `large` from `scope.json`
- **Risk triggers**: `money`, `persistent_state`

## Outcome

Implement the bounded Phase-7 freeze/evidence-classification contract for Programme 003 without opening protected historical outcomes or authorizing live capital.

## Scientific authority

The canonical scientific requirements are owned by:

- GitHub issue #361 and its predecessor-folding comment;
- `research/programmes/003-natural-gas-trading-decision-system/phase5-stacking-policy-v1.json`;
- `research/programmes/003-natural-gas-trading-decision-system/phase6-controlled-expansion-v1.json`;
- `research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.json`.

This change record does not restate or extend those scientific requirements.
## Repository mapping

- `scripts/research/run_phase7_frozen_evaluation.py` verifies frozen identities, reproduces the already-consumed development ledger, rejects protected-period leakage, and enforces a two-stage prospective ledger in which the frozen decision is hash-chained before its later outcome settlement.
- `scripts/research/derive_phase7_prospective_decision.py` derives the frozen HistGB forecast and policy action from verified pre-2023 training state plus decision-time inputs; caller-supplied forecast/position outputs and outcome fields are rejected.
- `scripts/research/run_phase7_prospective_operations.py` is the operational entrypoint. It removes raw caller-supplied decision creation, manual outcome settlement and caller-controlled `recorded_at` from the CLI; rejects caller-supplied specialist outputs, market-source identity and execution-price evidence; internally binds exact-source Databento histories, generates TimesFM/Kronos outputs through the pinned prewarmed runtime, derives the frozen pre-2023 market action from persisted position/risk state, records a cadence-consuming deadline miss instead of any late decision, derives daily Databento session evidence, automatically settles an episode only after exactly five gap-free verified session events reach the frozen target end, counts independent episodes with the preregistered earliest-non-overlap rule, and keeps episode-window economics informational while the daily session ledger remains the sole economic/risk gate. Activation remains fail-closed until real governed Linux Torch execution and measured deadline proof exist.
- `tests/test_phase7_frozen_evaluation.py` provides focused freeze/chronology evidence.
- `tests/test_phase7_prospective_operations.py` verifies derived-decision binding, daily risk accounting, persistent kill state, missed-origin cadence integrity and settlement identity binding.
- `tests/test_phase7_prospective_decision_derivation.py` verifies outcome-blind derivation, the fixed five-session horizon, pre-2023 training isolation, source-freshness failure behavior, exact Phase-4 specialist context/profile geometry and retained runtime-asset identity binding.
- `.work/changes/361-frozen-evaluation/phase7-freeze-audit.json` is generated machine evidence for the pre-prospective freeze audit.
- `.work/changes/361-frozen-evaluation/phase7-serving-preflight.json` records the current fail-closed serving readiness: Databento retained through 2026-08-12 only, no September covering triple, exact local specialist assets machine-verified and a prewarmed CPU serving wrapper implemented, but no governed Linux Torch execution or measured durable-write latency proof.
- `docs/reference/research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.md` is the human projection.

## Acceptance boundary

This bounded change may establish the frozen candidate and prospective evidence contract. A pre-first-observation audit found that the Phase-5 Kronos path modifier was development-tested only on a frozen 96-origin sampled path set and the landed Phase-7 contract did not define a future path-availability rule. The outcome-independent L3 serving-contract refreeze and episode-settlement rule were completed before any prospective or protected outcome access and landed as PR #381 (`a8dfeb67614945f3e764d8ade39ac9f7eeb63095`), merge `969c2ec957e249d8b405a4b73d851e6321c5639b`; that exact landing is now the frozen prospective serving boundary. Episode settlement is an exact five-session derivation from persisted session evidence; the daily session ledger remains the only economic/risk gate, while episode sums are diagnostic evidence only. Operational specialist inference is now wired from exact-source Databento histories through the pinned prewarmed TimesFM/Kronos runtime and frozen pre-2023 market decision path, but prospective activation remains blocked until that runtime actually executes under governed Linux Torch, durable decision-write latency fits the frozen pre-fill window, and fresh exact Databento coverage exists. The supported CLI cannot accept backdated timestamps, manual execution prices or manual outcome settlement, and a missed fresh origin consumes its frozen cadence slot without retrospective backfill. Phase 7 still cannot complete until the frozen prospective evidence minimum is actually accumulated; Phase 8 remains ineligible until the exit criterion is met.

## Safety boundary

- Protected 2023+ outcomes remain unread during this change.
- Historical foundation-model-dependent evidence is not relabeled as pristine confirmation.
- Live trading remains prohibited by `config/trading-policy.json`.
- Any material post-result change requires a new scientific identity rather than mutation of this freeze.