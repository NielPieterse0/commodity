# Foundation Specialists Implementation Plan

> Execute through the live KIS lifecycle; issue #358 comment `5628520758` is the original L3 freeze, clarified by `5632161050` and extended by the closed-budget second-line amendment `5634786235`.

**Goal:** Qualify pinned Kronos and TimesFM 2.5 specialists, preserve their conditional clues, then exhaust the explicitly bounded second-line budget: Chronos-2 as the only new deployment-compatible family, Kronos-small as a capacity control, and Moirai-2.0-R-small as research-only/non-commercial comparator before final Phase-5 handoff.

## Constraints

- Stay inside `scope.json`; do not reinterpret L3 science here.
- Preserve Phase-2 market-only baseline and rejected Phase-3 physical result.
- Protected confirmation remains unopened.
- Reuse still-valid prior #294/#295 evidence only as consumed development/background evidence.
- TimesFM 3.0 pretrained weights are outside scope while non-commercial/non-production licensed.

### Task 1 — Identity, license and PIT controls

- [x] Freeze deployment-compatible specialist identities and contamination boundary on #358.
- [x] Add exact TimesFM 2.5 registry pin and provenance metadata.
- [x] Implement PIT-safe specialist feature validation/join and remove-one sets.
- [x] Add focused negative tests for post-cutoff generation, target leakage, unverified licensing and incomplete PIT coverage.

### Task 2 — Runtime qualification and feature generation

- [x] Verify exact pinned Kronos/TimesFM artifacts before inference; matching repository-local caches are hash-qualified and reused.
- [x] Generate first-line fold-safe specialist outputs without target/outcome access. TimesFM and one-step Kronos features are complete at 3,088/3,088 origins with exact model/source identities and protected confirmation untouched.
- [x] Add TimesFM probabilistic calibration/coverage diagnostics for the admitted q10/q90 outputs. The development diagnostic uses the next canonical same-contract settlement return: 2,980 evaluable origins, 108 terminal-contract origins excluded with no next settlement, and 83.02% empirical coverage versus 80% nominal.
- [x] Make the Phase-4 runner worktree-self-contained: remove the undeclared `duckdb` dependency and allow bounded Kronos-only resume without regenerating valid TimesFM evidence.
- [x] Harden resumable Kronos generation against concurrent writers after a duplicate live runner was observed: add an OS-backed exclusive checkpoint-writer lock, fail a second invocation immediately, and preserve the existing 2,256-row checkpoint unchanged while switching the active run onto the guarded implementation.

### Task 3 — Whole-system evaluation and role diagnostics

- [x] Compare market-only, +Kronos, +TimesFM and +both with unchanged execution/risk semantics; preserve the first-line result without promoting from raw aggregate P&L.
- [x] Run the mandatory combined remove-one diagnostic; removing Kronos improved the first-line combined aggregate.
- [x] Decompose TimesFM and Kronos conditional information by sign agreement/disagreement, side, magnitude/uncertainty, fold/year, predeclared volatility/trend/seasonal regimes, forecast disagreement/residual behaviour, and P&L concentration. Treat this as exploratory mechanism evidence, not a new promotion claim from already-seen development outcomes.
- [x] Run one bounded Kronos native-strength five-step sequence/path diagnostic because the first-line representation retained only one-step close return/range.
- [x] Preserve the provisional first-line Phase-5 hypotheses without selecting any policy: TimesFM baseline-short, Kronos baseline-long, Kronos sequence, TimesFM uncertainty.

### Task 4 — Closed-budget second-line extension

- [x] Freeze #358 amendment `5634786235` before any second-line score: Chronos-2 only new deployable family, Kronos-small capacity control, Moirai-2.0-R-small research-only comparator.
- [x] Pin model identities, artifact hashes, license status and pretraining-exposure boundary in canonical registries; explicitly prohibit Moirai production/commercial promotion under CC-BY-NC-4.0 weights.
- [x] Reuse the exact outcome-blind 96-origin three-block sample for fixed five-step second-line diagnostics; do not search representations, thresholds, policies or model families after outcomes are observed.
- [x] Run Kronos-small capacity-control path diagnostic on the exact Kronos-base sample/profile.
- [x] Run Chronos-2 fixed native five-step probabilistic/multivariate market-path diagnostic and mechanism summary; 96/96 completed, with no Phase-5 handoff from the tested role.
- [x] Run Moirai-2.0-R-small only as a research comparator using an isolated Python 3.11/uni2ts 2.0.0 runtime and exact-hash governed weight export; 96/96 completed and remains non-deployable under current licensing.
- [x] Freeze final Phase-4 handoff to #359 after preserving all positive and negative second-line evidence.
- [ ] Record final Phase-4 disposition durably, regenerate governed docs once on the final state, verify/review once, publish/merge/reconcile through KIS.
