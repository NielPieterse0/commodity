# Commodity isolated data runtime — Issue 487

This is a local Linux computation helper, not Supabase or a source archive.
Build requires Docker Desktop's Linux backend and build-time internet for
pinned Python wheels. Execution runs offline. Never disable Windows App Control.

## Preflight, build, run

1. Start Docker Desktop in Linux-container mode; check with docker info.
2. Create this worktree's approved .venv via scripts/environment/create_venv.ps1,
   using an approved C:/Projects base Python interpreter.
3. Launch scripts/environment/docker_data_runtime.py --build-image with
   the worktree-local .venv interpreter.
4. Run the 1.5-million-row synthetic benchmark using --mode docker
   (or --mode auto after verifying the checkout-local native environment).
5. Inspect .work/runtime/docker-data-platform/outputs/benchmark.json.
   Do not confuse synthetic evidence with actual NG source data.

Build input is restricted to docker/data-platform/. The base is pinned to
the official Python 3.11.17 slim Bookworm OCI image-index SHA-256.
Exact package version pins: DuckDB 1.5.6, NumPy 2.4.6, Polars 1.44.2
with polars-runtime-32, and PyArrow 25.0.1.
Built image ID, Dockerfile SHA-256 and requirements SHA-256 are recorded
in ignored .work/runtime/docker-data-platform/image-lock.json.
Execution uses the verified immutable image ID, never a mutable tag.
The runner rejects reparse points/symlinks in the runtime mount tree and
atomically replaces its image-lock record. The local user and Docker daemon
are trusted: another principal with write access to the runtime directories
can cause a residual check/use race. Keep those directories private; do not
run untrusted concurrent processes against the same workspace.


## Modes and isolation

--mode auto checks native imports using the worktree's own .venv.
Only a recognizable Windows native policy block triggers Docker fallback.
Missing packages and unrelated execution errors never trigger fallback.
--mode host requires healthy native imports. --mode docker explicitly
requires the verified Linux image.

Each Docker run disables networking, limits CPU to 2, RAM to 2 GiB and
PIDs to 128, drops capabilities, denies privilege escalation, runs as
UID/GID 65532 and uses a read-only root filesystem. Only scripts/data,
src and tracked config are read-only mounts. Ignored runtime output and temporary
folders are writable. No entire checkout or credential files are mounted.
Input is never mounted by default. Only approved staged unprotected input
beneath .work/runtime/docker-data-platform/inputs/ may be passed using
--input-dir. Source ownership and the original archive stay unchanged.

## Recovery and updates

- DOCKER_DAEMON_UNAVAILABLE: start Docker Desktop Linux engine.
- DOCKER_IMAGE_LOCK_MISSING_RUN_BUILD_FIRST: explicitly build the image.
- DOCKER_IMAGE_DIGEST_MISMATCH or changed input hashes: inspect provenance,
  then rebuild intentionally. Do not silently trust changed images.
- DOCKER_INPUT_MISSING or DOCKER_INPUT_NOT_APPROVED: stage only permitted
  non-protected data in the dedicated ignored runtime input area.
- DOCKER_OUTPUT_NOT_WRITABLE or DOCKER_EXECUTION_FAILED: check mounts,
  disk/memory limits and detailed error; do not retry on an unsafe host.
- Review upstream security and license notices on package/base upgrades.
- Inspect docker image ls and docker system df before removing only
  identified unused artifacts; do not prune other project caches.

## Open evidence

The live 1.5M-row #487 Linux benchmark repeats 85,249,539 Parquet bytes
(SHA-256 fb6901a038911c8d757ab376abc66b7e71d190fec9560e0e77dc38abe562cb37);
the retained Phase 1 Windows reference records 85,249,533 bytes
(SHA-256 3589634177ef922ffc1fbf82146d31e699722a3077a612253175bf8b72c4f5c0).
The six-byte, different-hash encoded file is reproducible within Docker;
the original reference file was not retained, so exact binary root cause
cannot be established. Query parity is asserted only for comparable
calculations. Phase 1's window query sorted by a non-unique trade_date,
so its result varied across runs; #487 adds settle and feature_6 tie breaks.
Repeated corrected window totals agree within floating-point tolerance.
See data/manifests/issue487-docker-benchmark.json for immutable snapshots
and CI's repeated-run checks. Exact wheels for Linux amd64 CPython 3.11
are SHA-256 locked in requirements.txt, and pip enforces --require-hashes at
build time. Wheels were downloaded in the digest-pinned Linux build environment
and their bytes hashed independently before inclusion. To update, download and
verify every new wheel for the target architecture before changing the lock;
never remove --require-hashes to make a build pass. The pinned Python 3.11.17
base image must be security-reviewed before production. No new paid subscription is required.

For a bounded data script, pass --script scripts/data/<name>.py and each
script argument with --arg=VALUE. In Docker mode use /input for explicitly
staged read-only inputs and /outputs for writable outputs. For example,
--arg=--input=/input/source.dbn and --arg=--output=/outputs/result.parquet.
No arbitrary absolute script paths are allowed.
