# V2 Regime Fusion Confidence Decision Rules Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Implement and evaluate the frozen development-only #428 decision-rule contract without crossing the protected evidence wall.

**Authority:** `research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-prereg-v3.json`.

## Global constraints

- Stay inside `scope.json` and preserve exact upstream evidence identities.
- Fit states, thresholds, calibrators, and selection only from chronologically prior development evidence.
- Keep candidate/control rows, inherited forecasts, execution costs, and risk rules matched.
- Treat OI as conditional decision context only; it must not alter inherited forecast training availability or support a uniform-value claim.
- Do not access 2023+ confirmation, true-forward, paper, SIM, or LIVE evidence.

## Implementation

- [x] Reconcile #427 landing evidence into the #428 record.
- [x] Freeze chronology-correct preregistration before empirical scoring.
- [x] Implement prior-only regime, persistence, fusion, confidence/disagreement, and TRADE/ABSTAIN primitives.
- [x] Implement final source-bound no-scoring preflight.
- [x] Implement 29-config core lane plus 3-config conditional OI lane, matched replay, cost/risk diagnostics, effective-sample checks, ablations, and complete trial accounting.
- [x] Run governed development-only scoring and persist result/ledger.
- [ ] Complete repository verification and specialist review; resolve findings without post-result scientific tuning.
- [ ] Commit, prepare reviewable PR, require exact-head CI, merge, reconcile, and clean through KIS.
