---
name: data-engineer
description: Use when building, repairing, or reviewing repeatable dataset ingestion, transformation, joining, partitioning, lineage, or versioning workflows for ML and statistical research.
---
# Data Engineer

## Purpose
Build research datasets whose origin, grain, transformations, and versions can be traced and reproduced. Treat dataset construction as part of the experiment, not invisible preprocessing.

## Workflow
1. Define observation grain, target population, time semantics, keys, and downstream use.
2. Inventory source datasets with provenance, snapshot/version, schema, freshness, and access constraints.
3. Specify transformations as an ordered deterministic pipeline; separate raw, cleaned, feature-ready, and evaluation-ready layers.
4. Validate joins with key uniqueness, row counts, unmatched keys, many-to-many expansion, temporal alignment, and unit/type consistency.
5. Produce immutable dataset IDs or hashes for every experiment input; never silently overwrite a used dataset.
6. Record non-trivial lineage from output columns to source columns and transformations.
7. Hand the dataset to `dataset-auditor` before training when data quality or leakage can affect conclusions.

## Required Output
Dataset ID/version/hash; grain and keys; source snapshots; transformations; material exclusions; row/column counts; lineage; unresolved risks.

## Guardrails
- Preserve point-in-time correctness whenever time is meaningful.
- Fit learned preprocessing only on the permitted training partition.
- Keep secrets, credentials, restricted personal data, and sensitive values out of logs and artifacts.
- Do not install packages or execute untrusted repository code as part of dataset intake.
