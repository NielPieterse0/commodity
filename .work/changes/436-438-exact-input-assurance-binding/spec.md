# Change Specification: 438 Exact Input Assurance Binding

- **Change ID**: `436-438-exact-input-assurance-binding`
- **Status**: Implementation verification
- **Complexity**: `medium`; risk trigger `public_contract`

## Outcome

Bind #355 research-ready assurance to the exact runtime market, selected-path, and features identities so a valid assurance for different data cannot authorize a decision run.

## Authority and scope

- GitHub issue #438 acceptance criteria.
- Audit finding F1 in `.temp/audit-354-355/AUDIT_REPORT.md`.
- Existing #355 decision-system contract and protected-evidence boundary remain authoritative.
- Owned/shared/excluded paths and lifecycle classification: `scope.json`.

## Requirements mapping

- `src/commodity/trading_decision_v0.py`: require one canonical decision-input binding whose identity covers the research-ready assurance, instrument, roll policy, evidence partition, and exact market/selected-path/features role hashes.
- The research-ready assurance must independently cover each runtime role with one verified artifact layer and one explicit transformation identity. Missing, partial, duplicate, invalid, or mismatched coverage fails closed.
- `src/commodity/cli.py`: retain the validated decision-input binding SHA-256 in the deterministic run manifest.
- `tests/test_trading_decision_v0.py`: prove exact binding succeeds; valid-but-unrelated assurance fails; partial assurance fails; missing transformation identity fails; context mismatch fails; legitimate CLI reconstruction remains deterministic.

## Acceptance

1. A research-ready assurance for different runtime artifacts is rejected even when a syntactically valid binding names the observed files.
2. Partial assurance coverage is rejected.
3. Selected-path and feature artifacts require explicit assured transformation identities.
4. The binding identity covers assurance SHA-256, exact input roles/hashes, instrument, roll policy, and evidence partition.
5. Existing legitimate #355 CLI behavior remains deterministic and reconstructable.
6. Focused verification, repository verification, and independent code-quality/architecture review close without material findings.

## Risks and recovery

- **Risk:** This intentionally tightens the public input-authority contract; legacy boundary files without exact assurance coverage and binding evidence fail closed.
- **Recovery:** Regenerate the governed input-authority artifact from the exact assured runtime files. Do not weaken validation or accept legacy self-attestation.

## Out of scope

- #439 persistent killed-state semantics.
- #440 historical #354/#355 governance reconciliation.
- V2 optimization/search behavior, model selection, or protected confirmation evidence.
- Any `kis-mcp` implementation, upgrade, or tooling request.
