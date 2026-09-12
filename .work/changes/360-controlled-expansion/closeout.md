# Closeout — Phase 6 Controlled Expansion

## Authority and boundary

- Parent programme: #353; phase issue: #360.
- Frozen comparator: Phase-5 nested two-year policy cadence.
- Preregistration was committed at `52ca632042e57266abe9d7440e35b9aa8e83a8d3` before Phase-6 scoring.
- Input: committed Phase-5 `policy-year-scores.csv`, years 2014-2022 only.
- Protected 2023+ confirmation was not accessed.
- No global-gas source, new model fit, policy-grid expansion, threshold search, or target-horizon change occurred.

## Result

- Frozen two-year path: standard net P&L $13,980; median yearly P&L -$2,305; worst year -$6,145; costs $4,530; max yearly drawdown 6.236%.
- Annual refit: standard net P&L $17,160; median yearly P&L -$715; worst year -$6,145; costs $3,540; max yearly drawdown 8.222%.
- Annual cadence passed net-P&L, median, worst-year and cost gates but failed the preregistered drawdown non-inferiority gate.
- Decision: reject annual refit as an incremental contributor; retain the frozen Phase-5 cadence.

## Interpretation

The cadence hypothesis produced economically better aggregate and median development performance but not risk-dominant evidence. The result therefore does not justify changing the frozen candidate. Phase 6 does not open global-gas expansion in the same adaptive test; the disciplined route is to carry the unchanged Phase-5 system to the next programme evidence stage.

## Implementation evidence

- Governed impact analysis found the bounded change confined to the declared Phase-6 research, runner, test, generated documentation and change-record paths.
- KIS code-quality review completed with no actionable findings and confirmed the preregistered gates, chronological prior-OOS selection and protected 2023+ boundary.
- Fresh canonical verification passed: `623 passed, 7 skipped`; documentation generation, rule verification, environment, durable-evidence, source/data authority, work-layout, repository hygiene, experiment/programme integrity, research metrics/memory, quantitative-research knowledge and git-whitespace checks all passed.
- The optional KIS test-quality reviewer route failed because qualified provider outputs were unusable/unavailable; this did not invalidate the deterministic acceptance suite or completed code-quality review.

## Durable evidence

- `.work/changes/360-controlled-expansion/phase6-preregistration.json`
- `.work/changes/360-controlled-expansion/phase6-controlled-expansion-result.json`
- `research/programmes/003-natural-gas-trading-decision-system/phase6-controlled-expansion-v1.json`
- `scripts/research/run_phase6_controlled_expansion.py`
- `tests/test_phase6_controlled_expansion.py`
