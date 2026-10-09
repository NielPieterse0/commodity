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
- [x] Reconcile KIS change/review and verification evidence for the merged scope; retain explicit limitations of the full-head security evidence projector and separate production security assessment.
- [x] Run actual Docker benchmark twice, reproduce six-byte difference, preserve both SHA-256 identities and document unresolved binary cause.
- [x] Capture and enforce Linux/amd64 CPython 3.11 wheel-file SHA-256 hashes; rebuild the image and verify immutable image ID and build-input hashes.
- [x] Confirm exact-head PR #488 GitHub Actions (verify and docker-data-runtime passed on `61a82956f8726c332b87e8f4bbb257a9c7f8e33b`) and comparable logical result parity; byte-for-byte Parquet equivalence is not claimed.
- [x] Merge PR #488 as `a1d8da618f4f1ebe60aa1a64802cdd89832254e5`; close GitHub issue #487, reconcile KIS Work Management to Done, fast-forward local main, and remove the merged worktree/local branch.
