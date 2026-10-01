# Closeout: Historical Evidence Recombination Joint Advantage Discovery

## Implemented scope

- Built the deterministic historical advantage map and frozen #459 Wave 1 joint search.
- Completed Wave 1: 3,168 outer-level trials / 528 policies / 0 promotions.
- Froze Wave 2 mechanically around all 8 eligible Wave 1 parents plus PIT-safe TimesFM-short and Kronos-long specialist roles.
- Completed Wave 2: 276 outer-cost trials / 46 policies / 2 development promotions; protected 2023+ confirmation remained unread.

## Implementation evidence

- Source revision/tree: working-tree fingerprint pending final review/commit binding.
- Focused verification: 89 focused #459 tests passed; Ruff passed.
- Canonical verification: `scripts/verify.ps1` passed with 1,017 tests passed / 7 skipped and all repository gates green.
- Canonical LF Wave 1 preflight SHA: `2494085ae50fa66b555797618a5dfee81e4d39299ce3989452db2bf4bf2ccf87`.
- Canonical LF Wave 1 result SHA: `1c8b8f86aae5a1c8386b87ed58d63d8bd161b341e0e7dc8e103db099ea53ecc0`.
- Wave 1 trial-ledger SHA-256 remained unchanged: `9203b1365cc9117b52ab662ed49feb934545cf39e7a37aa377b21709ab6dbd5c`.
- Wave 2 prereg v2 file SHA-256: `c90b20f799bd7443c301e677dae282ce22078b5bc38e823541dba22f909f257f`.
- Wave 2 v2 preflight identity: `52bd31935b8302808be408d00c1454f9c9a8f97b66d14428a9e427cc57fa744b`.
- Wave 2 v2 result identity: `66ea6671e8a5dc05d291f8bc125117eed1190bd2b8efbebd4931444f34ebe961`.
- Wave 2 v2 trial-ledger SHA-256: `d1bacc02331fe0a0dc6d8368346d0210ebfc70966c65c3bdda7c560e51e2aa86`.
- Pre-landing identity rebind: the advantage-map JSON was semantically identical but canonicalized from CRLF to repository-authoritative LF; Wave 1 was rerun and the 8-parent Wave 2 eligibility set remained identical. Final verification then exposed an identity-domain mismatch in Wave 2 prereg v2: `parent_wave1.result_sha256` had been rebound to the Wave 1 JSON file hash instead of its semantic result identity. The prereg now preserves semantic `result_sha256` `b4e6ce357f89ccde4e906ebc5d84ee74ae65eb155771588febf6a97a621cedfc` and explicit canonical-LF `result_file_sha256` `1c8b8f86aae5a1c8386b87ed58d63d8bd161b341e0e7dc8e103db099ea53ecc0`; Wave 2 was rebound and rerun with unchanged candidate space, eligible parents, ledger SHA, promotions, and economics.
- Review closure: exact-diff code-quality and test-quality reviews completed with zero findings on the final core source/test slice; unchanged runner/evidence-map slices were previously reviewed clean.
- Exact-head CI portability repair: the first PR run showed that the source-bound Wave 1 preflight test depended on the non-versioned local #448 parquet/family cache. The test now skips only when those cache artifacts are absent; in the full-data development worktree the same test still executes and passes, so the scientific preflight contract is unchanged.
- PromotionReady / reusable evidence: implementation and scientific evidence are verification-clean; pending final exact-head CI/landing.

## Provider and landing evidence

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: generated reference projections are current; final reconciliation pending landing.
- Cleanup: pending landing.

## Research return, when applicable

- Upstream L3 authority: `issue459-prereg-v1.json` plus frozen `issue459-wave2-prereg-v2.json`; v2 explicitly supersedes local pre-landing Wave 2 prereg v1 for identity-only LF rebinding.
- Strongest Wave 2 development candidate: `both__strength_q50__f1.00__loss_cooldown_3_sessions__short_none__long_veto`.
- Candidate mean outer monthly net-return delta: +0.00324275; 2019-2020 +0.001048 and 2021-2022 +0.0054375 at base cost.
- Specialist incremental effect: +0.00256/month in 2019-2020 and 0 in 2021-2022, repairing the weak early outer without reducing the later outer.
- Candidate passed effective-sample, concentration, higher-cost, cross-outer nonnegative, and kill-regression gates.
- Exact implementation/landing identity returned to research lineage: pending landing.
- Any scientific escape/re-entry: none; Wave 2 stayed within the frozen preregistration.

## Residual items

- Close KIS review, prepare PR, require exact-head CI, merge, and reconcile landing evidence.
