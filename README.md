# Commodity

Natural-gas ML research repository. Repository authority is assigned in [`AGENTS.md`](AGENTS.md#repository-authority); this README is a non-authoritative onboarding and current-state projection.

## Current state

- **Research target:** U.S. / CME Henry Hub remains the first serious forecasting target. Geographic expansion and desired source families are owned by [`docs/data-manifest.md`](docs/data-manifest.md).
- **Market evidence:** ingestion is provider-adapted; current source selection, readiness, and evidence gates are owned by `config/data_sources.json`.
- **Databento preservation:** acquisition has progressed beyond the earlier probe stage; the current local integrity state is recorded in [`docs/development/databento-full-history-acquisition/evidence.json`](docs/development/databento-full-history-acquisition/evidence.json).
- **Point-in-time research:** U.S. fundamentals/weather preservation and evidence-tier handling are operational, with revision-risk restrictions explicit. Rules are owned by `config/data_sources.json`; `src/commodity/availability.py` implements the joins.
- **Models and evaluation:** model settings live in `config/models.json`; the active experiment now freezes a leakage-safe PIT core and compares configured baselines under one walk-forward protocol. The research sequence is owned by [`docs/roadmap.md`](docs/roadmap.md).
- **Execution:** permission is owned only by `config/policy.json`.

## Research direction

- [Kronos + indicator fusion architecture](docs/architecture/kronos-indicator-fusion.md)
- [Natural-gas data manifest](docs/data-manifest.md)
- [Compact research roadmap](docs/roadmap.md)

## Point-in-time evidence

Evidence-strength semantics and source-specific availability/revision rules are owned by `config/data_sources.json`; `src/commodity/availability.py` implements the join behavior. Keep exploratory screening, research point-in-time evidence, and canonical evidence distinct without duplicating source-specific rules here.

For the complete repository authority assignment, see [`AGENTS.md`](AGENTS.md#repository-authority).

## Data preservation

Raw snapshots live under ignored `data/raw/snapshots/`. Manifests contain source/query metadata, artifact hashes and byte counts; credentials and licensed market values are not committed.

Preserved Databento `definition`, `statistics`, and `ohlcv-1d` DBN/Zstd files can be decoded locally through the pinned `databento` dependency. Offline canonicalization uses `definition` + final settlement/cleared-volume `statistics`; `ohlcv-1d` is inspection/coverage evidence only and is never substituted for official settlement. This path makes no API call and does not promote quarantined data or satisfy licensing gates.

```powershell
.\.venv\Scripts\python.exe -m commodity.cli capture-canonical-market-v1 --end <YYYY-MM-DD> --snapshot-id <id> --curve-contracts 12
.\.venv\Scripts\python.exe -m commodity.cli capture-eia-v1 --end <YYYY-MM-DD> --snapshot-id <id>
.\.venv\Scripts\python.exe -m commodity.cli capture-weather-run --run <YYYY-MM-DDTHH:MM> --latitude <lat> --longitude <lon> --snapshot-id <id>
.\.venv\Scripts\python.exe -m commodity.cli capture-weather-v1-window --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli capture-cftc-v1-window --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli capture-wngsr-v1-window --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli capture-nyiso-v1-window --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli audit-v1-exogenous --end <YYYY-MM-DD>
```

Verified 2026-08-13 capture metadata is recorded in `docs/development/us-v1-data-foundation/evidence.json`. That file intentionally records hashes/coverage only.

## Bootstrap

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m commodity.cli fetch-market --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli fetch-canonical-market --start <YYYY-MM-DD> --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli freeze-v1-dataset
.\.venv\Scripts\python.exe -m commodity.cli run-tournament
.\.venv\Scripts\python.exe -m commodity.cli run-baseline
.\.venv\Scripts\python.exe -m commodity.cli backtest --predictions artifacts/runs/baseline/predictions.csv --output artifacts/runs/baseline-backtest
.\.venv\Scripts\python.exe -m pytest -q
```
