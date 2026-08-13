# V1 PIT Dataset + Model Tournament Review

## Disposition

Ready for PR after final commit verification. No policy or execution authority changed.

## Closed findings

1. **Experiment leakage field semantics:** the implementation initially wrote the enforcement mechanism name into the schema-v2 leakage-result field. The focused contract test failed; `controls.leakage_check` remains the allowed `incomplete` outcome while `dataset.leakage_enforcement` owns the mechanism name.
2. **Baseline runtime bound:** the first histogram-gradient-boosting configuration used 100 iterations and was too expensive under five-session retraining. It was bounded to 20 iterations without changing the common walk-forward protocol.
3. **Frozen-input provenance:** tournament execution originally accepted an arbitrary CSV. It now requires the sibling frozen-dataset manifest and verifies the CSV artifact hash before fitting any model.

## Architecture / leakage review

- Dataset construction reuses the existing point-in-time availability validator and rejects `screening` evidence.
- Full-V1 completeness fails closed; the current smoke dataset is explicitly `pit_core` and is not research-promotion eligible.
- All models use the same chronological expanding walk-forward protocol; no shuffled time-series split is exposed.
- Data construction, model factories, tournament evaluation, downstream simulation, and execution policy remain separate modules.
- `config/experiment.json` and `config/models.json` remain the authoritative owners for active experiment/model settings. Source evidence gates remain untouched in `config/data_sources.json`.
- The current smoke input is the noncanonical market bootstrap and omits market structure, positioning, power, storage, and weather. Its ranking is pipeline evidence only, not a validated forecasting edge.

## Review tooling

KIS automated code-review backends were attempted twice. Codex CLI failed with `UnicodeEncodeError`; the NVIDIA NIM backend also failed before returning findings. The failures are environmental and are recorded in `evidence.json`; deterministic inspection, focused/full tests, Ruff, diff checks, and this direct review were used instead.
