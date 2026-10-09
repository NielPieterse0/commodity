# Change Specification: Issue 487 Docker Native Fallback

- Change ID: 487-docker-native-fallback
- Complexity: medium (schema-v4 scope.json)
- State: implementation in progress
- Requirements authority: GitHub issue #487; roadmap #481; Phase 1 #479; Phase 2 #482.
- Exact owned paths and risk triggers: scope.json.
- Scientific methodology, PIT, protected outcomes and archive architecture stay under their canonical owners.

## Bounded runtime contract

- Windows native execution uses this checkout's own approved .venv.
- Auto mode falls back only on an explicitly identified Windows native-policy block.
- Docker execution is default-offline with hard CPU/memory/PID, privilege and mount restrictions.
- Docker image build requires a digest-pinned base and exact package versions; runtime verifies local image ID and source-lock provenance.
- Never mount the checkout root, environment secrets or protected outcomes.
- Allow only bounded scripts/data workloads, explicit approved input staging and ignored output/temporary folders.
- Preserve non-native errors and reject unavailable Docker without host retry.
- Supabase remains optional catalog/control; it does not execute the Linux runtime.

## Acceptance evidence

- Simulated host/blocked/Docker/mismatch/unavailable/permissions/input tests.
- Fresh KIS verification and code review bound to this governed worktree.
- GitHub Actions exact-head 1.5M-row synthetic benchmark under Docker restrictions.
- Record actual Parquet sizes, hashes, workload results, and explain reported six-byte difference.
- No new paid services, Windows policy changes, or access to reserved 2023+ data.

## Deferred blockers

- Docker Desktop Linux engine is available and the 1.5M-row synthetic benchmark executes with restricted Docker flags.
- Dependency wheel-file SHA-256 locking and physical Parquet byte parity remain unproven.
- Residual concurrent local filesystem mutation is outside the trusted single-operator threat boundary and must not be overlooked.
- Do not merge or close until the required live benchmark and KIS/CI gates are green.
