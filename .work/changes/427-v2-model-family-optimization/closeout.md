# Closeout: V2 Model Family Optimization

## Implemented scope

- Completed the frozen #427 development-only V2.30 model-family optimization through 2022-12-31: bounded core-model search, retained-feature matched ablations, OI conditional-role evaluation, volatility/tail specialists, and foundation-model/comparator lanes.
- Persisted 180 new governed #427 trials: 150 core trials plus 30 specialist trials. Protected confirmation/forward/paper/SIM/LIVE evidence remained untouched.
- Retained six development advantages for downstream #428 conditional/regime work: range breakout (+0.000450 mean monthly net-return delta), volume confirmation (+0.000314), trend strength (+0.000274), positioning (+0.000068), jump intensity (+0.000500), and volatility-of-volatility (+0.000610).
- The strongest new #427 specialist was volatility-of-volatility, followed by jump intensity. The combined all-stable feature set was not retained as a standalone bundle.

## Implementation evidence

- Scoring identities: runner SHA-256 `96658dcec1c3c0ffb7fde600a9dd38e027b23b71835991763b48c5b380b5c1c6`; model code SHA-256 `3934a1f4a0bc69163eae1c19998d161f72b6a89c315a306fa6fcf23913fcbd63`; V2 code SHA-256 `810c16c9af4c7a8a0e096dcab3e3d94e6fb8b6e0c818547a9efd7b4bcd27c2ee`.
- Focused/scientific evidence: no-scoring preflight PASS with 3,088 feature rows, 3,897 session rows, zero failures, and protected confirmation untouched; preflight SHA-256 `2c2c4b7351d7c13b14983e5a52c1b866a1d335186871cc6979a1d3970c0c9c58`. Final result SHA-256 `28ebe85aa3ae3d6991bfee94dd2463f3b980286712ed2704e512f4842c540f9f`; core result SHA-256 `83f64399a1b457c21312de36570926e352d3e46d5848247a242f8656a464ab8a`; specialist trial ledger SHA-256 `90d3012658c699a96f801774cd9f7af0a093f724f57091c255c9adaff4c241ec`.
- Canonical verification: `scripts/verify.ps1` PASS with 920 passed / 7 skipped and one known duplicate-name test warning; documentation generation, rule verification, evidence integrity, programme/research checks, Ruff-integrated checks, and Git whitespace all passed.
- Review closure: exact staged review of the 1,228-line #427 research runner completed with no findings and explicitly confirmed PIT/protected-evidence/preregistration/row-matching/trial-accounting/hash-binding boundaries. Exact staged model/test review completed with three reported findings; two were closed as false positives because the GARCH expression already computes `prior_return * prior_return` and feature preparation copies the input frame before mutation, while the fixed 45-candidate assertion is deliberate preregistration freeze enforcement. No code change was required from review.
- PromotionReady / reusable evidence: pending exact commit identity and KIS lifecycle promotion.

## Provider and landing evidence

- Pull request exact head:
- Provider-native GitHub Actions:
- Merge / landed revision:
- Documentation / Work reconciliation:
- Cleanup:

## Research return, when applicable

- Upstream L3 authority: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue427-prereg-v1.json`.
- Exact implementation/landing identity returned to research lineage: pending exact commit/merge identity.
- Any scientific escape/re-entry: none; implementation and scoring remained within the frozen #427 scientific contract.

## Residual items

- Provider/landing fields remain pending until exact-head PR CI and merge complete.
