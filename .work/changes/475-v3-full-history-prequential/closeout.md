# Closeout: V3 Full History Prequential

## Implemented scope

- Implemented the frozen #475 pre-2023 full-history prequential engine, runner, bounded candidate ladder, lifetime evidence, robustness gates, protected-window enforcement, authoritative traversal artifacts, and Programme 004 reconciliation.
- Authoritative traversal ran once from freeze commit `81066f40912b7c4aadcfde9152b5d717c286718e`; protected 2023+ confirmation remained unopened.
- Frozen disposition: `NO_SUFFICIENTLY_ROBUST_EDGE`; always-short remains a research lead, not a promoted edge.

## Implementation evidence

- Pre-closeout implementation head: `b84b3d53c4d388e23f00c9b307eead6fcca05152`.
- Canonical verification: `pwsh -NoProfile -File scripts/verify.ps1` -> exit 0; 1,209 passed, 12 skipped, 1 warning; all governance checks and git-whitespace passed.
- Review closure: KIS whole-change projector returned `manual_fallback mode=exact-diff` because the bounded projector omitted large source/test/evidence files. Manual exact-diff review covered `src/commodity/v3_prequential.py`, the #475 runner, focused tests, freeze/result identity linkage, and post-freeze source changes. No material findings remained.
- Post-freeze source changes from `81066f4..b84b3d5` are representation/lint-only: typing import location, equivalent champion-selection expression, redundant integer conversions, a lint annotation, and JSONL trailing-newline normalization. The authoritative result retains the original freeze commit and engine/runner hashes.
- PromotionReady / reusable evidence: pending final committed-tree verification and KIS PR promotion.

## Provider and landing evidence

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: pending.
- Cleanup: pending.

## Research return, when applicable

- Upstream L3 authority: GitHub issue #475 plus Programme 004 line/inference/decision/sealed-window authorities.
- Exact implementation/landing identity returned to research lineage: authoritative runtime head `81066f40912b7c4aadcfde9152b5d717c286718e`; final landing identity pending.
- Any scientific escape/re-entry: none. No rescue tuning or scientific-contract change occurred after the frozen traversal.

## Residual items

- Benchmark lane totals include the initial 252 history rows while the adaptive controller is deliberately flat during those rows. A diagnostic equal-window recalculation leaves always-short severe return strongly positive (+1.08980 versus +1.12745 full-history) and does not change the frozen `NO_SUFFICIENTLY_ROBUST_EDGE` disposition. Do not describe the aggregate benchmark and adaptive totals as equal-window direct performance without stating this window difference.
- Complete KIS PR preparation, exact-head Actions, merge, Work reconciliation, and worktree cleanup.
