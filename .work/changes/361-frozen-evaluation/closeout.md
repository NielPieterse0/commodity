# Closeout: Frozen Evaluation

## Authority and boundary

- Parent programme: #353; phase issue: #361; Work item: WORK-361.
- Frozen candidate: `s-veto__l-none__p-half__u-none`, unchanged from the accepted Phase-5 selection after Phase 6 rejected annual refitting.
- Protected 2023+ outcomes remain unopened and are not treated as pristine confirmation for the foundation-model-dependent candidate.
- Prospective evidence may start only after the exact freeze change lands on the registered default branch. That boundary is now fixed at PR #372 merge commit `74fe9eb182ab9f82bad0b5aa4bb99ade22f19886`, merged `2026-09-12T04:30:20Z`; only decisions strictly after that timestamp are eligible.

## Implementation evidence

- Phase-7 freeze contract, identity audit, historical-development replay, and prospective-record validator are implemented in the declared governed scope.
- Final independent KIS code-quality review fingerprint: `4932ba839122311c8fb0fec5ee1703f60dfc5f643f548b241415eac15a8780ad`; no findings or unknowns.
- Fresh canonical `scripts/verify.ps1` passed: `625 passed, 7 skipped`; documentation/rule/environment/source/data/work-layout/hygiene/experiment/programme/research checks, lint, and git-whitespace all passed.
- Focused Phase-7 tests and lint also passed after the final timestamp-parser lint-only repair.

## Environment recovery evidence

- The original worktree-local UV Python 3.12 runtime was blocked by Windows Application Control while importing `_multiprocessing`; this was classified as a runtime defect, not a scientific failure.
- The `.venv` was rebuilt from the repository-approved KIS-managed Python 3.13.7 runtime within the permitted Projects execution domain, and required development/Databento runtime packages were restored.
- The blocked prior environment was moved recoverably to the repository-local ignored `.work/quarantine/361-frozen-evaluation/` area; no scientific contract, data boundary, target, candidate, or execution assumption changed.
## Lifecycle state

- WORK-361 handoff was frozen with `change_id=null`; supported binding failed because the KIS binder incorrectly requires a `src/kis_mcp` directory even for a registered Commodity checkout.
- The defect was routed through the supported `exit_once_through` recovery into `manual_closeout`; required change-governance, exact-PR, exact-head-CI and merge-readiness gates remained in force.
- No raw Git/GitHub bypass was used. Publication, remediation and merge used registered KIS GitHub operations.
- Phase 7 remains open for prospective evidence accumulation; the next scientific action is to generate and append eligible post-freeze paper-trading records without tuning.

## Provider and landing evidence

- PR #372 frozen head after publication-hygiene remediation: `616a47119398ee6a61110f43cad31fe943355086`.
- Provider-native GitHub Actions passed on that exact head after the only CI failure (machine-local paths in closeout text) was repaired; local canonical verification also passed `625 passed, 7 skipped`.
- Merge / landed revision: `74fe9eb182ab9f82bad0b5aa4bb99ade22f19886`.
- Exact freeze landing timestamp: `2026-09-12T04:30:20Z`.
- Prospective logging is bound to the landed freeze and uses an append-only JSONL hash chain that rejects pre-freeze decisions, contract-identity drift and tampered prior rows.
- A post-landing implementation audit found that the first logger revision only appended complete records after outcomes existed, which did not prove the forecast/action was recorded prospectively. This was treated as an implementation defect, not a scientific redesign.
- The logger now persists a separate decision event before outcome availability and only permits later settlement against that exact pre-existing decision hash. No protected or post-freeze outcome was opened to make this repair.

## Current operational closeout

