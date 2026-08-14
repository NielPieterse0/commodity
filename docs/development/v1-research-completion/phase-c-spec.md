# Phase C Deterministic Full-V1 Freeze and Audit Specification

## Outcome
Phase C owns the immutable freeze and independent audit boundary for the first `full_v1` research dataset. It must never manufacture readiness when Phase B evidence is incomplete.

## Requirements
- **R1 — Promotion gate:** freezing is allowed only when the upstream dataset manifest declares `completeness=full_v1`, contains every configured required family, and has no missing required family.
- **R2 — Deterministic identity:** identical dataset bytes, upstream manifest, configuration, and transformation code produce the same freeze identity and artifact hashes.
- **R3 — Immutable artifact:** a frozen dataset is written to a content-addressed directory; an existing conflicting artifact fails closed rather than being overwritten.
- **R4 — Reconstruction lineage:** the freeze manifest binds the upstream dataset hash/manifest hash, source hashes and vintages, configuration hashes, transformation-code hashes, grain/key semantics, and target semantics.
- **R5 — Independent audit:** the auditor checks identity, uniqueness, chronology, missingness, finite numeric values, required-family completeness, join diagnostics, OOS capacity, and leakage/provenance contract evidence.
- **R6 — Split safety:** a dataset with too few rows to leave an out-of-sample period after the configured initial training window is `not-fit`.
- **R7 — Fail closed:** any integrity or PIT-contract blocker yields `not-fit`; bounded non-blocking diagnostics may yield `fit-with-caveats`.
- **R8 — Current empirical state:** `phase-c-evidence.json` must state that the real full-V1 freeze is blocked while Phase B reports `full_v1_ready=false`; synthetic fixtures may test machinery but are not research evidence.
