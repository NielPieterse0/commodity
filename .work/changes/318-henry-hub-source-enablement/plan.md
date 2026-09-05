# WORK-318 implementation plan

## Outcome

Replace the false observed-weather source-fidelity contract with an executable reconstruction contract, narrow the Bloomberg blocker to entitled extraction/key resolution, and preserve the outcome blind.

## Authority order

1. Correct Programme 002 experiment/source specifications.
2. Correct `config/data_sources.json` and define the NOAA acquisition/reconstruction recipe.
3. Reconcile implementation-readiness, implementation-contract, feasibility, and revisit-trigger evidence.
4. Enforce the corrected contract with deterministic tests.
5. Regenerate owned generated documentation only if verification requires it.

## Scientific constraints

- Original Richman-Lamb artifacts remain Tier A evidence, not a prerequisite to Tier C reconstruction.
- Tier C uses NOAA observations and metadata with a predeclared Richman-Lamb-style station-selection/substitution algorithm and rolling prior-30-year climatology.
- Fixed NOAA 1991-2020 normals are Tier D modern robustness only.
- Ergen/Rizvanoghlu uses the Rice dissertation as an executable precursor specification; continuity into the final 2016 paper is not assumed.
- Bloomberg public source discovery is complete; the remaining gate is entitled event-key/extract verification.
- No Henry Hub literature outcomes, protected evidence, outcome-conditioned choices, preregistration freeze, or empirical execution.

## Verification

- Regression test must fail on the old fixed-normal/source-faithful contract, then pass on the corrected contract.
- Run focused research tests, acquisition-recipe tests, affected KIS verification, whole-change review, and canonical repository verification before delivery.
