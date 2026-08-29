# Repository Documentation

Maintained documentation is intentionally small. It explains the durable system and points to machine-owned authority instead of copying mutable values.

## Maintained docs

| Document | Purpose |
| --- | --- |
| `README.md` | Short repository entry point |
| `AGENTS.md` | Mandate, authority map, development governance |
| `CONTRIBUTING.md` | Contribution and pull-request hygiene |
| `SECURITY.md` | Security, secrets, and local-state boundary |
| `docs/roadmap.md` | Stable research progression |
| `docs/data-manifest.md` | Desired data families and acquisition architecture |
| `docs/THIRD_PARTY.md` | Approval, licensing, and third-party trust boundaries |
| `docs/architecture/` | Durable explanatory architecture |

## Where information belongs

```text
.work/changes/    temporary change reasoning; ignored and disposable
research/         governed scientific preregistration/results/interpretation
artifacts/        durable machine-produced evidence
config/           mutable machine authority and policy
contracts/        machine-checkable schemas and contracts
src/              implementation
docs/             durable human explanation
docs/development/ legacy historical change evidence only
```

A scientific experiment and a software change may be related, but they are different records. New confirmatory and exploratory research follows the #249 lifecycle under `research/`; implementation notes do not substitute for scientific records.
## Drift rule

A maintained document should not copy a value that can change independently. Provider status, model pins, exact metrics, experiment state, issue state, dataset identities, runtime versions, and execution permissions belong to their assigned owners. Maintained docs state the durable rule or consequence and link to the owner.

When a change creates a permanent architectural decision, update the relevant maintained document or machine authority. The temporary `.work/changes/<issue>-<slug>/` material can then be deleted.