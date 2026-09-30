# Change Specification: V2 Regime Fusion Confidence Decision Rules

- **Change ID**: `428-v2-regime-fusion-confidence-decision-rules`
- **Status**: Active — empirical execution complete; verification/review/landing pending
- **Complexity**: large

## Outcome

Execute bounded development-only V2.31 regime/state conditioning, signal fusion, calibrated confidence/disagreement, and TRADE-vs-ABSTAIN optimization while keeping protected 2023+ confirmation, paper, SIM, and LIVE evidence sealed.

## Authority and scope

- L3 scientific authority: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-prereg-v3.json`.
- V3 supersedes V2 before scoring because executable feasibility showed the 2017 meta-confidence history could not satisfy the frozen 100-train + 50-calibration minimum.
- Upstream frozen evidence identities are enforced by the runner against #427, #448, Phase 2, and Phase 5 artifacts.
- Owned/shared/excluded paths and base identity are defined by `scope.json`.

## Requirements mapping

- `src/commodity/v2_decision_optimization.py`: prior-only state fitting, persistence, fusion gates, calibrated meta-confidence, disagreement, TRADE/ABSTAIN application, and chronological policy selection.
- `scripts/research/run_issue428_decision_optimization.py`: source-bound preflight, inherited forecast reconstruction, matched replay, OI conditional lane, complete trial ledger, cost/risk/effective-sample diagnostics, ablations, and result persistence.
- `tests/test_v2_decision_optimization.py`: focused chronology, boundary, selection, conditional-state, meta-calibration, and ablation-support tests.

## Acceptance

1. The final no-scoring preflight is bound to the frozen preregistration, source cache, runner, decision code, model code, and V2 code and reports zero failures.
2. Every core policy attempt and OI incremental attempt is retained in the trial ledger, including preregistered ineligible meta-confidence years.
3. Candidate/control replay keeps forecast rows, costs, risk policy, chronology, and protected evidence boundaries matched; OI is decision context only and does not shorten inherited model training history.
4. Outer results report effective sample, cost sensitivity, calibration, signal-abstention versus risk shutdown, remove-one-input ablations, and stability.
5. Promotion follows only the preregistered main gate; conditional OI diagnostics cannot create a uniform-value claim.

## Risks and recovery

- Primary risks: temporal leakage, post-result threshold changes, mismatched candidate/control rows, underpowered abstention policies, and accidental access to protected evidence.
- Recovery: fail closed, preserve attempt history, supersede preregistration only before scoring for scientific-design changes, and rerun source-bound preflight whenever executable identities change.

## Out of scope

- 2023+ reserved confirmation, true-forward, paper, SIM, LIVE, leverage/sizing optimization, and post-result threshold tuning.
