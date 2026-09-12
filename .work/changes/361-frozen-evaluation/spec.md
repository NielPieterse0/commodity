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
- `scripts/research/run_phase7_prospective_operations.py` is the operational entrypoint. It removes raw caller-supplied decision creation, manual outcome settlement and caller-controlled `recorded_at` from the CLI; rejects caller-supplied specialist outputs, market-source identity and execution-price evidence; remains fail-closed until pinned TimesFM/Kronos inference plus internal Databento session-price derivation are integrated; and keeps the tested append-only decision/session/outcome helpers behind that operational boundary.
- `tests/test_phase7_frozen_evaluation.py` provides focused freeze/chronology evidence.
- `tests/test_phase7_prospective_operations.py` verifies derived-decision binding, daily risk accounting, persistent kill state and settlement identity binding.
- `tests/test_phase7_prospective_decision_derivation.py` verifies outcome-blind derivation, the fixed five-session horizon, pre-2023 training isolation and source-freshness failure behavior.
- `.work/changes/361-frozen-evaluation/phase7-freeze-audit.json` is generated machine evidence for the pre-prospective freeze audit.
- `.work/changes/361-frozen-evaluation/phase7-serving-preflight.json` records the current fail-closed serving readiness: Databento retained through 2026-08-12 only, no September covering triple, and no verified specialist runtime/latency proof.
- `docs/reference/research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.md` is the human projection.

## Acceptance boundary

This bounded change may establish the frozen candidate and prospective evidence contract. A pre-first-observation audit found that the Phase-5 Kronos path modifier was development-tested only on a frozen 96-origin sampled path set and the landed Phase-7 contract did not define a future path-availability rule. That is an outcome-independent feasibility defect: no prospective decision may count until an L3 serving-contract refreeze resolves it and lands on the default branch. Activation also requires measured proof that the pinned specialist serving runtime can generate and durably record the decision before the frozen planned fill, plus internal source-derived daily execution/session evidence; the supported CLI cannot accept backdated timestamps, manual execution prices or manual outcome settlement. Missed origins must be skipped rather than backfilled. Phase 7 still cannot complete until the preregistered prospective evidence minimum is actually accumulated, and Phase 8 remains ineligible until that exit criterion is met.

## Safety boundary

- Protected 2023+ outcomes remain unread during this change.
- Historical foundation-model-dependent evidence is not relabeled as pristine confirmation.
- Live trading remains prohibited by `config/trading-policy.json`.
- Any material post-result change requires a new scientific identity rather than mutation of this freeze.