# Phase C Implementation Plan

## Task 1 — Freeze contract (R1-R4)
- [ ] Add RED tests for full-V1 gating, deterministic identity, immutable writes, and reconstruction lineage.
- [ ] Implement content-addressed dataset freeze/load verification.
- [ ] Bind configuration and transformation hashes without volatile timestamps.

## Task 2 — Independent dataset audit (R5-R7)
- [ ] Add RED tests for uniqueness, chronology, missingness, non-finite values, join coverage, and OOS-capacity blockers.
- [ ] Implement deterministic `fit` / `fit-with-caveats` / `not-fit` audit output.
- [ ] Ensure no synthetic fixture can be confused with empirical V1 evidence.

## Task 3 — Current Phase C evidence (R8)
- [ ] Read Phase B evidence and record the real freeze as blocked when `full_v1_ready=false`.
- [ ] Record machinery verification separately from empirical readiness.

## Task 4 — Review, verify, close
- [ ] Run focused RED→GREEN tests, full pytest, Ruff, diff check, and changed-file secret scan.
- [ ] Attempt independent review; manually review exact diff if reviewer backends remain unavailable.
- [ ] Commit the exact reviewed Phase C machinery while keeping Phase D blocked until a real audited full-V1 dataset exists.
