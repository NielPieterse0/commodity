# Change Specification: Power Publication Time PIT Admission

- **Change ID**: `452-pjm-publication-time-pit-admission`
- **Status**: Implementation complete; verification/review pending
- **Complexity**: `large` per `scope.json`

## Outcome

Resolve the V2.29 power-family source HOLD through the preregistered U.S.-ISO source ladder without weakening point-in-time controls. Preserve PJM and NYISO evidence, admit MISO only through its implemented archive/publication/lineage/leakage gate, and return the resulting development-only power evidence to Programme #393.

## Scientific authority

- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-power-source-ladder-v2.json`
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-miso-historical-audit-v1.json`
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-search-plan-v1.json`
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v3.json`
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-weather-feature-contract-v1.json`
- Owned/shared/excluded paths and integration boundary: `scope.json`

## Repository mapping

- MISO source acquisition/normalization/audit: `src/commodity/miso.py`, `data/acquisition-recipes/commodity-miso-rf-al-v1.json`.
- Source status and PIT policy: `config/data_sources.json`.
- #426-compatible power scoring and power×weather orchestration: `src/commodity/v2_optimization.py`.
- Durable source/scoring/reproduction evidence: Programme #393 `issue452-*.json` / `issue452-power-trials-v1.jsonl` artifacts.
- Boundary/regression evidence: `tests/providers/test_miso.py`, `tests/providers/test_nyiso.py`, `tests/test_v2_optimization.py`.

## Acceptance

1. MISO capture reproduces 144 monthly archives, 4,383 daily members, 4,374 usable PIT days, and exactly 9 declared publication-date exclusions with hash-valid lineage.
2. Current-day actual load is excluded; availability uses the conservative preregistered publication-day rule.
3. Only source-identifiable power representations consume search budget; same-target revision remains held.
4. Supported outer power periods are scored against matched market controls inside the frozen development cutoff.
5. Power×weather cannot execute unless the reconstructed weather input reproduces frozen #426 evidence.
6. Protected confirmation, forward, paper, SIM, and LIVE evidence remain unopened.
7. Fresh focused and canonical verification plus exact-worktree KIS implementation review pass before PR preparation.

## Risks and recovery

- Primary risk: timing or source reconstruction drift creates false PIT evidence. Recovery is fail-closed source/interaction HOLD with preserved audit evidence.
- Provenance risk: long-running search code hash predates later orchestration-only edits. The result preserves the ledger execution hash and a tracked exact replay of both selected outer scores under the final implementation.
- Raw source data remain local acquisition evidence; tracked manifests/hashes provide durable source identity without committing provider archives.

## Out of scope

- Protected confirmation, prospective paper, SIM, LIVE, or post-2022 development evidence.
- Reclassifying Norway/Europe as the U.S.-ISO power hypothesis.
- Relaxing PJM/NYISO source-level HOLDs to manufacture a scorable source.
