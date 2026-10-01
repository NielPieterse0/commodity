# Closeout: V2.32 Entry / Exit / Holding / Position Structure

## Implemented scope

- Frozen development-only preregistration: `issue429-prereg-v1.json` SHA `0ec059451809fc65d2e8543cb51235c3abd151d0ae483eeaa2503341191bb73e`.
- Reconstructed the promoted #459 parent before scoring and bound #448 cache, #459 parent/result/ledger, specialist, cost, and safety identities.
- Added matched contribution ablations and 12 bounded lifecycle transforms with protected 2023+ evidence sealed.
- Executed the complete frozen budget: 114 outer x cost trials across 2019-2020 and 2021-2022 at base, 1.5x, and 2x costs.

## Scientific result

- Disposition: `NO_ISSUE429_LIFECYCLE_IMPROVEMENT`; 0 / 12 lifecycle variants passed every frozen promotion gate.
- Removing the strength gate reduced mean monthly return by `0.596100%` across outers; it is the largest measured parent contribution.
- Removing the three-session loss cooldown reduced mean monthly return by `0.440408%` across outers.
- Removing the Kronos long veto reduced mean monthly return by `0.128000%` across outers; TimesFM is inactive in the promoted parent.
- Removing retained TA decision context, positioning decision context, or volatility-tail decision context changed return by exactly `0.000000%` in both outers. These families do not carry the promoted strength-gate policy.
- `max_hold_3_sessions` was the cleanest lifecycle near-miss: `+0.026042%/month` mean versus parent, nonnegative in both outers, higher-cost robust, effective-sample pass, and no kill regression, but it failed the frozen concentration gate.
- `hold_on_abstain__max_hold_3` had a larger mean gain (`+0.107608%/month`) but was negative in 2019-2020 and failed concentration / higher-cost robustness, so it was not promotable.

## Evidence identities

- No-scoring preflight identity: `a787720492d9fc67cdd29503781d06efe87023b82f51313c08d53b00acb92437`.
- Runner SHA: `64a062a0d9e2048a64fff5ac216cae0a52ca2711985d20ba6b0c529e3904076e`.
- Trial ledger file SHA: `c3ef3f917cf2bfbaeb2b9690f5766d6b6f693cca110870477c549aeaf4ab56c8`.
- Result identity: `2b800943f250867278b952555994204fb5dcf98c7fd058894947064470333430`.
- Result file SHA: `89134b272b4d9f2d6fe73ee1721abe5e18e2b688b7bda57d4c3a95687d38d699`.
- Deterministic rerun reproduced the ledger and result-file hashes exactly.

## Implementation verification

- Focused #429 tests: `11 passed`.
- Ruff on runner/tests: clean.
- Canonical `scripts/verify.ps1`: `1028 passed, 7 skipped, 1 warning`; all repository gates passed.
- Independent KIS code-quality review of the exact runner/tests: completed with no findings.
- Protected 2023+ confirmation remained unread throughout preflight, scoring, rerun, verification, and review.

## Landing status

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: pending.
- Cleanup: pending.
