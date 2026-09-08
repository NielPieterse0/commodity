# Change: Preserve Roberts 2019 Brown-Yucel Replication Package

- **Change ID**: `343-preserve-roberts-replication-package`
- **Risk Profile**: lean

## Outcome

Preserve the operator-supplied Roberts (2019) *Revisiting the Drivers of Natural Gas Prices* replication package as immutable durable raw evidence for #327 / rep-012, with exact DOI, source/archive/member SHA-256 identities and no empirical interpretation or sealed-confirmation access.

## Scope and acceptance

- Preserve the supplied ZIP bytes unchanged under `data/raw/snapshots/iree/roberts-2019-revisiting-drivers`.
- Bind DOI `10.15456/iree.2018197.145241`, original filename, byte size, SHA-256, citation, and archive-member identities.
- Retain `brownyuceldata.dta`, `bycommands.do`, and `citation.txt` unchanged for direct source-study reproduction.
- Link preservation issue #343 and Phase-1 parent #327.
- No new downloading, acquisition plumbing, outcome interpretation, or sealed-confirmation access.

## Implementation and verification

- Original archive SHA-256: `d0b1bc18101438cabae21107f12e13fc4a9e9313447e273e0f8c129aae52a895`; 91,436 bytes.
- Dataset manifest SHA-256: `68ceedcc9c6900064a3694e4a05a3b521e138fd2eac7a92c76f89eca486095b0`.
- Every archive member was hashed directly from the source ZIP and matched its extracted durable copy exactly.
- Member SHA-256 identities: dataset `eaa3f5bd14cd72eaef7f3cff962465243e36ae9152ec0f3e1a29dd6763204c35`; command file `4af333341c5a22fe2e4ff17568b27b839651f8bd87d4c664fbe27f7e4c1663a0`; citation `f754d5acec047d5abbef497c035720fcd4140999013036bca681458a170b395b`.
- The durable raw snapshot is intentionally ignored by Git; `acquisition-evidence.json` binds its immutable identity to the tracked change record.
- License was not independently verified and is recorded as `not_verified` rather than inferred.

## Review and verification status

- Worktree-local Python preservation replay passed all five identity checks: operator source = durable ZIP, manifest hash matches, and all three archive members equal their extracted copies.
- Focused change-workflow contract tests: `2 passed`.
- Canonical `scripts/verify.ps1` passed documentation, rule, environment, durable-evidence, source-authority, data-assurance, work-layout, public-hygiene, documentation-authority, experiment, inference, metrics, and memory checks.
- The same local verification run completed `437 passed` tests and `6 failed`; all six failures are the known Windows Application Control block on the worktree-local `pyarrow._parquet` DLL in Databento-provider tests. No changed path is involved. Exact-head CI remains required for a clean cross-environment pass.
- Initial specialist review raised one procedural finding: `acquisition-evidence.json` was still untracked at review time. The governed commit/PR must include it; an exact-commit review will verify that resolution before landing.