- The prospective serving-contract amendment landed in PR #381 as `969c2ec957e249d8b405a4b73d851e6321c5639b`.
- The exact prewarmed TimesFM/Kronos serving proof then landed in PR #383 as `15a2e93d39e1ceb663fe998c5ffa562632ef96fc`; exact-head CI passed and measured prewarmed end-to-end decision latency remains 19.56265 seconds inside the frozen 60-second budget.
- Phase 7 is now explicitly paper-only. Saxo SIM and Saxo LIVE order submission remain prohibited and require a future explicit operator promotion decision; generic repository simulation does not authorize broker submission.
- The operational `run-day` path performs any due prior-session accounting, automatic five-session settlement, canonical source freshness, exact-source specialist prewarm, the next frozen decision, and status reporting. Stale canonical source records an append-only origin miss against the exact latest available source snapshot and never backfills the missed cadence slot.
- The simple market-only/no-modifier comparator is frozen to the persisted pre-specialist `baseline_position`, and v1 remains a permanent append-only paper control when later challengers are introduced.
- The operator approved a one-time `$0.30` Databento catch-up cap. The exact 2026-08-13 through 2026-09-11 definition/statistics/OHLCV partition triple was acquired for `$0.23765609040857` actual billed cost, all provider-manifest hashes verified, and the Phase-7 verifier accepted aligned source snapshot `54db4357e87d11ebf59510e6149a7dab8a6357d90bff8c7fe6343382ad7edfd0` with latest trade date 2026-09-11.
- The new source decoded and prewarmed successfully into 2,950 canonical rows and 760 OHLCV rows. This one-time approval does not change the standing automatic Databento spend authority from `$0.00`.
- Prospective activation at `2026-09-13T13:27:47.972406+00:00` landed in PR #385 as `febaa4ab9b549211a42887eb8839764a3c839a5b`; historical decision backfill remains prohibited from that boundary onward.
- The pre-first-observation hardening now derives the frozen selected contract and all 12 Phase-2 market features internally rather than trusting caller-supplied `current_origin`. Specialist serving history is stitched over the exact 807-calendar-day lookback and bound to 12 source files across four aligned partitions; the real stitched snapshot is `92f584182ece08e96e85ad6b253188439e021bb676b92ec98b62ea466eb64c34`.
- The real prewarm cache is hash-bound to that stitched snapshot with 100,964 canonical rows and 24,499 OHLCV rows and is now reused after hash/row-count validation instead of redundantly decoding the same source on every daily run.
- Real pre-first-observation validation found that the 2026-09-11 statistics partition contains preliminary settlement records but no frozen final-settlement records, while OHLCV is present. Therefore 2026-09-11 cannot legitimately reconstruct a Phase-2 market origin. The daily path now fails closed by consuming the prospective cadence slot as `prospective_market_origin_unavailable` instead of crashing, falling back to 2026-09-10, or fabricating a decision.
- No additional Databento acquisition was performed for this finding: the currently accessible statistics quote contained exactly the 14,474 records already retained locally, so buying it again would add no data. Saxo SIM/LIVE submission remains prohibited.
- The pre-first-observation hardening landed through PR #386 as merge `04874a7b15635b392a76dc98172e7f7cd562609a`; exact-head CI passed before merge.
- The first untouched post-activation cadence slot was then executed for the 2026-09-14 planned fill. Origin index 0 was recorded at `2026-09-13T16:36:31.163116+00:00` as `prospective_market_origin_unavailable`, bound to stitched source snapshot `92f584182ece08e96e85ad6b253188439e021bb676b92ec98b62ea466eb64c34`. No decision, position, cost or P&L was fabricated; the cadence counter advanced and live trading remained prohibited.
- That first hash-chained prospective ledger record (`b27ced0681380dd0eea2bf9b4f2d3f9669e980de4429c7bb440253ca3cc9b355`) landed through PR #387 as merge `5cb95dd83e53e2c959f10d5b235d2adffc788681` after local canonical verification and exact-head GitHub CI both passed.
- A post-landing timing audit shows this is a recurring source-access feasibility issue rather than only a malformed Sep-11 partition. On 2026-09-10, frozen final-settlement statistics arrived between `23:36:44.945572221+00:00` and `23:40:08.801255505+00:00`, leaving only about twenty minutes before the frozen 00:00Z next-session fill. The current no-subscription Databento account exposed recent historical data hours behind real time, so usage-based historical access cannot reliably supply those final settlements before the fill.
- Official Databento pricing checked on 2026-09-13 lists CME Globex MDP 3.0 Standard at `$199/month`, including live data and L0 OHLCV, definitions and statistics. The operator declined that subscription for now. Reconsider recurring data spend of roughly `$200/month` only after the system demonstrates about `$600/month` of trading profit, providing approximately 3x monthly profit coverage. Until that gate is met, v1 remains fail-closed when exact Databento inputs are unavailable; replacing Databento with Saxo or another source would require a separately versioned challenger rather than a silent v1 substitution.
- PR #389 recorded the live-source feasibility boundary and merged as `c09d8e5d62da5621a1f4097932eeaec34d5aef74` after exact-head CI passed.
- With that merge and the operator cost decision recorded, v1 implementation/development closeout is complete and the benchmark is frozen. Its prospective evidence ledger may continue accumulating untouched observations, but that ongoing observation does not authorize tuning v1 and does not block starting v2 as a separately versioned challenger.

