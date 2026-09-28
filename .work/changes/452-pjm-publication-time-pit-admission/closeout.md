# Closeout: Power Publication Time PIT Admission

## Implemented scope

- Preserved PJM publication-time and NYISO overwrite evidence as fail-closed source-level HOLDs.
- Superseded the preregistered source ladder to MISO, implemented the MISO adapter/acquisition/audit path, and captured the full 2011-2022 archive locally.
- Persisted a tracked 144-month archive/feature/hash index covering 4,383 daily reports, 4,374 admissible PIT days, and 9 declared publication-date exclusions.
- Re-entered source-identifiable power features into frozen #426 development scoring; `issued_revision` remains source-unidentifiable and held.
- Completed 166 power trials. Both supported outer periods fail the matched marginal-value retain criterion; aggregate mean-monthly-return delta is `-0.00038775510204081665`.
- Reconstructed all 2,908 weather issue days but failed exact frozen #426 replay; power×weather therefore remains unexecuted under the fail-closed production gate.

## Implementation evidence

- Source revision/tree: pending final governed commit.
- Focused verification: 90 passed across MISO, NYISO, and V2 optimization tests; changed-file Ruff check passed.
- Canonical verification: `scripts/verify.ps1` passed with 852 tests passed, 7 skipped; documentation, rule registry, environment, durable evidence, data assurance, research integrity, public-repository hygiene, Ruff, and Git whitespace checks passed.
- Review closure: exact-worktree KIS source/test slice reviews closed. MISO and NYISO source reviews are clean after fail-closed lineage/parser fixes; provider and orchestration test-quality reviews are clean after boundary additions. The oversized `v2_optimization.py` whole-file projector used the AGENTS.md exact-diff fallback after complete earlier review rounds; all actionable findings were fixed and regression-tested.
- Power trial ledger: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-power-trials-v1.jsonl` (`sha256=88a646d8db7a49b9b1fb96447cd715cfc8bf6ac7ec2eedbe6551268bd885628f`).
- MISO manifest index: `dd28e7a8ab08c39a735f68c366e46eaae7fb2cd7269fe1ccfdb5428f854d78ea`.
- Authoritative result: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue452-result-v1.json`.

## Provider and landing evidence

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: pending verification and landing.
- Cleanup: transient acquisition/replay material moved recoverably to ignored `.work/scratch`.

## Research return

- Upstream L3 authority: `issue452-power-source-ladder-v2.json`, `issue452-miso-historical-audit-v1.json`, and frozen #426 search/optimization/weather contracts.
- Development conclusion: MISO power is PIT-admissible but does not establish matched marginal value on the supported outer periods; the power×weather interaction remains held because reconstructed weather did not reproduce frozen #426 evidence.
- Exact implementation/landing identity returned to research lineage: pending governed commit/merge.
- Scientific escape/re-entry: weather reconstruction mismatch is preserved explicitly; no approximate substitute was admitted.

## Residual items

- KIS reviewable PR preparation, exact-head CI, merge, local-main refresh, Work reconciliation, and cleanup.
