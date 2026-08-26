# #198 — TimesFM 2.5 zero-shot preregistration

## Purpose

This is the pre-result design for the first Commodity TimesFM experiment. It evaluates Google TimesFM 2.5 as an independent zero-shot benchmark on the existing PIT-safe, same-contract Henry Hub evaluation identity. It does not authorize inference.

The machine-readable preregistration is `docs/development/timesfm-zero-shot-preregistration/contract.json`. It is experiment-local evidence only: the already-consumed global model and V2 candidate registries remain byte-identical and are not refrozen by #198. Any later decision to adopt TimesFM as a repository model requires a separate governed registry change.

## Exact upstream identity

- Source: `google-research/timesfm` at `3dae50b20d7a724981e8ea36cda75578f80dd2dc`.
- Checkpoint: `google/timesfm-2.5-200m-pytorch` at `1d952420fba87f3c6dee4f240de0f1a0fbc790e3`.
- `model.safetensors` SHA-256: `2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8`.
- The source pin includes the July 2026 autoregressive quantile flip correction.
- Loading is local-files-only after a separate source/checkpoint preflight.

No PyPI floating version, `main` checkpoint revision, XReg, LoRA, PEFT, or fine-tuning is permitted in this experiment.

## Data and target boundary

The scored identity is the frozen Phase-D 204-row OOS set: 2025-10-03 through 2026-08-11, dataset `us-ng-pit-0c0a39b36692`, SHA-256 `0c0a39b...c80a45f`.

At every prediction cutoff, the selected contract comes from the existing derived continuous-series policy. History is restricted to that contract and to rows already available then. The target date is the next trading-session date on the selected-path calendar, but the target contract remains the contract selected at the cutoff even if the path rolls on that next date. The exact same-contract target row must exist and become available strictly after the cutoff; otherwise the entire experiment fails closed with no row drop or substitution. Every scored row also requires at least 20 valid same-contract history bars. Cross-contract history and cross-contract target substitution are prohibited.

## Frozen model variants

Each of the context lengths 128, 256, 512, and 1024 is evaluated for three return-producing univariate representations: same-contract settlement level, log settlement, and same-contract settlement log return. The context is a cap, not a minimum: every row uses only the most recent history actually available for that contract at the cutoff.

Garman–Klass variance is a fourth, auxiliary volatility task and cannot rescue the primary next-session return claim.

Inference is fixed to PyTorch, CPU, horizon 1, `torch_compile=false`, input normalization on, continuous quantile head on, flip invariance on, quantile-crossing correction on, and q10 through q90. TimesFM 2.5 output index 0 is the mean and indices 1–9 are q10–q90; q50 is the point forecast.

No context or representation may be selected after results. All prespecified variants must be reported.

## Evaluation

Primary point-forecast comparisons are the 3 return representations × 4 context lengths against each of two governed primary baselines: zero return and Phase-D HistGB. These 24 comparisons form `F198_TIMESFM_ZERO_SHOT`; BH consumes the prespecified one-sided moving-block-bootstrap RMSE-improvement p-value, while Diebold–Mariano is confirmatory and does not enter BH.

Distributional evidence has its own closed 12-member family, `F198_TIMESFM_DISTRIBUTION_12`, against same-context empirical same-contract return quantiles. A distribution branch can pass only with BH-adjusted pinball-loss improvement plus the frozen central 60% and 80% coverage guards.

Complementarity uses a separate 12-member `F198_TIMESFM_FIXED_BLEND_12`: each variant is blended 50/50 with the frozen Phase-D HistGB return forecast and compared with HistGB alone. Blend weights are never fitted or changed after results. The corrected Kronos Small result is an error-reference only.

The volatility task reports RMSE, MAE, MASE, and QLIKE versus the frozen trailing-20-session mean Garman–Klass variance baseline. It is secondary descriptive evidence and cannot keep the return programme by itself.

## Decision and stop rule

TimesFM remains interesting only for a statistically credible point-forecast improvement, useful predictive-distribution calibration, or materially complementary errors that improve a separately governed future ensemble. Generic benchmark quality is not commodity-edge evidence.

If direct zero-shot TimesFM fails these roles, record the negative result. XReg, LoRA/PEFT adaptation, alternative horizons, longer contexts, ensemble fitting, or any post-result tuning requires a new experiment.

This freeze does not self-authorize inference. Prediction generation is prohibited until this design exists as an exact committed revision, source/checkpoint preflight passes, the frozen 204-row identity and same-contract coverage are reconstructed, and the execution tree is clean and committed.
