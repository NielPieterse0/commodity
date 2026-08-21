# #178 — Kronos same-contract execution correction

## Scope

This change closes the residual #133/#154 integration gap without running Kronos or changing any checkpoint, sampling setting, target, horizon, or historical result.

The old #82 Mini result remains historical evidence under its original frozen implementation identity. This correction does not rewrite or rescue #82.

## Corrected execution boundary

Future Kronos execution must enter through `build_execution_pit_context` with both canonical per-contract rows and the selected contract path.

That function:

- preserves explicit timezone requirements before any roll-safe transformation;
- calls `build_same_contract_model_context` from #133;
- derives history only for the contract selected at the prediction cutoff;
- reuses the historical #82 PIT/OHLCV validation without changing its semantics;
- preserves `selection_trade_date`, `selection_roll_reason`, `source_row_sha256`, and transformation lineage;
- keeps `max_context=512` fixed.

The successor-only `execution_adapter_frame` requires exactly one `contract_id` immediately before identity columns are stripped. `governed_kronos_forecast` is the governed future execution entry point: it always builds the same-contract context first, passes only the checked adapter frame to the generic adapter, and constructs exactly one future target timestamp after the prediction cutoff.

Historical #82 `build_pit_context` and `adapter_frame` behavior remains unchanged so consumed #82 evidence stays reproducible under its original identity.

## Successor freeze requirement

The historical `IMPLEMENTATION_SOURCE_PATHS` constant remains unchanged because it is part of #82's frozen provenance contract.

Any successor Kronos experiment must instead bind `CORRECTED_IMPLEMENTATION_SOURCE_PATHS`, which adds `src/commodity/roll_safe_market.py` as a result-affecting transitive dependency. A successor freeze must therefore create a new implementation/source-manifest identity before empirical execution.

This is especially required before #180 compares Mini, Small, and Base. #180 must not reuse #82's source manifest or overwrite its artifacts.

## Verification contract

Regression tests prove that:

- historical #82 context behavior remains reproducible under the original frozen path;
- the successor execution builder produces only the selected contract's own history across a roll and retains lineage evidence;
- the successor adapter boundary refuses mixed-contract identity before stripping `contract_id`;
- the governed executor reaches the adapter only with same-contract OHLCV and exactly one future target timestamp;
- naive market identity timestamps remain prohibited;
- the corrected successor source-path set includes the roll-safe implementation.

No model inference is part of #178.
