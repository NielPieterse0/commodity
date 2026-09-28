# Power Publication Time PIT Admission Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Resolve the V2.29 power-family HOLD without weakening point-in-time controls. Preserve the PJM publication proof, retain NYISO as a source-level HOLD after its overwrite audit, exhaust equivalent U.S.-ISO sources before a family-level HOLD, and re-enter power into development-only matched-control scoring only after one source passes a preregistered PIT gate. Protected confirmation, forward, paper, SIM, and LIVE evidence remain closed.

**Architecture:** Keep provider-specific acquisition and normalization in bounded adapters. Keep source selection/timing authority in programme research records and `config/data_sources.json`. Reuse the existing #426 search representations, roles, matched control, chronological blocks, search budget, and 2022-12-31 cutoff rather than redefining the experiment.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific authority; source rescue cannot weaken timing or revision controls.
- Fail closed when publication timing, source identity, lineage, or leakage cannot be defended.
- Do not consume power-family search budget while a candidate source is held.
- Use focused tests during development and the live KIS lifecycle for final verification/review.

### Task 1: Preserve completed PJM and NYISO evidence

- Keep the preregistered PJM publication-time reconstruction, archive hash/vintage audit, and fail-closed source gate.
- Leave PJM unscored unless its authorized historical archive is reacquired and passes revision preservation.
- Preserve the NYISO P-7 2015-04-24 overwrite finding as a source-level HOLD; do not relax its immutability gate.

### Task 2: Bind the next equivalent U.S.-ISO source before scoring

- Supersede the source ladder before any power rescoring to record MISO as the next continuous U.S.-ISO candidate, with ISO-NE retained behind it and PJM retained as replication.
- Bind the MISO Daily Regional Forecast and Actual Load product, archive identity, publication-day semantics, conservative availability rule, lineage requirements, and explicit treatment of malformed publication-date metadata.
- Keep Norway/Europe segregated as a separately named global-gas/cross-market family.

### Task 3: Acquire and validate MISO 2011-2022

- Acquire all 144 monthly MISO archived ZIPs for 2011-01 through 2022-12 with archive and member SHA-256 lineage.
- Validate one daily report for every calendar day, reporting-period identity, MISO-wide current-day MTLF, and absence of current-day actual-load leakage.
- Admit only daily members whose internal Published Date equals the report day. Exclude malformed/late publication-date members rather than repairing them.
- Reconstruct availability conservatively after the declared publication day has fully ended; do not optimize timing from performance.

### Task 4: Re-enter only identifiable power representations

- Build the #426-compatible power family frame from admissible MISO daily issued forecasts.
- Keep `issued_load_level` and prior-only `issued_load_anomaly` when supported by source semantics.
- Hold `issued_revision` with zero search budget if the one-issue-per-day MISO product cannot identify a same-target revision without semantic substitution.
- Reuse #426 roles, 25-hour max staleness, matched market-only controls, chronological blocks, and development cutoff unchanged.

### Task 5: Verify and land through KIS

- Run affected tests and repository change checks.
- Close KIS review findings against the exact governed worktree.
- Prepare the reviewable PR, require exact-head CI, merge, refresh local main, and record closeout evidence.
