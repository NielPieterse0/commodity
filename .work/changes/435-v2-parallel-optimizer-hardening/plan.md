# V2 Parallel Optimizer Hardening Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Add reusable safe deterministic parallel optimization orchestration for Programme #393 future winner-search issues without modifying the already-scored #425 implementation or evidence.

**Architecture:** Describe only the smallest repository implementation needed. For research-originated work, reference the L3 authority instead of reproducing scientific reasoning.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific/requirements authority; implementation planning cannot redefine it.
- Use focused tests/verification during development and let the live KIS lifecycle decide what evidence is missing or stale.
- Do not rerun valid implementation evidence merely because the workflow was interrupted.

### Task 1: Parallel execution integrity

**Files:**
- Add: `src/commodity/v2_parallel.py`
- Add: `tests/test_v2_parallel.py`

- [x] Bind the change to Programme #393 and the #425 duplicate-runner integrity finding without altering scored #425 code/evidence.
- [x] Add deterministic balanced shard planning bound to frozen code/data/search-plan/evidence identity.
- [x] Make serialized shard IDs identity-scoped, path-safe, and reconstructable from exact shard membership; reject malformed manifests fail-closed.
- [x] Add exclusive shard leases, heartbeat/liveness state, stale-claim detection, and host-bounded worker count.
- [x] Add atomic idempotent per-shard result persistence and deterministic conflict-safe canonical reduction.
- [x] Add a bounded concurrent orchestrator that resumes completed shards instead of rerunning them.
- [x] Prove deterministic equivalence for one-worker and two-worker optimizer modes.

### Task 2: KIS agent operating contract

**Files:**
- Modify: `AGENTS.md`
- Modify: `config/rule_verification.json`
- Generate: `docs/rule-verification.md`

- [x] Require scheduled/multi-agent coordination through live KIS Work Management and linked issue comments rather than chat/session memory.
- [x] Require separate Work/change identities and governed worktrees for concurrent mutating agents, with KIS reservation/lease fencing and non-conflicting owned paths.
- [x] Preserve single-agent mode using the same Work/issue protocol with one active worker lane.
- [ ] Complete governed review/verification and land before #426 consumes the module.
