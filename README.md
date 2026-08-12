# Commodity

Natural-gas ML research repository. The authoritative mandate and hard constraints live in [`AGENTS.md`](AGENTS.md).

## Current state

- Market: CME Henry Hub natural-gas forecasting; `NG=F` is bootstrap research data only.
- Models: zero-return benchmark + ridge baseline; Kronos-mini is an available optional CPU research model, while Ridge remains the default.
- Evaluation: expanding-window, leakage-safe, out-of-sample forecast scoring; signal and execution simulation remain separate layers.
- Execution: intentionally non-operational; LIVE trading is prohibited by `config/policy.json`.

## Authoritative configuration

| Concern | Owner |
|---|---|
| Data providers | `config/data_sources.json` |
| Models/hardware | `config/models.json` |
| Experiment definition | `config/experiment.json` |
| Experiment record schema | `ml-research-core/contracts/experiment.schema.json` |
| Research maturity stages | `config/research_stages.json` |
| Signal policy | `config/signal_policy.json` |
| Simulation assumptions | `config/simulation.json` |
| Trading/execution policy | `config/policy.json` |
| External tools/LLMs | `config/tools.json` |
| Third-party source approval | `docs/THIRD_PARTY.md` |

## Bootstrap

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,market]"
.\.venv\Scripts\python.exe -m commodity.cli fetch-market --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli run-baseline
.\.venv\Scripts\python.exe -m pytest -q
```
