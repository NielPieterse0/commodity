# Commodity

Commodity is an experimental trading-research platform for finding, testing, and eventually combining evidence into realistic trading decisions. Natural gas and CME Henry Hub are the first complete reference implementation; reusable platform components are intended to support later instruments without hard-coding Henry Hub into the core.

This repository is research software, not trading advice. Live trading is disabled by policy; binding execution authority is owned only by `config/policy.json`. License: no project-wide open-source license has been granted yet; public visibility does not grant reuse, modification, or redistribution rights. Third-party rights remain governed by `docs/THIRD_PARTY.md`.

## Start here

- [`AGENTS.md`](AGENTS.md) — repository mandate, authority map, and development rules.
- [`docs/README.md`](docs/README.md) — documentation map and boundaries.
- [`docs/architecture/trading-system.md`](docs/architecture/trading-system.md) — durable system architecture.
- [`docs/roadmap.md`](docs/roadmap.md) — long-term research progression.
- [`docs/data-manifest.md`](docs/data-manifest.md) — desired data architecture.
- [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md) — third-party approval and licensing boundaries.

## Repository shape

`config/` and `contracts/` hold machine authority and contracts. `src/` implements the system. `research/` holds governed scientific records under the #249 methodology. `artifacts/` holds durable machine evidence. `docs/` explains the durable system. Temporary change reasoning belongs in ignored `.work/changes/`.

Completed historical change records under `docs/development/` are legacy evidence. They remain available for traceability but are not current authority and are not the destination for new change documentation.

## Development

Create an isolated governed change through the live KIS workflow described in `AGENTS.md`. A normal local verification run is:

```powershell
python -m pytest -q
```

See `CONTRIBUTING.md` for contribution and pull-request rules, and `SECURITY.md` for secrets and local-state boundaries.