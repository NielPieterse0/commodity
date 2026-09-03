# #155 effective-N and detectable-effect closeout

- Issue: #155
- Work record: `RES-155`
- Pull request: #188
- Exact reviewed head: `57400b49d167ff3eb23aac6d1062491d1b9ce103`
- Landed `main`: `9301b5ebcc953016fa9d91252e385b5e08dc261d`
- Exact-head GitHub Actions CI run `32587920047`: passed
- Local verification before review: 489 tests passed; Ruff clean; public-hygiene clean; power calculations independently recomputed; `git diff --check` clean
- Documentation reconciliation: post-merge complete at `9301b5ebcc953016fa9d91252e385b5e08dc261d`

Research disposition:
- Current 204-row OOS window is about 10.2 block-equivalent information units under the governed 20-session dependence assumption.
- Approximate 80%-power detectable RMSE improvement is 2.33% for one primary test and about 3.0–3.22% under conservative multiplicity scenarios.
- Detecting about 1% RMSE improvements needs roughly 1,106–2,121 comparable rows, depending on multiplicity.
- Longer 2–5-session or weekly targets do not add independent information over the same calendar span unless the mechanism produces a stronger signal.
- Storage-event designs are statistically attractive if PIT-safe consensus history can be obtained; weather revisions remain attractive because deeper issued-forecast history may be available.
- Existing 2010–2026 Databento history is an upper-bound planning opportunity only; #149 retains authority over conditioning, candidate matching, and any reacquire/defer/reject decision.
- No new model was fitted, no prediction was generated, and no unconsumed OOS result was inspected.