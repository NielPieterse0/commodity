# Phase 5 Stacking Policy Implementation Plan

> Execute through live KIS lifecycle; scientific authority remains issue #359 + frozen Phase-4 handoff.

**Goal:** Select one bounded long/short/flat policy candidate using nested chronological prior-OOS evidence only.

**Architecture:** Reuse frozen Phase-2 market baseline forecasts/execution semantics and committed Phase-4 specialist ledgers. Add a new pure Phase-5 policy module and one research runner; do not modify Phase-2/4 implementations.

## Global constraints

- Stay inside `scope.json`.
- End evidence no later than 2022-12-31; protected confirmation remains unopened.
- Freeze candidate families, thresholds, primary criterion and search budget before scoring.
- Preserve every tried configuration/failure and all outer-block selections.
- Keep operator risk capacity fixed and separate signal abstention from risk enforcement.
- Treat TimesFM one-step quantile calibration as non-authoritative for the five-session target.

### Task 1: Freeze inputs and candidate contract

- [ ] Verify Phase-2 baseline identity and Phase-4 artifact hashes/keys.
- [ ] Define the exact bounded candidate grid from the four frozen hypotheses only.
- [ ] Freeze primary selection score, hard constraints, tie-breaks and search budget.
- [ ] Write tests that reject post-2022 evidence, unknown specialists and outer-fold leakage.

### Task 2: Implement policy/replay primitives

- [ ] Build PIT specialist join and target-matched prior-OOS uncertainty state.
- [ ] Map baseline + admitted modifiers to bounded continuous target position.
- [ ] Charge costs from position/contract changes and preserve explicit position state.
- [ ] Emit signal-abstention, risk-shutdown, timing, horizon and equity attribution.
- [ ] Support standard fixed-risk replay and a diagnostic continuous no-kill replay.

### Task 3: Execute nested selection

- [ ] Select policy settings from prior OOS blocks only and freeze before each outer block.
- [ ] Preserve all search attempts/failures and selected path evidence.
- [ ] Run remove-one-specialist ablations and cost sensitivity.
- [ ] Report long/short P&L, turnover, MDD, concentration and kill/flat attribution.
- [ ] Select one Phase-6/7 candidate only under the frozen criterion.

### Task 4: Reconcile durable evidence

- [ ] Write `phase5-stacking-policy-v1.json` and update programme ledgers without overstating evidence.
- [ ] Run affected tests, canonical verification and one final review through KIS.
- [ ] Commit → PR → exact-head CI → merge → reconcile #359 once through.
