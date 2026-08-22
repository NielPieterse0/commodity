# #180 — Corrected Kronos three-checkpoint confirmation

## Decision

**Drop direct one-step Kronos for this target and grain.** None of Mini, Small, or Base passed the frozen keep rule against both the zero-return and Phase-D HistGB baselines. No tuning, calibration, fusion, metric regrouping, seed search, or checkpoint rescue was performed after results.

Authoritative machine-readable evidence:
- `artifacts/kronos-confirmation/kronos-180-corrected-three-checkpoint-v1/result.json`
- `artifacts/kronos-confirmation/kronos-180-corrected-three-checkpoint-v1/comparisons.json`
- `artifacts/kronos-confirmation/kronos-180-corrected-three-checkpoint-v1/run-manifest.json`

The authoritative execution runner commit is `207596eb8501b7f44071f8c7564c4752f38404b3`.

## Headline result

| Checkpoint | RMSE | MAE | Direction accuracy | Prediction/actual correlation |
| --- | ---: | ---: | ---: | ---: |
| Mini | 0.0616096434 | 0.0427640200 | 50.98% | -0.08110 |
| Small | **0.0552930751** | **0.0398376878** | 50.00% | -0.02436 |
| Base | 0.0664801364 | 0.0496662212 | 51.96% | 0.06019 |
| Zero-return baseline | 0.0453230578 | 0.0292674562 | n/a | n/a |
| Phase-D HistGB | 0.0465073378 | 0.0295768064 | 53.43% | -0.05802 |

Small was the best Kronos checkpoint, but it still missed zero-return RMSE by `0.0099700174` and Phase-D HistGB RMSE by `0.0087857373`. Both primary bootstrap confidence intervals were entirely negative, and both BH-adjusted p-values were `0.0022477522`, confirming deterioration rather than improvement.

Mini and Base also materially underperformed both frozen baselines. All three checkpoints failed every frozen period/regime robustness check against both baselines: zero positive periods and zero positive regimes for each checkpoint/baseline pairing.

## Checkpoint-size conclusion

Performance did **not** improve monotonically with model size. The RMSE ordering was Small (`0.05529`) < Mini (`0.06161`) < Base (`0.06648`), not the preregistered `Base < Small < Mini` ordering required to claim a checkpoint-size benefit.

Small did significantly improve on Mini inside the frozen nine-member family (`RMSE improvement 0.0063165683`, 95% bootstrap CI `0.0020363520` to `0.0107063573`, BH-adjusted `p=0.0053946054`). Base was worse than both Mini and Small. This pairwise checkpoint evidence does not rescue direct Kronos because Small still materially failed both external baselines.

## Laptop resource observations

| Checkpoint | Wall clock | Peak process RSS | Device |
| --- | ---: | ---: | --- |
| Mini | 188.2 s | 428 MB | CPU |
| Small | 327.0 s | 571 MB | CPU |
| Base | 501.6 s | 1.20 GB | CPU |

All checkpoints remained below the frozen 12-hour per-checkpoint cap and used zero paid compute.

## Execution provenance

The first Mini execution attempt reached prediction generation but failed before its prediction manifest or any evaluation because Windows peak-RSS telemetry used an incorrect API structure/calling declaration. The generated prediction file was never inspected, was moved to recoverable local quarantine, and was excluded from the authoritative run.

The telemetry-only defect was fixed and independently reviewed. Full verification then passed (`487` tests, Ruff, and `git diff --check`), the exact scientific preflight was rerun, and Mini → Small → Base was restarted from zero under commit `207596eb8501b7f44071f8c7564c4752f38404b3`.

The completed run preserved the exact #182/#183 freeze/release, 204 OOS rows, same-contract execution path, source/model/tokenizer hashes, inference profile, nine prespecified comparisons, BH family, baselines, and robustness rule. No intermediate checkpoint performance was inspected between Mini, Small, and Base.

## Research consequence

This experiment is evidence against using uncalibrated direct next-session Kronos close forecasts as a Henry Hub return component under the frozen setup. It does not establish that Kronos is useless for other targets or roles. Any alternative sampling profile, target, calibration, fusion, feature use, or trading application requires a new governed experiment rather than modifying #180 after the fact.
