# Change Specification: V2 Optimization Harness

- **Change ID**: `424-v2-optimization-harness`
- **Status**: Draft
- **Complexity**: use live KIS schema-v4 classification

## Outcome

Implement the development-only V2 optimization execution harness, trial ledger, common monthly score engine, frozen V1 comparator, conditional search support, and bounded resumable pilot required by issue #424 without accessing protected confirmation, prospective paper, Saxo SIM, or LIVE evidence.

## Authority and scope

- Authoritative sources: GitHub issue `#424`; parent Programme `#393`; `config/v2_variable_registry.json`; `config/phase2_market_only.json`; Programme-003 development evidence through `2022-12-31`.
- Owned/shared/excluded paths: `scope.json`.
- Dependencies/integration ownership: `scope.json`.

## Requirements mapping

- Enforce the registry evidence boundary: search may use only `development` or `rolling_research_oos`; `reserved_confirmation` and `true_forward` must fail closed.
- Add deterministic trial identities and an append-only/idempotent JSONL ledger binding config, seed, code identity, dataset identity, evidence class, status, and score/disposition.
- Add one common monthly score contract whose primary economic measure is net return on starting paper capital and whose diagnostics cover drawdown, monthly distribution, costs, turnover, exposure/leverage, trade count, side contribution, concentration, and stability.
- Support bounded interacting search axes drawn from the authoritative registry without rewriting it.
- Bind frozen V1 by immutable repository identity only; V1 remains unchanged and protected post-2022 outcomes are not used for V2 search.
- Run a bounded, resumable pilot on development-only pre-2023 evidence to prove the harness before family optimization begins.

## Acceptance

1. Protected evidence classes are rejected before a trial can be recorded or scored.
2. Identical trial/config/data/code inputs produce the same trial identity; conflicting duplicate ledger writes fail closed and exact reruns are idempotent.
3. Monthly scoring is deterministic and emits all Programme-393 required diagnostics from a chronological per-session ledger.
4. Registry-selected conditional/interacting axes are validated against declared candidates/bounds and carry interaction coverage metadata.
5. A bounded pre-2023 pilot writes durable Programme-004 evidence and a second invocation resumes without re-executing completed trials.
6. Focused tests and repository verification pass, subject only to separately evidenced base/environment failures.

## Risks and recovery

- Risk: accidental use of exposed post-2022 outcomes during V2 search. Recovery: fail closed on evidence class/cutoff and delete no evidence; create a new candidate identity if contamination occurs.
- Risk: trial-ledger interruption or duplicate writes. Recovery: atomic append plus deterministic identity permits safe resume and detects conflicts.

## Out of scope

- Family-level V2 optimization beyond the bounded harness pilot.
- Reserved confirmation, prospective paper, Saxo SIM, Saxo LIVE, or any broker order submission.
