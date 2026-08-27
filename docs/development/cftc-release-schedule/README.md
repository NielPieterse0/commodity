# CFTC release-schedule coverage

Issue #213 makes CFTC research availability fail closed outside the source-backed report-date window owned by `config/data_sources.json` under `sources.cftc_cot.availability_policy`.

The resolver must not extrapolate publication timing beyond that configured window. Special publication dates and the verified 2026 scheduled release dates remain authoritative inside the supported window.

## Extending the window

Before extending `supported_report_date_start` or `supported_report_date_end`:

1. add source-backed CFTC publication/release-schedule evidence to the existing availability policy owner;
2. preserve any special announcement or shutdown dates explicitly;
3. add regression coverage for the new boundary and representative scheduled dates;
4. rerun the CFTC/PIT verification suite before using the extended period in research.

## Historical-result impact

The completed V1 research window is inside the configured supported report-date range. This change therefore closes a future leakage hazard and does not, by itself, require a V1 rerun or rewrite of historical results.
