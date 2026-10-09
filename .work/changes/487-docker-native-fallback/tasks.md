# Tasks: Docker Native Fallback

- [x] Read repository instructions and KIS skills.
- [x] Claim WORK-487 and create isolated worktree.
- [x] Preserve unrelated main .env.example edit byte-for-byte.
- [x] Inspect College Docker invocation and the #479 synthetic benchmark.
- [x] Add pinned Linux Dockerfile, version pins and provenance enforcement.
- [x] Implement host-first native blocking detection with explicit Docker mode.
- [x] Add bounded mounts, offline execution, hard limits and failures.
- [x] Adapt benchmark temporary and output paths.
- [x] Add initial simulated tests and Docker-specific GitHub CI job.
- [x] Add runtime operator and recovery guide.
- [x] Expand tests for host, policy-block, no-Docker, digest, mounts, bounded arguments and fatal-error conditions; add independent repeated-benchmark CI checks.
- [ ] Reconcile registered KIS verification and reviews.
- [x] Run actual Docker benchmark twice, reproduce six-byte difference, preserve both SHA-256 identities and document unresolved binary cause.
- [x] Capture and enforce Linux/amd64 CPython 3.11 wheel-file SHA-256 hashes; rebuild the image and verify immutable image ID and build-input hashes.
- [ ] Confirm exact-head CI and source parity.
- [ ] Complete PR, merge, Work reconciliation and cleanup via KIS.