## Qualified historical benchmark authorization

- On 2026-09-13 the operator authorized one final frozen-v1 historical benchmark before v2 begins: consume the reserved 2023+ block exactly once, without tuning or reselection, and preserve the result as the immutable v2 comparison baseline.
- The benchmark is preregistered in `phase7-v1-qualified-historical-benchmark-prereg-v1.json` before any reserved-window P&L is scored. It uses the final frozen v1 candidate, one pre-2023 market-model fit, exact pinned TimesFM/Kronos identities, the frozen 8/109 Kronos-path cadence, continuous paper-risk state, frozen costs and exact Databento source semantics.
- Because TimesFM/Kronos checkpoint pretraining exposure cannot be excluded, this result must be labelled `foundation_model_qualified_historical_evidence`, not pristine confirmation. It remains separate from the stronger true-forward Phase-7 prospective evidence contract.
- The preregistered benchmark was then executed exactly once over 805 eligible origins with the frozen v1 unchanged. Exact specialist coverage completed at 805/805 TimesFM one-step origins, 805/805 Kronos one-step origins and 60/60 preregistered Kronos five-step path origins.
- Frozen v1 produced net P&L of `-$2,520` after frozen costs, ending equity `$97,480`, maximum peak drawdown `2.52%`, and annualized simple return about `-0.6823%`. The frozen daily-loss limit triggered after the first active long session and the persistent risk state then shut down 995 later sessions.
- The frozen market-only/no-modifier comparator produced the same `-$2,520` economics and the same daily-loss kill. This does not prove specialist irrelevance generally; under the frozen v1 risk contract both paths were terminated before later specialist differences could express economically.
- The result is permanently classified `foundation_model_qualified_historical_evidence`, not pristine confirmation. It is the immutable v1 benchmark for v2 comparisons and must not be used to tune, rewrite or rerun v1.
- Durable result authority is `research/programmes/003-natural-gas-trading-decision-system/phase7-v1-qualified-historical-benchmark-result-v1.json`; exact hash-bound audit artifacts retain both 996-row ledgers, 805 TimesFM rows, 805 Kronos one-step rows and 60 Kronos path rows.
- The pre-result benchmark implementation passed canonical verification (`701 passed, 7 skipped`, all repository checks and git-whitespace passed) and one bounded independent code-quality review with no findings or unknowns; review source fingerprint `3d32600da8f44b3214aba8e4b60d0225a1700b1d2530db9937b35ccd4ee00b99`.
- After recording the completed benchmark evidence, fresh canonical verification again passed (`701 passed, 7 skipped`; generated documentation, rule registry, environment, durable-evidence references, market-source authority, data assurance, work layout, public hygiene, documentation authority, research-methodology checks, research metrics/memory, quantitative-research knowledge, lint and git-whitespace all passed). The final automated review surface could not invoke a backend because its bounded evidence projector omitted the large CSV artifacts; required exact-diff fallback found no scientific-contract or v1-model/configuration changes, and the retained result binds every audit artifact by repository-relative path, row count and SHA-256.
- The completed benchmark evidence landed through PR #421 at exact reviewed head `922ff85645beb550b17217307489ff565bcd7b80`; provider-native GitHub `verify` succeeded on that head, and the PR merged to `main` as `6a24f6c81e994b996b8033d5d253546376598691`. This landing closes v1 benchmark/development work; the separately frozen prospective Phase-7 observation remains open and untouched.

## Research return

- Phase-7 exit remains intentionally gated by the preregistered prospective contract: at least 365 elapsed days, 40 independent five-session episodes, 20 active exposures, including at least 5 long and 5 short, plus the frozen economic/risk gates.
- Phase 8 / #362 is not eligible unless that prospective gate succeeds; Phase 8 cannot be used to rescue failed or inconclusive evidence.
- The next valid action is to continue the frozen daily prospective paper loop without tuning or backfill. Each cadence slot must either produce a valid internally derived paper decision from fresh exact-source inputs or consume an origin miss; standing automatic Databento spend remains `$0.00`, and Saxo SIM/LIVE submission remains prohibited.