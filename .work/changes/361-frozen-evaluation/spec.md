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
- `scripts/research/run_phase7_prospective_operations.py` is the operational entrypoint for that frozen ledger. It requires the decision-time input snapshot identity, forecast identity/value, target window, intended contract/position, fill rule, cost profile, risk state and source-freshness/completeness facts before a decision can be appended; later settlement must bind those exact decision-time facts.
- `src/commodity/phase7_prospective.py` implements outcome-blind prospective market-baseline inference. It verifies the exact Phase-5 `origins.csv` byte identity before fitting, fixes `histgb-core-v1` candidate identity/parameters, the 12-feature core set, 504-row minimum, 10,000 MMBtu multiplier, five-session horizon and landed Phase-7 freeze timestamp, rejects any 2023+ training target or current realized outcome field, and binds the frozen training identity plus current-origin snapshot into the forecast identity.
- `tests/test_phase7_frozen_evaluation.py` provides focused freeze/chronology evidence.
- `tests/test_phase7_prospective_operations.py` verifies the stricter operational record and settlement identity binding.
- `tests/test_phase7_prospective_baseline.py` verifies exact frozen-training identity, outcome blindness, candidate immutability and input-bound forecast identity.
- `.work/changes/361-frozen-evaluation/phase7-freeze-audit.json` is generated machine evidence for the pre-prospective freeze audit.
- `docs/reference/research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.md` is the human projection.

## Acceptance boundary

This bounded change may establish the frozen candidate and prospective evidence contract. It cannot complete Phase 7 until the preregistered prospective evidence minimum is actually accumulated. Phase 8 remains ineligible until that exit criterion is met.

## Safety boundary

- Protected 2023+ outcomes remain unread during this change.
- Historical foundation-model-dependent evidence is not relabeled as pristine confirmation.
- Live trading remains prohibited by `config/trading-policy.json`.
- Any material post-result change requires a new scientific identity rather than mutation of this freeze.