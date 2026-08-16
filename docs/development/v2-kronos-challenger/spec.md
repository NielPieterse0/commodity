# #82 — Kronos-only challenger preregistration

## Status and boundary

#78 and #15 are closed/reconciled. The #82 preparation and non-empirical implementation are complete enough to bind into the corrected #81 freeze, but **empirical execution remains blocked** until #81 is re-frozen against the exact child revisions and #88 independently passes that exact freeze.

This work has not performed model inference, model fitting, prediction generation, research-data execution, new acquisition, tuning, or results-driven design.

## Role

#82 is the standalone Kronos market-layer component control. It may test only whether the preregistered Kronos representation adds robust out-of-sample information against the strongest comparable V1 control under the exact #81 target, split, dataset/vintage/PIT, comparator, and #78 metric contract. It is not the fusion claim and may not add indicator families, alternate models, provider expansion, new geographies, or compensating search.

## Frozen implementation and preparation separation

The preparation revision and executable implementation revision are intentionally separate identities. Corrected #81 must bind both independently.

- Preparation evidence: this directory / PR #96, at the exact refreshed head used by #81.
- Implementation: PR #100, exact head `a1d1c7cb46e698555a7c221d75537829c9c00c6b`.
- Implementation CI: GitHub Actions run `31932936638`, passed. Its synthetic PR merge commit has the same tree `75f6c1337e2f600d4ec0fa52ae232fc39e5a5736` as the exact child head, so the verified source tree is exact.
- Checkpoint/source preflight: GitHub Actions run `31932936671`, passed.
- Result-affecting implementation source-manifest SHA-256: `02083ca257d896c42db9d6e442e194c6ea353a5a78e8751d1fc46d971c586ff0`.

The child implementation SHA remains a frozen provenance identity. Because later integration necessarily creates a different repository commit SHA, runtime reproducibility is enforced by the bound result-affecting source manifest: the integrated runtime revision may differ only if the bound #82 implementation files and vendored Kronos source revision are byte/identity-equivalent. Any source-manifest change requires reopening the relevant binding and renewed #88 review before empirical inspection.

## Model and checkpoint authority

`config/models.json#models.kronos_mini` owns the Kronos runtime identity. The frozen implementation moves the already-preregistered inference values into that authority without changing them:

- vendored Kronos inference source: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`;
- model: `NeoQuasar/Kronos-mini` at `7fdcc628d87f325ccdbcae0a372622ca7e6813aa`;
- tokenizer: `NeoQuasar/Kronos-Tokenizer-2k` at `b22fb9cb30a2de2f77e8b617169cd756ba964a08`;
- CPU only, `max_context=512`;
- `T=1.0`, `top_p=0.9`, `sample_count=1`, `verbose=false`;
- no post-result mutation or seed/search alternative.

The measured run is local-files-only. The exact pinned `model.safetensors` artifacts were resolved and SHA-256 checked by the non-empirical preflight on the exact implementation source tree:

- model SHA-256 `a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c`;
- tokenizer SHA-256 `b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717`.

`src/commodity/kronos.py` rejects missing local cache authority, a missing pinned snapshot, or a hash mismatch before model loading. The measured run cannot silently fetch or substitute checkpoint bytes.

## Input and PIT contract

The permitted input is strictly expiry-aware OHLCV. Raw selected-series rows retain `trade_date`, `contract_id`, `expiration`, and `available_at`; only `open`, `high`, `low`, `close`, and `volume` cross the adapter boundary.

Input construction remains bound to `config/data_sources.json#canonical_contract_schema` and `config/assumptions.json#assumptions.continuous_series_policy`. The active roll policy must match `volume_crossover_dte_v1`; there is no stored price adjustment and no cross-contract target return.

For each prediction cutoff, context is deterministically the most recent `min(512, N)` PIT-eligible rows. No scaling, imputation, interpolation, forward-fill, silent row drop, implicit timezone localization, or context search is permitted. Invalid/missing/non-finite OHLCV, non-positive prices, negative volume, invalid OHLC bounds, duplicate/non-increasing timestamps, missing contract trace, naive/unresolved timezone semantics, or post-cutoff input fail closed.

## Inherited #81 fields

Corrected #81 remains the owner of the frozen dataset/vintage/hash, OOS identity, target/horizon, prediction and target timestamp semantics, split/protocol identities, PIT rule, strongest comparable V1 control, metric identities, materiality, uncertainty/significance, multiplicity, robustness, cost, and stop rules. #82 does not redefine them.

The implementation validates the V1-comparable `target_ret_1` / one-trading-session mapping and computes the governed scalar as `log(predicted_close_next / observed_close_at_cutoff)`. Any cross-contract target mapping blocks the run.

## Seed, reproducibility, and cost

The primary stochastic seed is `0` for Python, NumPy, and PyTorch; CUDA is prohibited. One exact replay with the same immutable inputs is permitted only for reproducibility. Primary and replay prediction artifacts must hash identically.

CPU only, no fitting/fine-tuning/adaptation, no paid compute, and no new paid data are allowed. The corrected #81 programme cap is authoritative and any lower cap wins.

## Artifacts and longitudinal evidence

The frozen namespace is `artifacts/v2/v2-82-kronos-only/`. After release, the governed run must emit deterministic input/model/run/reproducibility/hash evidence plus predictions and metrics, and must hand exact provenance to the #78 longitudinal metrics system for both `previous_stage` and `best_comparable` comparisons.

Lineage records both identities separately: (1) the exact child implementation revision and bound source-manifest SHA-256, and (2) the actual integrated runtime repository revision. The runtime source manifest must equal the #81-bound manifest; a different integration commit is acceptable only when the result-affecting #82 source bytes and Kronos submodule revision are unchanged.

## Stop/failure rules

Execution remains blocked unless corrected #81 binds this exact refreshed preparation revision separately from implementation SHA `a1d1c7cb46e698555a7c221d75537829c9c00c6b`, source-manifest SHA-256 `02083ca257d896c42db9d6e442e194c6ea353a5a78e8751d1fc46d971c586ff0`, and #88 independently passes that exact freeze. Checkpoint/config/source mismatch, failed local hash resolution, PIT/coverage/trace/timezone failure, cross-contract target construction, runtime/cost violation, invalid outputs, replay mismatch, or incomplete artifact/longitudinal identity fails closed.

A negative, null, or inferior result is preserved. It does not authorize checkpoint swaps, seed search, sampling changes, horizon changes, input substitution, model-family search, or compensating features.
