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

- `scripts/research/run_phase7_frozen_evaluation.py` verifies frozen identities, reproduces the already-consumed development ledger, rejects protected-period leakage, and validates prospective-record timing/identity.
- `tests/test_phase7_frozen_evaluation.py` provides focused acceptance evidence.
- `.work/changes/361-frozen-evaluation/phase7-freeze-audit.json` is generated machine evidence for the pre-prospective freeze audit.
- `docs/reference/research/programmes/003-natural-gas-trading-decision-system/phase7-frozen-evaluation-v1.md` is the human projection.

## Acceptance boundary

This bounded change may establish the frozen candidate and prospective evidence contract. It cannot complete Phase 7 until the preregistered prospective evidence minimum is actually accumulated. Phase 8 remains ineligible until that exit criterion is met.

## Safety boundary

- Protected 2023+ outcomes remain unread during this change.
- Historical foundation-model-dependent evidence is not relabeled as pristine confirmation.
- Live trading remains prohibited by `config/trading-policy.json`.
- Any material post-result change requires a new scientific identity rather than mutation of this freeze.