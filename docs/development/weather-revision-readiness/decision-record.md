# Weather forecast revision readiness — issue #114

**Decision date:** 2026-08-20

## Decision

Preregister a NOAA GFS-first post-V2 weather-revision challenger, but do not activate or execute it yet.

The June 2026 Zhu, Hsu & Park working paper directly studies weather forecast revisions in natural-gas price discovery and reports significant revision effects plus warm/cold asymmetry. Because it is a working paper rather than peer-reviewed evidence, it raises the hypothesis evidence grade but does not establish settled proof.

Chen, Hartley & Lan (2023, *Journal of Futures Markets*, DOI `10.1002/fut.22402`) provides peer-reviewed adjacent support for economically weighted temperature measures and natural-gas futures effects. It is not direct forecast-revision evidence.

## Data-source disposition

NOAA GFS 0.5-degree issued forecasts are the preferred baseline. NCEI documents four daily cycles (00/06/12/18 UTC), three-hourly forecast output to +192h, and a record from 2006 onward, with older material available through archive ordering.

NOAA GEFS is a useful ensemble sensitivity candidate, but NCEI explicitly documents an official archive discontinuity around 23 September 2020 and says newer NODD data are not officially archived. That continuity question must be resolved before canonical use.
ECMWF remains deferred for the primary historical study. Its free Open Data service retains only the most recent 12 forecast runs (about 2–3 days), while historical MARS archive access carries a service charge for commercial users and only a discretionary research waiver.

## Future preregistration requirements

The future contract must freeze the exact NOAA product/grid, eligible cycles, forecast horizons, market-information cutoff, missing-cycle rule, model-version treatment, and gas-demand weighting before outcomes are inspected.

For each valid date and demand region, HDD/CDD must be calculated from actually issued forecasts. Revision features must compare an eligible forecast cycle only with the immediately preceding eligible issued cycle for the same valid horizon. Reanalysis or realized weather must never be substituted for a missing forecast vintage.

Demand weights should be fixed from lagged natural-gas demand information. Population weighting may be retained as a predeclared control. Warm and cold revision terms should be separated ex ante because the direct working paper reports asymmetric response.

## Boundary

This decision does not alter the frozen V2 contract, authorize a model run, acquire paid data, generate a feature, or inspect any new empirical outcome. Activation requires a separate preregistration and evidence gate.

Machine-readable evidence and source links are in `evidence.json`. Operational source status is owned by `config/data_sources.json`; revisable assumptions are owned by `config/assumptions.json`.
