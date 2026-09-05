# Change Specification: Henry Hub Source Enablement

- **Change ID**: `318-henry-hub-source-enablement`
- **Status**: Active
- **Complexity**: Large
- **Risk triggers**: `public_contract`

## Outcome

Implement and close WORK-318 by replacing the false observed-weather source-fidelity assumption with a governed NOAA/Richman-Lamb reconstruction route, recording the executable Ergen precursor construction and Bloomberg PiT entitlement boundary, and updating Programme 002 source-readiness evidence without opening empirical outcomes.

## Authority and scope

- Source work: GitHub issue `#318` / Work Management `WORK-318` and its bounded research closeout.
- Scientific authority: `research/programmes/002-henry-hub-fresh/**`.
- Operational source authority: `config/data_sources.json` plus the governed NOAA acquisition recipe.
- Owned/shared/excluded paths and base evidence: `scope.json`.
- No empirical execution, preregistration freeze, protected-evidence opening, or outcome-conditioned station/model choice is authorized.

## Acceptance

1. Fixed NOAA 1991-2020 normals are not represented as source-faithful Mu/Ergen reproduction; they are Tier D robustness only.
2. rep-007 has a deterministic Tier C NOAA reconstruction contract with rolling prior-30-year climatology and frozen station/substitution lineage.
3. rep-008 records the Rice dissertation precursor locations, weights, seven-day shock horizon, 30-year normal, and ARIMA(1,2,1)/500-day/SIC construction while explicitly not assuming final-2016 continuity.
4. Bloomberg public product ambiguity is closed; rep-003/018/019 remain fail-closed on entitled PiT/ECOS legacy-key and last-pre-release-state extraction.
5. Configuration/readiness/feasibility records agree and preserve `empirical_execution_authority=false`.
6. Deterministic tests reject the stale weather assumption and validate the Bloomberg entitlement boundary; generated docs are regenerated through the canonical generator.
7. Focused tests and repository verification/review provide current evidence; any environment-only limitation is explicit and exact-head CI owns the full-suite gate.

## Recovery

Revert this bounded change to the verified base SHA in `scope.json`; no data acquisition or empirical outcome artifact is created by this change.
