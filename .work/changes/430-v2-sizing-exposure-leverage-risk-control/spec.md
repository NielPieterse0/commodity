# Change Specification: V2 Sizing Exposure Leverage Risk Control

- **Change ID**: `430-v2-sizing-exposure-leverage-risk-control`
- **Status**: Implemented; verification/review pending
- **Complexity**: large
- **Risk triggers**: money

## Outcome

Execute #430 development-only sizing, exposure, leverage, and risk-control optimization against the fixed promoted policy while keeping protected confirmation and prospective evidence sealed.

## Authority and scope

- Scientific authority: GitHub issue #430 and frozen `issue430-prereg-v1.json` SHA `d1009575138536bd7a960ba0ac3cd993d8b33b1095cd3736bdd47bfade6ab016`.
- Registration boundaries: issues #409 and #410 permit bounded research-only sizing/leverage and risk-control optimization while operational paper/SIM safety remains non-optimizable.
- Parent evidence: frozen #429 parent and #459 promoted policy identified in the preregistration.
- Owned/shared/excluded paths: `scope.json`.

## Requirements mapping

- `src/commodity/v2_sizing_risk.py`: research-only sizing and causal risk-control replay with explicit contract, margin, and notional-leverage diagnostics.
- `scripts/research/run_issue430_sizing_risk.py`: prereg/hash enforcement, no-scoring preflight, full trial accounting, Stage-1/Stage-2 evaluation, and deterministic result generation.
- `tests/test_issue430_sizing_risk.py`: evidence-boundary, sizing, replay, causality, accounting, selection, and integration tests.
- `issue430-*.json/jsonl`: frozen preregistration, bound preflight, complete trial ledger, and deterministic development result.

## Acceptance

1. Protected 2023+ confirmation, prospective paper, SIM, and LIVE evidence remain unread.
2. Operational paper max remains one standard NG contract and fixed paper risk limits are not optimized or weakened.
3. Research sizing may use up to four contracts only with explicit capital, margin, cost, drawdown, and notional accounting.
4. All 318 declared outer×cost trials are ledgered with no post-result rescue grid.
5. Promotion requires cross-outer and higher-cost robustness, concentration control, margin bounds, and no hard-safety regression.
6. Dynamic allocation is separately compared against nearest fixed-exposure controls so exposure amplification is not mislabeled as allocation edge.

## Risks and recovery

- Primary risk: hidden leverage or path leakage could create artificial economics. Mitigation: causal replay tests, explicit leverage/margin diagnostics, parent/control reproduction, and frozen no-scoring preflight.
- Recovery: fail closed on identity/boundary mismatch; do not rescore after changing the frozen preregistration or bound implementation without a new governed research identity.

## Out of scope

- Protected confirmation scoring.
- Paper/SIM/LIVE size authorization or order submission.
- Synthetic options-implied state.
- Post-result candidate rescue or parameter expansion.
