# Closeout: Docker Native Fallback

Status: OPEN — not PromotionReady.

## Scope implemented so far

- Isolated runner, pinned Docker build description and bounded input/output mounts.
- Host policy-block detection and explicit Docker mode.
- Synthetic benchmark integration and initial deterministic tests.
- Independent Docker-enabled GitHub Actions job and operator guide.

## Evidence and blockers

- Local worktree: change/487-docker-native-fallback.
- Local Docker Desktop Linux engine available, with #487 image ID `sha256:a78a5644cce5213e445d3206d753295f87e764851f65a03750d72c529c09ea72` checked against pinned build inputs.
- Live bounded Docker run and repeat both passed at 1,500,000 synthetic rows, 2 CPU/2 GiB, offline, no privilege escalation, readonly sources and separate outputs/temp.
- Docker Parquet `85,249,539` bytes, sha256 `fb6901a038911c8d757ab376abc66b7e71d190fec9560e0e77dc38abe562cb37` across repeated runs; Phase 1 reference `85,249,533` bytes, sha256 `3589634177ef922ffc1fbf82146d31e699722a3077a612253175bf8b72c4f5c0`. Exact binary cause not proven because original file is unavailable.
- Phase 1 window ORDER BY trade_date had duplicated keys and varied by ~3.35 across replays. Changed benchmark window ORDER BY trade_date, settle, feature_6. Repeat corrected results 4499521.356808823/4499521.356808826 agree within floating-point tolerance. Other four logical results agree with Phase 1.
- Machine-readable evidence: `data/manifests/issue487-docker-benchmark.json`. GitHub CI job separately builds/runs benchmark twice and checks source-bound comparable results.
- Initial `scripts/verify.ps1` line-ending failure was fixed. Fresh full `scripts/verify.ps1` after all runtime, test, Docker CI and documentation changes: 1,253 passed, 16 skipped, zero failures, one known duplicate-archive-name warning; documentation/rule checks, Ruff and Git whitespace all passed. The 1.5M-row Docker benchmark was rerun against the verified immutable image ID and produced 85,249,539 Parquet bytes with 4.065x input-to-memory ratio.
- 2026-10-09 supply-chain closure: downloaded the exact five CPython 3.11 Linux/amd64 wheels using the digest-pinned Python base in a temporary Docker build; independently hashed the wheel bytes, pinned SHA-256 per wheel in `docker/data-platform/requirements.txt`, and made pip enforce `--require-hashes --only-binary=:all: --no-deps`. The locked Docker image rebuilt successfully: `sha256:156e6fae2a95aa9cda91c567a842f0439473ae1093a7e94b661a0aba10103bbd`; Dockerfile SHA-256 `8d2b4861a5d1cf687bee2063ed7587324c9b82ec8a05f92493e3125b418166e0`, requirements SHA-256 `f9daeb24d3c5a8e420b0d440b9e17652c97b920874be1fbf0469c9085324bcea`. No claim of production base-image security approval; immutable wheel availability remains external.
- Staged KIS/Codex security reviews of runtime source identified and drove fixes for writable symlink mounts, effective Dockerfile FROM pinning, nested-script aliasing, mutable image tag execution and benchmark policy aliasing. A residual local TOCTOU race requires write access to the worktree's runtime directories; hardened checks and atomic image-lock replacement are implemented, but fully atomic directory-handle mounts are not available and the trust assumption remains explicit.
- KIS staged security review of the wheel-lock diff (Dockerfile, requirements, operator guide) found no actionable defects. KIS full old-head code-quality review identified the previously missing wheel hashes as its only medium finding; this fix addresses it. The security-boundary projector excluded existing runtime implementation from the old full-head security review; that review is not represented as full production security approval. Exact-head GitHub Actions, PR/merge/cleanup remain pending.
- KIS lifecycle discovered .work/runtime was not Git-ignored, making the worktree dirty after commit. Added an explicit .work/runtime/ ignore rule and updated owned_paths to keep generated image locks and benchmark outputs out of the governed tree.
- No Supabase data-plane modifications or protected data access.
