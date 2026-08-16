# #82 — Kronos-only challenger preparation

## Status and boundary

This slice is **preparation only** while #15 remains open. It does not authorize or perform V2 empirical execution, model fitting, prediction generation, data acquisition, tuning, feature execution, or results-driven design.

Empirical release requires, in order: #15 closed/reconciled; #81 frozen; #88 independent activation audit passed. A failure at any gate leaves #82 blocked.

## Role

#82 is the standalone Kronos market-layer component control. It tests only whether the predeclared Kronos representation/forecast adds robust out-of-sample information against the strongest comparable V1 control under the exact #81 target, split, data/PIT, comparator, and #78 metric contract.

It is not the fusion claim and may not add indicator families, alternate model families, provider expansion, new geographies, or compensating search.

## Authority bindings

- Model enablement/pins/runtime owner: `config/models.json#models.kronos_mini`.
- Current adapter/interface evidence: `src/commodity/kronos.py#KronosMiniAdapter`.
- Metrics/comparability owner: `contracts/research_metrics.schema.json` and `artifacts/research-metrics/longitudinal-ledger.json`.
- Executable V2 inherited context owner: frozen #81 candidate records when available.
- This directory is preregistration evidence only; it does not become a second mutable owner for those values.

## Frozen Kronos-specific design

The exact observed checkpoint and tokenizer revisions are captured in `preparation-contract.json` as a base-revision snapshot and MUST match `config/models.json` at activation. Any mismatch blocks execution and requires a pre-result contract revision plus renewed #88 review.

The permitted adapter input is strictly expiry-aware OHLCV with columns `open`, `high`, `low`, `close`, `volume`. No exogenous indicator, fundamental, cross-market, Europe/Norway, or future-known field may enter #82.

Input construction is bound to `config/data_sources.json#canonical_contract_schema` and the continuous-series policy owned by `config/assumptions.json`. Raw rows retain `trade_date`, `contract_id`, and `expiration`; the adapter receives only OHLCV, indexed from the frozen #81 `trade_date` representation. `contract_id` and `expiration` remain in the input manifest for every row. The active roll policy must still match the authority at activation; the base revision records `volume_crossover_dte_v1`, with no stored price adjustment and no cross-contract returns.

For each prediction cutoff, the context is deterministically the most recent `min(512, N)` PIT-eligible rows, using all available rows when `N < 512`. OHLCV is cast to float64 without scaling. No imputation, interpolation, forward fill, or silent dropping is permitted. Invalid/missing/non-finite OHLCV, negative volume, invalid OHLC bounds, duplicate/non-increasing timestamps, or unresolved timezone semantics block execution. If a short deterministic context is rejected by the pinned adapter/checkpoint, that is a failed run rather than permission to change the window.

The currently observed inference call is frozen as `T=1.0`, `top_p=0.9`, `sample_count=1`, CPU, and `max_context=512`. These values are not tuning knobs after activation.

Because `T`, `top_p`, and `sample_count` are currently hard-coded in `src/commodity/kronos.py` rather than owned by `config/models.json`, #82 MUST remain blocked until #88 confirms an immutable authority path for them. Agent 4 does not repair that ownership drift in this preparation slice.

## Inherited #81 fields

The following are deliberately unresolved here and MUST be populated only from the frozen #81 contract: candidate ID, exact code/config revision, dataset ID/vintage/hash, OOS window, target/horizon, prediction/target timestamp semantics, evaluation protocol and split IDs/hashes, PIT availability rule, strongest comparable V1 control, primary/secondary metric IDs, materiality threshold, uncertainty/significance rule, multiple-testing rule, and any program-wide cost ceiling.

No local fallback is permitted. A null/missing/mismatched inherited field is an execution blocker.

## Prediction mapping

The adapter may forecast only the next #81-governed horizon. If #81 freezes the V1-comparable `target_ret_1` / one-session log-return target, the preregistered scalar mapping is `log(predicted_close_next / observed_close_at_cutoff)`.

If #81 freezes any incompatible target or horizon, #82 MUST NOT improvise a mapping. The contract must be revised before results exist and re-audited by #88.

## Seed and reproducibility semantics

The primary stochastic seed is fixed at `0`. Before the primary run, the future executable runner must set Python, NumPy, and PyTorch RNGs to `0`; CUDA is prohibited by this contract. No alternate performance seed is permitted after observing results.

One exact replay with the same seed and identical immutable inputs is permitted solely for reproducibility. Its prediction artifact must hash-identically to the primary artifact; otherwise the run fails reproducibility and no performance claim is eligible.

## Compute ceiling

- CPU only; no GPU escalation.
- No fitting/fine-tuning/adaptation passes.
- At most one primary inference pass plus one exact reproducibility replay.
- Maximum context remains 512 observations.
- Hard wall-clock ceiling: 6 hours per pass, 12 hours total for the two-pass reproducibility pair.
- External market/data acquisition cost: USD 0 inside #82.
- If the frozen #81 programme-wide cap is lower, the lower cap wins.

Exceeding a compute ceiling is a failed run, not permission to shorten the OOS window, change checkpoint, alter sampling parameters, or tune the model.

## Checkpoint/network preflight

The empirical run may not silently fetch or substitute model/tokenizer artifacts. Before release, #88 must verify that the pinned model and tokenizer revisions are locally resolvable and hash-recordable. Missing artifacts stop the run; artifact installation/cache preparation must occur outside the measured run and before its immutable environment manifest is sealed.

## Deterministic artifact contract

After release, the candidate namespace is `artifacts/v2/kronos-only/<candidate_id>/`. The run must emit, at minimum:

- `input-manifest.json`: inherited #81 dataset/vintage/split/PIT identities plus ordered input-row identity/hash.
- `model-manifest.json`: model/tokenizer IDs and revisions, dependency/runtime identity, inference parameters, seed semantics, and artifact hashes.
- `predictions.parquet`: prediction timestamp, target timestamp, fold identity, observed cutoff close, predicted OHLCV fields, and governed scalar prediction.
- `metrics.json`: only #81/#78-authorized metric identities and comparator references.
- `run-manifest.json`: exact code/config revision, environment, timestamps, compute usage, disposition, and failure reason if applicable.
- `reproducibility.json`: primary/replay hashes and equality result.
- `hashes.json`: SHA-256 identities for every governed output artifact.

No result may be promoted until these identities are complete and the longitudinal #78 ledger records the stage with explicit comparability/disposition.

## Stop/failure rules

Execution must stop or remain blocked if any activation dependency is unresolved; any inherited #81 hard-context identity is absent; checkpoint/tokenizer/config identity mismatches; the inference knobs remain mutable; a required input is non-PIT, missing, non-finite, unordered, duplicated, or outside the permitted OHLCV schema; the pinned artifacts are unavailable locally; runtime exceeds the compute ceiling; output timestamps/schema are invalid; predictions are non-finite; the replay hash differs; or governed artifact hashing fails.

A negative, null, or inferior result is **not** a failure condition that permits another search. It is preserved. No post-result checkpoint swap, seed search, sampling change, horizon change, input substitution, model-family search, or compensating feature addition is permitted in #82.

## Release checklist

#82 may begin empirical execution only when every field in `preparation-contract.json.activation_gate` is true and #88 records an independent pass against the frozen #81 records. Until then, `execution_authorized` remains false.
