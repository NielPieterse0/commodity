# Repository Boundaries

This document describes the durable logical boundaries of Commodity. It is a target architecture, not a claim that every historical module already has perfect physical separation.

| Area | Responsibility |
| --- | --- |
| `config/` | Mutable machine authority: policy, assumptions, providers, models and research controls |
| `contracts/` | Machine-checkable record and interface contracts |
| `src/commodity/` | Product/research implementation |
| `research/experiments/` | Confirmatory preregistration, results, interpretation and executive summaries |
| `research/exploratory/` | Governed exploratory/diagnostic records |
| `artifacts/` | Durable generated evidence and longitudinal outputs |
| `docs/` | Maintained durable human explanation |
| `docs/development/` | Legacy historical change evidence only |
| `.work/changes/` | Temporary implementation plans, investigations, reviews and scratch material |

## Change versus research history

Software-change reasoning belongs in `.work/changes/<issue>-<slug>/` and is disposable after the durable consequence is recorded. Scientific evidence that must remain reproducible belongs in the #249 research lifecycle or another assigned machine authority; it must never depend on `.work/`.

## Logical system boundary

The reusable platform separates instrument discovery, data, features/context, signal producers, evaluation/calibration, decisions, risk, policy, execution and forward evaluation. Historical slice-specific modules may span these concerns while the codebase is progressively generalized. New work should move toward explicit interfaces rather than documenting transitional coupling as permanent architecture.