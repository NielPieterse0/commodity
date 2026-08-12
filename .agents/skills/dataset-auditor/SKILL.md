---
name: dataset-auditor
description: Use when deciding whether a dataset is trustworthy enough for modeling, experimentation, statistical inference, evaluation, or downstream research decisions.
---
# Dataset Auditor

## Purpose
Determine whether a dataset is fit for its stated research use. Prioritize defects that can change conclusions rather than producing an exhaustive profiling dump.

## Audit Sequence
1. Confirm grain, keys, target, time semantics, population, and intended split strategy.
2. Check completeness, uniqueness, validity, consistency, integrity, freshness, volume, and schema drift.
3. Test join coverage and row multiplication; compare counts and key cardinalities before and after important joins.
4. Inspect missingness, class balance, labels, duplicates, impossible values, outliers, and distribution shifts by time and key segments.
5. Audit leakage: post-outcome fields, future timestamps, target proxies, duplicate entities across splits, full-data preprocessing, and unavailable backfilled information.
6. Distinguish data defects from legitimate regime, instrumentation, or population changes.
7. Assign severity and confidence to each material issue and state its downstream analytical risk.

## Output Contract
For each finding record check, evidence, affected scope, severity, confidence, likely cause, impact, and remediation. End with `fit`, `fit-with-caveats`, or `not-fit` for the stated use.

## Defaults
- Compare rates and distributions, not only counts.
- Segment temporal checks when history exists.
- Escalate leakage, broken grain, invalid labels, and split contamination because they can invalidate model results.
