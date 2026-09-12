# Change Specification: Phase 5 Stacking Policy

- **Change ID**: `359-stacking-policy`
- **Status**: Active
- **Complexity**: large

## Outcome

Implement the repository mapping for WORK-359 without widening the frozen scientific design or opening protected 2023+ confirmation.

## Authority and scope

- Scientific authority: GitHub issue #359 and frozen WORK-359 handoff fingerprint `91c42252dd053d690ca5947545067e91d4824869c14223fb6c12c35792fa0f8c`.
- Phase-4 handoff authority: `research/programmes/003-natural-gas-trading-decision-system/phase4-foundation-specialists-v1.json` → `phase5_handoff`.
- Research-line constraints: `research/programmes/003-natural-gas-trading-decision-system/lines/001-trading-system/line.json` → `stopping_rules.phase5`.
- Owned paths and change classification: `scope.json`.

## Requirements mapping

- `src/commodity/stacking_policy.py`: deterministic bounded policy, nested selection helpers, replay/accounting, diagnostics.
- `scripts/research/run_phase5_stacking_policy.py`: frozen candidate search, chronological execution, durable evidence emission.
- `tests/test_stacking_policy.py`: chronology, boundary, accounting, abstention-vs-kill, selection and ablation acceptance evidence.
- Programme JSON owners: exact Phase-5 result, decisions, evidence, revisit state and line interpretation.

## Acceptance

1. Specialist/policy fitting and selection use only prior OOS evidence; outer outcomes never train their own policy.
2. Only the four frozen Phase-5 specialist hypotheses are admissible; Chronos/Moirai and post-hoc families are excluded.
3. Policy output is bounded long/short/flat sizing inside unchanged operator risk limits and includes position-change costs.
4. Ledgers distinguish signal abstention from risk shutdown and include a continuous no-kill diagnostic replay.
5. Diagnostics include long/short contribution, turnover, drawdown, cost sensitivity, concentration, timing/latency, target/horizon, specialist ablations and adaptive-history accounting.
6. Exactly one candidate is selected under a frozen primary criterion without protected confirmation.

## Risks and recovery

- Risk: repeated development search overfits the policy. Recovery: fixed candidate grid/budget, retained attempt history, inner-only selection and simplicity tie-breaks.
- Risk: old risk kills masquerade as abstention. Recovery: separate requested-position and enforced-risk-state ledgers plus no-kill replay.
- Risk: one-step TimesFM intervals are misused as five-session uncertainty. Recovery: use only target-matched prior-OOS residual uncertainty or exclude that role if calibration cannot be defended.
- Recovery is repository-local and reversible through the governed change worktree.

## Out of scope

- Protected 2023+ confirmation, live trading, operator risk-capacity optimization, new foundation-model families, Chronos/Moirai policy inputs, Phase-6 horizon/global-gas expansion, and Phase-8 production hardening.
