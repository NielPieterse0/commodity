# #78 Agent 1 — Implementation Plan

1. **Contract (R1–R5):** add a JSON Schema for the governed longitudinal ledger, including stage context, metrics, comparison policy, interpretations, evidence, and closeout state.
2. **Identity/comparability (R1–R2):** add deterministic context identity plus fail-closed comparability classification with explicit hard-context and methodology movement reasons.
3. **Regression logic (R3–R4):** add direction-aware materiality checks against the previous stage and best comparable stage, then enforce interpretation/tracking requirements.
4. **Closeout integration (R5–R6):** add ledger validation, generated Markdown summary, and CLI check/summary commands without changing model or evaluation calculations.
5. **Tests (R1–R6):** cover schema validity, identity stability, non-comparability, methodology movement, regression thresholds, best-so-far comparison, fail-closed closeout, and generated summaries/CLI.
6. **Review/verify:** inspect the exact diff, run focused then full verification, request architecture/API/test review, fix blocking findings, and publish only this isolated Agent 1 change for integration.

## Recovery

The change is additive except for bounded CLI wiring. Rollback is deletion of the new contract/module/tests/docs plus removal of the CLI import/handlers/parser entries.
