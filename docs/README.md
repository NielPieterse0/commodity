# Repository Documentation

Maintained documentation is intentionally small. It explains the durable system and points to machine-owned authority instead of copying mutable values.

## Start with the whole, then zoom in

| Document | Purpose |
| --- | --- |
| `docs/big-picture.md` | Why Commodity exists, what the programme has learned, where it is going, and how experiments connect back to the whole |
| `docs/research-methodology.md` | Plain-English research method and confirmatory lifecycle |
| `docs/roadmap.md` | Stable research progression from data truth to controlled execution |
| `docs/data-manifest.md` | Desired data families and acquisition architecture |
| `docs/THIRD_PARTY.md` | Approval, licensing, and third-party trust boundaries |
| `docs/architecture/` | Durable explanatory architecture |

Repository-level authority remains in `AGENTS.md`; contribution and security rules remain in `CONTRIBUTING.md` and `SECURITY.md`.

## Where information belongs

```text
.work/changes/             temporary change reasoning; ignored and disposable
.work/reference-archive/   local historical/reference material when useful; ignored
research/                  governed scientific preregistration/results/interpretation
artifacts/                 durable machine-produced evidence
docs/development/           frozen legacy evidence; compatibility exception only
config/                    mutable machine authority and policy
contracts/                 machine-checkable schemas and contracts
src/                       implementation
docs/                      small set of durable human explanations
```

`docs/` is not an archive. `docs/development/` is the one frozen legacy exception because completed historical experiments bind exact paths and bytes there; moving it now would rewrite their evidence identity. Nothing new may be added there. External research packages and new development notes belong under ignored `.work/`; governed scientific records belong under `research/`.
## Research records are not change notes

A scientific experiment and a software change may be related, but they are different records. New confirmatory research follows the immutable preregistration/results lifecycle under `research/experiments/`. Exploratory and diagnostic runs use `contracts/exploratory_run.schema.json` with records under `research/exploratory/`. `.work/` notes never substitute for either kind of scientific record.

## Drift rule

A maintained document should not copy a value that can change independently. Provider status, model pins, exact metrics, experiment state, issue state, dataset identities, runtime versions, and execution permissions belong to their assigned owners. Maintained docs state the durable rule or consequence and point to the owner.

When a change creates a permanent architectural or methodological explanation, update the relevant maintained document or machine authority. Temporary `.work/changes/<issue>-<slug>/` material can then be deleted.
