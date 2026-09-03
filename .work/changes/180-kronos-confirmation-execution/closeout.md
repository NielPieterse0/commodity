# #180 corrected Kronos confirmation closeout

- Issue: #180
- Pull request: #186
- Exact reviewed head: `4a1f5e66432f444fd248549c5bcbd49a794292ac`
- Landed `main`: `12a823653b6ccfa355e653b9526898269c802ff9`
- Execution runner commit: `207596eb8501b7f44071f8c7564c4752f38404b3`
- Exact-head GitHub Actions CI run `32565666515`: passed
- Local verification: 489 tests passed; Ruff passed; `git diff --check` passed; generated #180 artifacts LF-only
- Documentation review: no findings
- Documentation reconciliation: post-merge complete at `12a823653b6ccfa355e653b9526898269c802ff9`

Scientific disposition:
- Mini RMSE: `0.06160964344136518`
- Small RMSE: `0.05529307513018762` — best Kronos checkpoint
- Base RMSE: `0.06648013639481652`
- Frozen zero-return RMSE: `0.0453230577562102`
- Frozen Phase-D HistGB RMSE: `0.04650733779411404`
- All three Kronos checkpoints materially failed both frozen RMSE baselines; no checkpoint passed robustness.
- Frozen decision: `drop_direct_one_step_kronos` for this target/grain.
- No post-result tuning, calibration, fusion, seed search, checkpoint rescue, or metric/multiplicity regrouping occurred.
