# #154 — Kronos semantic audit

## Scope

This is a correctness audit of the current Kronos interface after the post-V2 representation work. It does not change model code, frozen #82 evidence, checkpoints, inference knobs, targets, or results.

Audited authority:

- Commodity base: `344fd10721dec0ce8083b476defc67a17b22326d`.
- Pinned Kronos source: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- Commodity adapter: `src/commodity/kronos.py#KronosMiniAdapter`.
- Frozen #82 contract: `src/commodity/v2_kronos.py` plus the #81 activation contract.
- Roll-safe correction: `src/commodity/roll_safe_market.py` from #133.

No model inference or performance inspection was performed.

## What one #82 prediction means

The Commodity adapter passes five raw columns in level units to the pinned upstream predictor: `open`, `high`, `low`, `close`, and `volume`. The upstream predictor deterministically derives a sixth `amount` field as `volume * mean(open, high, low, close)` before normalization.

For each input context, upstream Kronos computes a separate mean and standard deviation for each of the six fields, standardizes each field as `(x - mean) / (std + 1e-5)`, clips normalized values to `[-5, 5]`, generates tokens autoregressively, decodes them, then reverses the transform as `decoded * (std + 1e-5) + mean`. Therefore the returned `close` is back in the original price-level units. There is no price/return unit mismatch at this boundary.

Commodity then maps that returned next-close level to the evaluator with:

`log(predicted_close_next / observed_close_at_cutoff)`.

That output is a dimensionless log return. The frozen actual target is different in measurement source: next-session selected-contract **settlement-to-settlement** `target_ret_1`. The close-based prediction is intentionally an uncalibrated proxy; settlement reconstruction and calibration are prohibited by the frozen #82 contract.

## Horizon semantics

The #81 authority fixes the target and forecast horizon to one trading session, with the prediction cutoff after the current daily bar close and the target on the next selected-contract session. `governed_return_prediction` also blocks cross-contract target returns.

`KronosMiniAdapter.forecast` is a generic adapter and will accept any length of `future_index`; it does not itself enforce one step. The #82 execution contract therefore depends on the caller supplying exactly one next-session timestamp. The new audit test proves the one-step adapter/evaluator round trip for the governed usage, but this remains a caller-level constraint rather than a generic adapter invariant.

## Decoding and randomness

The frozen #82 settings are `T=1.0`, `top_p=0.9`, `sample_count=1`, CPU, seed 0.

The pinned Kronos source uses multinomial token sampling for both token stages. `sample_count` repeats the context into parallel sampled paths and averages decoded paths after generation. Consequently:

- `sample_count=1` is **one sampled forecast path**, not an argmax point forecast and not an average across alternative paths;
- the fixed PyTorch seed and exact replay make the consumed run reproducible, but the emitted scalar is still seed-conditioned stochastic decoding;
- the upstream README example uses the same `T=1.0`, `top_p=0.9`, `sample_count=1` profile;
- the upstream fine-tuning/backtest configuration uses `T=0.6`, `top_p=0.9`, `sample_count=5`, which averages five decoded paths.

This is not grounds to mutate consumed #82 after seeing results. It means #82 was a valid frozen one-sample candidate, but it was not the paper-backtest sampling profile. `config/models.json#kronos_confirmation_profile` already records the separate paper-faithful profile for a future diagnostic/confirmation experiment.

## Finding F154-01 — roll-safe context is not wired into the Kronos execution helper

**Severity: high for any future Kronos execution that calls `v2_kronos.build_pit_context` directly.**

#133 correctly added `build_same_contract_model_context`, which builds model history only from the exact contract selected at the prediction cutoff. However, repository search shows no production caller of that function. `src/commodity/v2_kronos.py#build_pit_context` still accepts the concatenated selected-contract path and therefore permits multiple contract IDs and discontinuous raw price levels in one Kronos context.

The synthetic audit case is deliberately extreme to make the mechanism obvious:

- mixed selected path close levels: `[3.0, 3.1, 10.2]`;
- correct same-contract history: `[10.0, 10.1, 10.2]`;
- mixed close standard deviation: `3.3707895547`;
- same-contract close standard deviation: `0.0816496581`;
- scale ratio: about `41.28x`.

Because upstream Kronos normalizes by the context standard deviation and then de-normalizes generated values by the same standard deviation, a delivery-month level jump can materially change the dollar scale of decoded variation and present a false shock to the tokenizer. This is the exact class of defect #133 was intended to remove.

The target-side cross-contract check does **not** solve this input problem: it prevents a cross-contract target return, but mixed-contract history can still reach the model before that check.

Required action: #178 is the separate governed defect to wire the #133 same-contract context into every executable Kronos path and add a fail-closed invariant that no adapter context contains more than one `contract_id`. This #154 audit does not make that runtime change.

## Finding F154-02 — internal preprocessing is richer than the five-column adapter contract suggests

**Severity: documentation/semantic clarity.**

Commodity passes only OHLCV across its adapter boundary, as frozen. The pinned upstream predictor then synthesizes `amount`, standardizes all six fields independently, clips normalized values, and inverse-normalizes forecasts. The existing #82 wording that prohibits scaling should therefore be read as prohibiting **repository-side/custom pre-adapter scaling**, not as a claim that Kronos performs no internal normalization.

This transformation is pinned by source revision and is not an uncontrolled fallback, but future model-interface documentation should state it explicitly.

## Finding F154-03 — one-session enforcement is not local to the generic adapter

**Severity: low while the #82 caller obeys the frozen contract; medium for reusable future execution code.**

The frozen contract requires one trading session, but `KronosMiniAdapter.forecast` derives `pred_len` from the supplied `future_index` and accepts more than one timestamp. A future governed executor should validate the exact target timestamp and `len(future_index) == 1` before invoking the generic adapter.

## Normalization conclusion

The inverse-normalization formula itself is dimensionally correct and does not create a unit mismatch. The important risk is **context composition**: an invalid cross-contract level jump changes the normalization scale before generation and therefore changes the scale used to decode forecasts. With same-contract context construction, the normalization/de-normalization round trip is semantically coherent.

## Acceptance-criteria disposition

- Synthetic adapter-to-evaluator round trip: covered by `tests/test_kronos_semantics.py`.
- Price-level versus return-space conversion: explicit and tested.
- Exact one-session semantics: confirmed in #81; tested for governed usage; generic-adapter enforcement gap documented.
- Normalization/de-normalization: traced to pinned upstream source; dimensional round trip is correct; roll-induced scale contamination identified.
- Point-estimate semantics: identified as one seeded multinomial sample path for frozen #82, not argmax.
- Frozen candidate versus upstream usage: README profile matches #82; paper/fine-tune backtest profile differs (`T=0.6`, five-path average) and remains a separate future experiment.
- Contract-month contamination: residual wiring defect F154-01 confirmed; no consumed #82 evidence was rewritten.

## Scientific consequence

Do not interpret a poor consumed #82 result as clean evidence about Kronos model capacity until the programme distinguishes the already-known pre-#133 representation defect from model information content. Likewise, do not rescue #82 by rerunning it under corrected context or different sampling and calling it the same experiment. Any corrected or paper-faithful run needs its own preregistered identity and fresh pre-result authority.
