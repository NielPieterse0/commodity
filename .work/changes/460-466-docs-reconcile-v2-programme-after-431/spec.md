# Change Specification: 466 Docs Reconcile V2 Programme After 431

- **Change ID**: `460-466-docs-reconcile-v2-programme-after-431`
- **Status**: Implemented, pending verification/review
- **Complexity**: medium
- **Risk trigger**: `public_contract`

## Outcome

Reconcile Programme 004 canonical metadata through #431/#459 and register #465 as the final broad V2 development stage before #414 champion freeze, without new empirical scoring or protected-evidence access.

## Authority and scope

- Programme authority: #393 and `research/programmes/004-v2-maximum-reproducible-one-month-return/programme.json`.
- Source evidence: `issue459-wave2-result-v2.json`, `issue429-result-v1.json`, `issue430-result-v1.json`, `issue431-result-v1.json`, and `issue459-advantage-map-v1.json`.
- New handoff authority: GitHub issue #465.
- Existing post-V2 boundary: GitHub issue #449 / Programme 005 V3.
- Owned/shared/excluded paths and base identity: `scope.json`.

## Requirements mapping

1. Replace stale #425-era backlog state with #465 followed by #414.
2. Preserve exact historical conclusions while summarizing landed development evidence through #431/#459.
3. Record #431 `decay20` value together with its one-session-delay failure; do not convert the HOLD into a promotion.
4. Register the adaptive time-instance procedure as the final broad V2 development object; do not repurpose V3.
5. Regenerate human reference pages deterministically from the canonical JSON owners.

## Acceptance

1. Programme 004 backlog names #465 as next broad development work and #414 as its downstream freeze gate.
2. Decisions/evidence/line metadata cite the existing source artifacts and do not rewrite their scientific dispositions.
3. `protected_confirmation_accessed` remains false and all later evidence stages remain sealed.
4. All changed canonical JSON validates against its repository schema.
5. Generated documentation is fresh under `scripts/docs/generate_docs.py --check`.
6. Repository-required verification and independent implementation/documentation review pass before merge.

## Risks and recovery

- **Risk**: documentation accidentally upgrades development evidence into confirmation or weakens a prior HOLD/negative.
- **Control**: retain exact disposition language and source references; no empirical runner is executed by this change.
- **Recovery**: revert this documentation/governance commit; upstream scientific artifacts remain unchanged.

## Out of scope

- New empirical trials, tuning, model fitting, data acquisition, protected 2023+ confirmation, prospective paper, Saxo SIM or LIVE.
- Changing any #459/#429/#430/#431 source result artifact.
- Implementing #465 itself.
