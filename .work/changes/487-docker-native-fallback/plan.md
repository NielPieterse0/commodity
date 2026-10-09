# Issue 487 Implementation Plan

**Outcome:** Add a small reusable Docker execution fallback for blocked Windows-native DuckDB/Polars/PyArrow operations.

**Authority:** AGENTS.md, GitHub #487, phase-1 platform config and existing benchmark. Exact ownership is scope.json.

## Tasks in execution order

1. Claim WORK-487; isolate change/487-docker-native-fallback without modifying parallel work.
2. Read College Docker invocation and borrow its isolated binary-runtime model only.
3. Pin OCI base digest, exact Python dependency versions, Dockerfile/lock labels and image ID.
4. Build fail-closed host detection and explicit restricted Docker runner with safe output/temp staging.
5. Adapt only synthetic benchmark temporary/output paths for read-only runtime mounts.
6. Test policy-blocked/native-positive/forced-Docker/unavailable/mismatch/permissions and argument handling.
7. Provide operator guide, cache recovery, upgrade strategy, and audit of supply-chain gaps.
8. Run focused tests, lint, repository checks, KIS implementation review and GitHub exact-head CI.
9. Reconcile 1.5M-row runtime measurements and six-byte Parquet discrepancy; close only with evidence.

## Current boundaries

- No Supabase schema changes, source acquisition, native security bypass, protected outcome access or paid services.
- Docker daemon is now healthy on this Windows host; the restricted 1.5M-row benchmark has executed locally. Independent exact-head CI is still required.
- Exact library version lock is not a wheel-hash lock; do not overstate reproducibility.

## Verification focus

- Unit: deterministic command construction, error classification, image provenance, mount rules.
- Integration: reproducible 1.5M synthetic workload with resource/security settings.
- Governance: documentation, rule registry, Work/issue mapping, review and merge gates.
