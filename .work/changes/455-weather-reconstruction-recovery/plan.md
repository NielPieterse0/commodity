# Weather Successor Baseline Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Preserve the failed exact #426 weather recovery as historical evidence, freeze the complete PIT-safe reconstructed GDEX 0.25-degree archive as a new #455 successor weather baseline, rerun the registered development weather evaluation, then test MISO power × weather against the matched successor baseline.

**Architecture:** Keep `issue455-recovery-plan-v1.json` and `issue455-weather-replay-validation-v1.json` unchanged as historical recovery evidence. Introduce `issue455-successor-baseline-plan-v1.json` as the new pre-score authority. Reuse the frozen #426 market inputs, weather feature semantics, search space, chronological blocks, and matched controls; reuse the closed #452 MISO source/selection authority. Add a separate #455 interaction gate rather than weakening the old #452 exact-reproduction gate.

## Global constraints

- Stay inside `scope.json`; keep all outcome evidence development-only through 2022-12-31.
- Freeze the current GDEX source identity, manifests, omissions, grid/extraction semantics, and hashes before successor scoring.
- No outcome-driven weather-source archaeology, source switching, anchor tuning, interpolation, or omission repair after the successor freeze.
- Reacquired MISO raw inputs must reproduce the tracked #452 archive/member lineage before use; do not reopen power source research.
- Protected confirmation, true-forward, paper, Saxo SIM, and Saxo LIVE evidence remain unopened.

## Execution

1. Record the successor-baseline preregistration and update governed #455 scope/spec/tasks.
2. Add tests and implementation for an explicit #455 successor-baseline interaction gate while preserving #452 behavior unchanged.
3. Rerun the complete registered #426 weather-family search/outer evaluations against the frozen successor archive and persist its trial ledger/result.
4. Reacquire the deterministic 2011-2022 MISO capture only as needed, verify all 144 archive identities/member lineage against #452 evidence, and build the same PIT-safe power frame.
5. For each common outer block, keep the successor weather-selected configuration/role fixed, keep the closed #452 selected power representation fixed, and add only power × weather interaction terms.
6. Compare candidate PnL/trades/diagnostics and mean monthly return with the exact same successor-weather configuration on the same power-supported rows with only the interaction terms ablated; retain only positive matched marginal value.
7. Generate durable research/docs evidence, run focused/KIS-selected verification and reviews, then prepare exact-head PR/CI/merge through KIS.
