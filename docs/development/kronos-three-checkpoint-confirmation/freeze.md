# #182 — Corrected Kronos three-checkpoint freeze

## Purpose

This is the pre-result authority for #180. It creates a new experiment identity for Mini, Small, and Base on the corrected same-contract Kronos path. It does not rewrite, rescue, or reinterpret consumed #82 evidence.

The machine-readable authority is `config/kronos_confirmation.json`.

## What is frozen

- Experiment: `kronos-180-corrected-three-checkpoint-v1`.
- Models: `NeoQuasar/Kronos-mini`, `NeoQuasar/Kronos-small`, and `NeoQuasar/Kronos-base`, with exact model/tokenizer revisions and artifact hashes from `config/models.json`.
- Common inference: CPU, lookback 512, one trading session, seed 0, `T=1.0`, `top_p=0.9`, `sample_count=1`, `verbose=false`.
- Corrected execution: #178/#181 same-contract context, one target timestamp, no mixed-contract history, no cross-contract target return.
- Data: the exact 204-row Phase-D OOS identity already frozen by the activation contract.
- Benchmarks: zero-return and the frozen Phase-D V1 HistGB result.
- Evaluation: one shared metric/evaluator contract and one nine-member BH family fixed before predictions.

No checkpoint-specific tuning, calibration, seed search, or post-result metric changes are permitted.
## Release rule

#182 does not authorize inference. The frozen config deliberately cannot self-authorize execution. Independent issue #183 must audit the exact landed freeze and write `audit-release.json` binding the exact freeze SHA-256 before the #180 prediction entry point can construct any checkpoint adapter.

`commodity.kronos_confirmation.build_released_checkpoint_adapter` therefore fails closed while that audit record is absent, stale, failed, or points at a different freeze.

## Decision rule

Direct one-step Kronos is kept only if at least one checkpoint beats both frozen baselines on RMSE, has positive bootstrap lower bounds for both improvements, passes the prespecified BH threshold for both baseline comparisons, and passes the inherited period/regime robustness checks.

If all three materially fail the baselines, #180 records evidence against direct one-step Kronos at this target/grain and stops checkpoint-size search inside this experiment. Larger size is called an improvement only if RMSE is strictly ordered `Base < Small < Mini` on identical scored rows.

Any later tuning, alternative sampling profile, calibration, fusion, or trading use requires a new experiment.