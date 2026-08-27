# Commodity

Reusable commodity trading research platform, with natural gas and CME Henry Hub as the first complete reference implementation. Repository authority is assigned in [`AGENTS.md`](AGENTS.md#repository-authority); this README is a non-authoritative onboarding and current-state projection.

**Repository status:** experimental research, not trading advice or an execution system. Live trading is disabled by policy. See [`SECURITY.md`](SECURITY.md) for sensitive-reporting rules and [`CONTRIBUTING.md`](CONTRIBUTING.md) for change/PR hygiene.

**License:** no project-wide open-source license has been granted yet. Public visibility, if enabled, does not by itself grant reuse, modification, or redistribution rights. Third-party components retain their own licenses; see [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md).

## Current state

- **Reference market:** U.S. / CME Henry Hub remains the first serious end-to-end research target and proving ground. Reusable framework components are intended to support later governed replication onto other justified tradable instruments; geographic expansion and desired source families are owned by [`docs/data-manifest.md`](docs/data-manifest.md).
- **Market evidence:** ingestion is provider-adapted; current source selection, readiness, and evidence gates are owned by `config/data_sources.json`.
- **Databento preservation:** acquisition has progressed beyond the earlier probe stage; the current local integrity state is recorded in [`docs/development/databento-full-history-acquisition/evidence.json`](docs/development/databento-full-history-acquisition/evidence.json).
- **Point-in-time research:** U.S. fundamentals/weather preservation and evidence-tier handling are operational, with revision-risk restrictions explicit. Rules are owned by `config/data_sources.json`; `src/commodity/availability.py` implements the joins.
- **Models and evaluation:** V1 evaluation is complete on the frozen full-V1 PIT dataset. The 3-model × 8-ablation tournament completed 24/24 runs across 41 expanding walk-forward folds / 204 OOS rows and found `no_robust_edge`. With block size 20 this is only about 10.2 effective blocks, so uncertainty remains material. The tested histogram GB uses one explicit deterministic model seed (`random_state=0`). The current experiment decision is owned by `config/experiment.json`, with immutable empirical evidence under [`docs/development/v1-research-completion/`](docs/development/v1-research-completion/).
- **V1 disposition:** the empirical V1 result is `no_robust_edge`. Research promotion remains false and trading authority remains false. Issue #78 is closed/accepted: the governed longitudinal measurement and regression infrastructure is operational, and the historical early-smoke → Phase-D change is classified as non-comparable rather than an established software/data regression. V1 programme closure is governed through #15; V2 empirical activation is eligible only after #15 itself is terminally closed and reconciled. The final closeout packet is [`v1-programme-closeout.json`](docs/development/v1-research-completion/v1-programme-closeout.json).
- **Execution:** permission is owned only by `config/policy.json`; V1 closeout does not authorize live trading.

## Research direction

- [Integrated trading research system](docs/architecture/trading-system.md)
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

## Research-grade V1 reproduction

Use the locked environment and the governed frozen dataset. `reproduce-v1` re-verifies the freeze, re-runs the current dataset audit, executes the rigorous Phase D evaluator, and fails if the Git working tree is dirty.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m commodity.cli reproduce-v1
```

The expected V1 disposition is `no_robust_edge`; evidence remains evaluation-only, research promotion remains false, and trading authority remains false. The ignored frozen dataset must already exist at the identity pinned by `config/phase_d_evaluation.json`.

## Development/bootstrap commands

`fetch-market`, `freeze-v1-dataset`, `run-tournament`, and `run-baseline` are development or screening utilities. They are not the research-grade V1 reproduction path and cannot grant full-V1, promotion, or trading authority. In particular, `freeze-v1-dataset --require-full-v1` fails closed because CSV/yfinance input does not provide the governed canonical market + exogenous evidence stack.

```powershell
.\.venv\Scripts\python.exe -m commodity.cli fetch-market --end <YYYY-MM-DD>
.\.venv\Scripts\python.exe -m commodity.cli run-baseline
.\.venv\Scripts\python.exe -m pytest -q
```
