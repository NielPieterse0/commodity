# Commodity

Commodity is an experimental trading-research platform for finding, testing, and eventually combining evidence into realistic trading decisions. Natural gas and CME Henry Hub are the first complete reference implementation; reusable platform components are intended to support later instruments without hard-coding Henry Hub into the core.

This repository is research software, not trading advice. Live trading is disabled by policy; binding execution authority is owned only by `config/trading-policy.json`. License: no project-wide open-source license has been granted yet; public visibility does not grant reuse, modification, or redistribution rights. Third-party rights are machine-owned by `config/third_party.json` and projected for humans in generated `docs/THIRD_PARTY.md`.

## Start here

- [`AGENTS.md`](AGENTS.md) — repository mandate, authority map, and development rules.
- [`docs/README.md`](docs/README.md) — documentation map and boundaries.
- [`docs/big-picture.md`](docs/big-picture.md) — why the project exists, what we have learned, and how experiments connect to the whole.
- [`docs/research-methodology.md`](docs/research-methodology.md) — plain-English research method and experiment lifecycle.
- [`docs/roadmap.md`](docs/roadmap.md) — long-term research progression.
- [`docs/data-manifest.md`](docs/data-manifest.md) — desired data architecture.
- [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md) — third-party approval and licensing boundaries.

## Repository shape

`config/` and `contracts/` hold current machine authority and reusable contracts. `src/` implements the system. `research/` holds durable governed scientific knowledge. `artifacts/` holds durable machine evidence intentionally reused across changes. `docs/` is a deterministic Markdown projection generated from machine-readable artifacts by `scripts/docs/generate_docs.py`. Governed change records remain in ignored `.work/changes/` for their full lifecycle; retained implementation worktrees belong under `.work/worktrees/`.

Retired pre-governance, non-governed, and non-authoritative material lives under ignored `.work/historical/`; governed change records do not move there merely because they close. Live code and generated documentation must not depend on historical paths. External reference working material and change-local notes belong under `.work/`, not generated `docs/`.

## Development

Create an isolated governed change through the live KIS workflow described in `AGENTS.md`. Commodity virtual environments must use a Python runtime whose base installation is under `C:\Projects`; the repository helper rejects user-profile Python rather than silently falling back to it. Select the machine's canonical Projects-local interpreter explicitly:

```powershell
$env:COMMODITY_PYTHON = '<canonical C:\Projects-local python.exe>'
.\scripts\environment\create_venv.ps1 -InstallLockedDependencies
.\scripts\verify.ps1
```

`COMMODITY_PYTHON` is machine-local state and is intentionally not pinned to a KIS installation path in repository authority.

See `CONTRIBUTING.md` for contribution and pull-request rules, and `SECURITY.md` for secrets and local-state boundaries.
