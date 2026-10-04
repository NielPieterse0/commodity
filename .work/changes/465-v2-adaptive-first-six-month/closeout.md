# Closeout: V2 Adaptive First Six Month

## Implemented scope

- Implemented only issue #465 `block-001`, 2010-07-06 inclusive through 2011-01-06 exclusive; later blocks were not accessed.
- Built the frozen PIT state, 1,126-policy candidate field, separate consequence memory, causal prior-only adaptive selector, deterministic ledger/result outputs, and non-tradable hindsight-oracle diagnostic.
- Canonicalized duplicate PIT decisions that map to one executable fill by retaining the latest PIT signal, reducing 124 structural origins to 123 executable decisions.
- Corrected policy-ID handling in the consequence engine before empirical scoring; the correction produced no empirical output before the final frozen run.
- Preserved the already-scored CRLF byte identity of exact hash-bound block-1 evidence through narrow per-file `.gitattributes` `-text` exceptions; this avoids post-scoring hash mutation while leaving the repository-wide LF policy and future block evidence unchanged.

## Implementation evidence

- Source revision/tree: working change `465-v2-adaptive-first-six-month`; exact landing identity pending KIS publication.
- Frozen preregistration: `issue465-prereg-v1.json`, SHA-256 `545f67b1541d19b4fd6c3e9b89cfca981474ae6ac2a6a85d9ca419bcca5ee88f`; adaptive freeze SHA-256 `897316924cbf1782e441d7e3c452cdf5c4c96f861956b32ab12a95c11516755b`.
- Focused verification: current issue-465 focused suite passed with 89 tests. Fresh canonical `scripts/verify.ps1` verification passed with 1,162 tests passed, 12 skipped, all repository authority/generation/rule checks green, Ruff green, and git-whitespace green.
- Review closure: the KIS whole-range reviewer returned the repository-declared `manual_fallback` with `mode=exact-diff` because the full source projection exceeded bounded review evidence. The exact committed source/test range `ac12f2200d252490c73a0779defa91ccf67fccf3..affec961e75ae550a750881fcc7bce949e21f71f` was therefore reviewed under that fallback. No new non-replay findings were identified; the known complete future-invariance/performance boundary remains explicitly transferred to #468. Durable review evidence is recorded in `evidence/manual-exact-diff-review.json`.
- PromotionReady / reusable evidence: exact immutable commit/lifecycle decision pending.

## Provider and landing evidence

- Pull request exact head: pending KIS publication.
- Provider-native GitHub Actions: pending exact-head PR verification.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: change-local record only; classified documentation impact is `none`.
- Cleanup: pending landing/closeout.

## Research return, when applicable

- Upstream authority: L2 `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json` plus frozen `issue465-prereg-v1.json`.
- Block-1 causal result: post-warmup net return `-14.6175%`, max drawdown `28.1843%`, transaction cost `$967.50` (`0.9675%` of initial capital), and max margin utilization `10.2898%`.
- Candidate-field diagnostic: `609/1,126` frozen fixed policies were positive over the same 93-decision post-warmup period; strongest fixed policy `season_cos_direct:1__h10__symmetric__x1p5` returned `+23.4750%`.
- Selector diagnostic: across all 93 post-warmup decisions, the selected policy's causal trailing-30 score averaged `+15.2499%`, while its next-decision candidate return averaged `-0.1521%`; correlation was `0.0448203`. The selector chose `1.5` contracts on `92/93` decisions.
- Oracle diagnostic: non-tradable hindsight oracle return `+104.1900%`; oracle-minus-causal selection gap `+118.8075` percentage points.
- Interpretation: block 1 contains substantial exploitable candidate structure, but the frozen winner-take-all prior-30 selector does not identify persistent winners. Costs and leverage are not the primary failure explanation. The next scientific iteration should replace or materially revise selection/state inference rather than blindly expand the signal universe.
- Seal evidence: `protected_confirmation_accessed=false`, `later_blocks_accessed=false`; block 2 and protected 2023+ confirmation remain unread.
- Exact implementation/landing identity returned to research lineage: pending KIS landing identity.
- Scientific escape/re-entry: required before any later-block execution because the frozen selector materially failed its intended adaptive role; block-1 outputs remain frozen evidence and must not be rescored under the revised selector.

## Successor handoff and residual items

- This change is being landed as the canonical implementation/evidence baseline for the V3 Block-1 controller. Landing #465 does **not** assert that the replay-dependent acceptance criteria are satisfied.
- The current frozen preflight remains `PREFLIGHT_FROZEN_REPLAY_REQUIRED` with scoring input identity `bbee004fefa7f0c07c32a14ad0e6c165d19544096e3bc9d34b1403db10200fef`.
- The completed bounded 1-of-96 replay exposed a final complete future-invariance failure after the phase-specific checks passed, and its runtime was operationally unacceptable. Those correctness/proof-boundary and replay-engine performance items are transferred to successor Issue #468 (`V2.37 — V3 replay correctness boundary, numerical-engine optimization, and multicore execution`).
- #468 must root-cause and close the complete future-invariance failure before freezing the semantic optimization baseline, then implement semantic-preserving replay optimization. The failed replay is evidence, not a trusted golden master.
- Until #468 closes that boundary, no complete V3 replay is considered operationally trustworthy, and #465 must not progress to Block 2 or protected 2023+ confirmation.
- Remaining landing work here is exact-source KIS verification/review, PR publication/merge of this bounded implementation baseline, and Work reconciliation. Replay-dependent scientific closure remains outstanding through #468.
