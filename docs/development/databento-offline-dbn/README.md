# Databento offline DBN decoding

Issue #50 adds a local-only decode/canonicalization path for the preserved Databento `GLBX.MDP3` archive.

## Boundary

- Runtime decoder: `databento==0.83.0`, backed by `databento-dbn==0.65.0` and `zstandard==0.25.0`; deterministic Parquet writing is pinned to `pyarrow==25.0.1` by the repository lock.
- No Historical/API client is constructed by the offline path and no API key is required.
- `definition` records provide point-in-time contract identity and expiry metadata.
- `statistics` records provide final settlement and cleared-volume observations.
- `ohlcv-1d` is decode-supported for inspection/coverage only; daily close is not substituted for official settlement.
- Statistics are streamed in bounded chunks and filtered before canonicalization.
- Reused `instrument_id` values are mapped to raw symbols by an as-of join against definition receive timestamps.
- Raw artifact SHA-256 values and adjacent Databento batch job IDs are retained in canonical metadata provenance; mismatched job metadata fails closed.

## Deterministic conversion

Run `scripts/dbn_to_parquet.py` with explicit definition/statistics DBN paths, product code, retrieval timestamp, Parquet output, and metadata output. The script performs no network calls and records both a canonical-row SHA-256 and the exact Parquet SHA-256.

The committed synthetic regression fixture lives under `tests/fixtures/mdp3-golden/`. Its `sample.parquet` and `expected.json` are regenerated only through the same converter and are byte-for-byte checked by the focused test suite.

## Promotion boundary

Successful decoding does not make the quarantined archive canonical evidence. `config/data_sources.json` remains fail-closed for `canonical_market_source`, `backtest_evidence_allowed`, and `licensing_rights_verified` until the independent rights gate is resolved.

Real preserved-artifact validation is recorded in `evidence.json`.
