# #83 Agent 5 Documentation Plan

**Documentation level:** Medium

**Issue:** `#83`

**Status:** preparation only; no empirical activation

## Outcome and audience

Produce a reviewable, non-executable #83 preregistration preparation package for Agent 2 (`#81`) and Agent 3 (`#88`). It must define the indicator/surprise feature surface tightly enough that later activation cannot silently change information families, PIT semantics, transforms, missingness, or ablations after results exist.

## Authority and sources

- Repository ownership/governance: `AGENTS.md`.
- Source availability/revision rules: `config/data_sources.json` pinned in `spec.md` and `data-inventory.json`.
- Existing U.S. V1 data/PIT architecture: `docs/data-manifest.md`, `docs/development/us-v1-point-in-time/spec.md`, and `docs/development/v1-pit-model-tournament/spec.md`.
- Existing V2 architecture context: `docs/architecture/kronos-indicator-fusion.md`.
- Longitudinal comparison requirements: `docs/development/longitudinal-research-metrics/agent-1-spec.md` and the landed #78 authority.
- Programme/activation scope: GitHub issues `#80`, `#81`, `#83`, and `#88`.
- Existing-data evidence only: local preserved manifests and the frozen V1 dataset manifest; raw values/results are not design inputs.

## Boundaries

No feature execution, model fitting, predictions, target-conditioned analysis, new acquisition, tuning, executable V2 config mutation, or empirical result inspection. `#81` owns executable experiment/control/metric/split/seed identities; `#88` owns empirical release.

## Implementation tasks

1. Inventory existing source identities, preserved coverage metadata, PIT/revision status, and known absence constraints without acquiring or executing features.
2. Define fixed W/S/C/V/P/L information families and deterministic transforms.
3. Define fail-closed PIT, predecessor selection, full fit/scored-row coverage, and imputation rules.
4. Define `I-ALL` as the sole primary challenger and fixed `I-NO-*` attribution-only ablations.
5. Freeze exclusions and the null-result stop rule so a negative result cannot trigger rescue search.
6. Review for authority duplication, leakage, post-hoc degrees of freedom, and activation ambiguity.
7. Validate JSON, formatting/diff hygiene, and exact documentation-only change scope.

## Source-to-output traceability

- `spec.md` owns the prepared #83 candidate definition and activation handoff.
- `data-inventory.json` records existing-data presence/eligibility constraints and evidence identities only.
- `plan.md` records documentation lifecycle scope, sources, tasks, and acceptance evidence; it does not own mutable operational values.

## Acceptance evidence

- All changed files remain under `docs/development/v2-indicator-surprise-challenger/`.
- No source/config/policy/test file changes exist.
- JSON inventory parses successfully and its pinned source-policy digest matches the current preparation base.
- `git diff --check` and Ruff pass on the exact change state.
- Documentation review has no unresolved substantive activation blocker; tool-contract failures are recorded separately from substantive findings.
