# Change Specification: V2 Parallel Optimizer Hardening

- **Change ID**: `435-v2-parallel-optimizer-hardening`
- **Status**: Draft
- **Complexity**: use live KIS schema-v4 classification

## Outcome

Harden Programme #393 optimization execution for identity-safe deterministic single/parallel worker runs and align repository multi-agent operation with KIS Work Management/issue coordination without modifying scored #425 evidence.

## Authority and scope

- Authoritative sources: Programme #393 V2 mandate; issue #425 execution-integrity finding requiring concurrent-runner prevention; `AGENTS.md`; `config/quantitative_research_knowledge.json` model-selection and attempt-history controls.
- Owned/shared/excluded paths: `scope.json`.
- Dependencies/integration ownership: `scope.json`; future #426-#431 runners consume this module without changing #425 scored code/evidence.

## Requirements mapping

- One canonical optimizer orchestrator may run multiple independent deterministic shards concurrently inside one governed change.
- Each shard has stable membership plus a path-safe shard ID reconstructed from frozen code/data/search-plan/evidence identity and exact shard membership.
- A shard is exclusively leased to one local worker; stale claims are detected but never silently stolen.
- Worker outputs are isolated, atomic, idempotent, resumable, and conflict-safe.
- Canonical trial reduction is deterministic and rejects stale fingerprints or conflicting duplicate trial IDs.
- Local optimizer worker count is bounded by host CPU capacity and supports both one-worker and multi-worker execution with identical deterministic reduction.
- KIS multi-agent development is a separate coordination layer: concurrent mutating agents use distinct Work/change identities, isolated governed worktrees, non-conflicting owned paths, and KIS reservation/lease fencing. The linked issue carries append-only assignment/progress/handoff comments; Work fields carry current operational state.
- Single-agent mode uses the same Work/issue protocol with one active worker lane. The optimizer runtime never grants authority for multiple agents to mutate the same governed worktree.
- This engineering change does not alter V2 selection objectives, chronological validation, protected evidence boundaries, or #425 results.

## Acceptance

1. Deterministic sharding covers each declared item exactly once, remains stable under input ordering, and produces identity-scoped path-safe shard IDs.
2. Manifest loading reconstructs shard IDs from identity/membership and rejects malformed, path-escaping, stale, or unreconstructable serialized IDs.
3. Concurrent local workers cannot acquire the same shard; stale claims are observable and fail closed.
4. One-worker and two-worker optimizer execution produce the same deterministic merged result; completed shards resume without rerun.
5. Repository operating rules require distinct KIS Work/change/worktree ownership for concurrent agents, issue-comment handoffs, Work-field state, and preserve a one-agent mode using the same protocol.
6. Result writes and reduction are atomic/idempotent and reject identity or duplicate conflicts.
7. Focused tests, change workflow checks, applicable review, and repository verification pass.

## Risks and recovery

- Risk: parallelism could create duplicate/conflicting evidence or oversubscribe the host.
- Recovery: isolated shard results, exclusive leases, host-bounded workers, deterministic reduce, and fail-closed conflict checks allow safe retry from completed shards.

## Out of scope

- Re-scoring or modifying issue #425.
- Changing scientific search spaces, winner criteria, protected confirmation gates, paper/SIM/LIVE promotion, or trading permissions.
