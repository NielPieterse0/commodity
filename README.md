# Commodity

Natural-gas ML research repository. The mandate lives in [`AGENTS.md`](AGENTS.md); revisable assumptions live in `config/assumptions.json`, while binding execution policy lives in `config/policy.json`.

## Current state

- Market: CME Henry Hub natural-gas forecasting; `NG=F` is bootstrap research data only. Massive Futures is selected for expiry-aware per-contract settlement/OHLCV ingestion. The configured account history and deterministic `volume_crossover_dte_v1` roll methodology are validated; canonical backtest evidence remains blocked because Massive non-display/backtesting rights are not verified for the current individual account. Raw Massive preservation is resumable, paced and M1-M12 bounded; licensed market values remain local/ignored.
- U.S. V1 data: immutable snapshot acquisition is implemented for EIA Natural Gas bulk history, targeted Lower-48 EIA-930 demand/forecast and gas generation, and archived Open-Meteo Single Runs weather. These are preservation/current-state snapshots, not automatically point-in-time backtest-ready datasets; historical release/revision `available_at` reconstruction remains explicit work.
- Models: zero-return benchmark + ridge baseline; Kronos-mini is an available optional CPU research model, while Ridge remains the default.
- Evaluation: expanding-window, leakage-safe, out-of-sample forecast scoring and explicit signal/execution simulation are operational; canonical-evidence promotion remains a separate data-quality gate.
- Execution: intentionally non-operational; LIVE trading is prohibited by `config/policy.json`.

## Research direction

- [Kronos + indicator fusion architecture](docs/architecture/kronos-indicator-fusion.md)
- [Natural-gas data manifest](docs/data-manifest.md)
- [Compact research roadmap](docs/roadmap.md)

## Authoritative configuration

| Concern | Owner |
|---|---|
| Data providers | `config/data_sources.json` |
| Revisable research assumptions | `config/assumptions.json` |
| Models/hardware | `config/models.json` |
| Experiment definition | `config/experiment.json` |
| Experiment record schema | `contracts/experiment.schema.json` |
| Research maturity stages | `config/research_stages.json` |
| Signal policy | `config/signal_policy.json` |
| Simulation assumptions | `config/simulation.json` |
| Trading/execution policy | `config/policy.json` |
| External tools/LLMs | `config/tools.json` |
| Third-party source approval | `docs/THIRD_PARTY.md` |

Authoritative ownership does not imply application-runtime consumption. `config/research_stages.json` and `config/tools.json` are governance/agent inputs rather than forecast-runtime dependencies; runtime code is not required to load them. In `config/experiment.json`, `research_period.end = "2100-01-01"` is an intentional far-future sentinel for an effectively open-ended historical upper bound, not a forecast horizon.

## Data preservation

Raw snapshots live under ignored `data/raw/snapshots/`. Manifests contain source/query metadata, artifact hashes and byte counts; credentials and Massive market values are not committed.

```powershell
.\.venv\Scripts\python.exe -m commodity.cli capture-massive-v1 --end <YYYY-MM-DD> --snapshot-id <id>
.\.venv\Scripts\python.exe -m commodity.cli capture-eia-v1 --end <YYYY-MM-DD> --snapshot-id <id>
.\.venv\Scripts\python.exe -m commodity.cli capture-weather-run --run <YYYY-MM-DDTHH:MM> --latitude <lat> --longitude <lon> --snapshot-id <id>
```

Verified 2026-08-13 capture metadata is recorded in `docs/development/us-v1-data-foundation/evidence.json`. That file intentionally records hashes/coverage only.

## Bootstrap

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,market]"
.\.venv\Scripts\python.exe -m commodity.cli fetch-market --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli fetch-canonical-market --start <YYYY-MM-DD> --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli run-baseline
.\.venv\Scripts\python.exe -m commodity.cli backtest --predictions artifacts/runs/baseline/predictions.csv --output artifacts/runs/baseline-backtest
.\.venv\Scripts\python.exe -m pytest -q
```
