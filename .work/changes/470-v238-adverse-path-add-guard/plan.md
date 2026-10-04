# V2.38 Adverse Path Add Guard Implementation Plan

**Goal:** Add the single causal #470 scale-up guard without broad controller tuning.

**Architecture:** Reuse the existing V3 current-position-instance economic-path state. Apply the guard only after hard-risk precedence and only when a proposed same-side target would increase absolute exposure.

## Constraints

- No date-, month-, direction-, candidate-, or December-specific logic.
- No new signal family or scoring change.
- No weakening of the strict PIT boundary.
- No changes to #468 replay-engine semantics.

## Execution

1. Map the exact V3 transition owner and current-instance P&L lifecycle.
2. Add focused failing tests for negative/positive/zero path state, prior-instance isolation, strict maturity, hard-risk precedence, unchanged lifecycle actions, and future invariance.
3. Implement the minimal guard plus explicit reason code.
4. Run focused and affected V3 tests.
5. Run the exact same six-month 96-candidate x 3-scenario replay and full future-invariance proof.
6. Compare October/November/December, base/stress, ADD count, and unintended lifecycle changes against the frozen baseline.
7. Run independent code, architecture/PIT, and test-quality review; fix findings in one bounded pass.
8. Freeze the revised controller if acceptance holds.
