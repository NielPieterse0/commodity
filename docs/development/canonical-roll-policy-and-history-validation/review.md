# Canonical Roll Policy and History Validation Review

## Change Boundary

- Original branch base: `dc344c029a39c9ad6d364c248c41cf42e06f2491`.
- Reconciled PR base after parallel PR #2 landed: `18ab54261f9931f6517eccf57ba3c127542b4baa`.
- Branch: `feat/canonical-roll-policy-and-history-validation`.
- Worktree: `.work/worktrees/canonical-roll-policy-and-history-validation`.
- Scope: Massive account/history validation, authentication hardening, canonical roll methodology, derived continuous series/ledger, readiness gates, and evidence documentation.
- Excluded: serious model training, Databento, LIVE execution, and redistribution of Massive market values.

## Code Review

Closed findings:

- **CR-01 / P1 — Apply the expiry guard on the first observed session.** `src/commodity/rolls.py`: the initial implementation selected the front contract before applying the 3-calendar-DTE invariant. A one-session regression test proved a front contract at exactly 3 DTE was incorrectly selected. Fixed by applying the DTE guard during initialization and writing an auditable `forced_dte` ledger row. The roll suite then passed 12/12.
- **CR-02 / P1 — Keep API credentials out of request URLs.** `src/commodity/massive.py`: the inherited adapter placed `MASSIVE_API_KEY` in `apiKey` query parameters, allowing HTTP exception URLs to contain the secret. TDD changed authentication to `Authorization: Bearer`; a credentialed live request returned `status=OK` with header authentication.
- **CR-03 / P2 — Enforce the complete versioned roll contract.** `src/commodity/market_data.py`: readiness initially validated only the policy name and `2/3` numeric settings. Added a failing config-drift test and now require all registered `volume_crossover_dte_v1` semantics to match exactly.

Final local findings-first review: no additional P0-P3 correctness findings survived verification in the changed behavior.

## Parallel-Main Reconciliation

After PR #3 opened, remote `main` advanced from `dc344c0` to `18ab542` through parallel PR #2. The feature branch was rebased onto the new main in the same isolated worktree. One conflict occurred in `tests/test_pipeline.py`; resolution preserved both the newly landed assertion that rejects `--product-code GC` and this slice's layered canonical-readiness `doctor` test. Focused overlapping verification passed 63 tests before the rebase continued. No other files required manual conflict resolution.

## Live Account and Derived Evidence

- Massive authentication succeeded using the configured `MASSIVE_API_KEY`; no credential value is recorded here.
- Contract discovery returned `OK` and pagination was observed.
- Aggregate rows for `NGU4`, `NGV4`, `NGX4`, and `NGF5` share an observed earliest session of `2024-08-13`; `NGQ4` returned no aggregate rows.
- Available session fields include settlement, OHLC, volume, transactions, dollar volume, and session/window dates; historical per-contract open interest was not observed.
- Ignored canonical sample: 24 rows across `NGU4` and `NGV4`, 12 rows each, with no weekday gaps from 2024-08-13 through 2024-08-28. SHA-256: `2c2a3dc1d75ec41a638dcf3baf43a1c99c69a6135f604b6f3e71546e5a4a9025`.
- Ignored derived validation: 12 selected sessions, one `forced_dte` roll, two null returns (initialization + roll boundary). Continuous SHA-256: `1f36d8e4bc250d702a561a56b414c7e739505a2a703d3135bfa37b647e4efd6d`; ledger SHA-256: `e34b37abc7f5768f957b85de1738168c2e7bd01f0c6bd846846ca49403647cfe`.

## Licensing Decision

Massive source/history and the roll methodology are technically ready, but canonical backtest promotion remains fail-closed. The current individual Market Data Terms do not establish the non-display/backtesting right needed for this research use, so `non_display_backtesting_rights_verified=false` and `backtest_evidence_allowed=false` remain authoritative. No Massive market values are committed.

## Modularity Assessment

Mode A, 90-day horizon, explicit changed Python units. Collector:

`python C:\Projects\.agents\skills\modularity-assessment\scripts\seams.py --repo . --since "90 days ago" --granularity file --unit src/commodity/massive.py --unit src/commodity/rolls.py --unit src/commodity/market_data.py --unit src/commodity/cli.py --top 10 --format md`

Evidence strength: **LOW**. The collector measured LOC, commit/subject counts, Python fan-in/out, and co-change, but read-set/edit-set, test isolation, hidden coupling, and reviewed RFC-kind clusters remain unmeasured; therefore MAS is `n/a`.

- `commodity.massive` remains cohesive around Massive HTTP acquisition and normalization.
- `commodity.market_data` remains provider-neutral canonical validation/readiness; measured fan-in is 6, but no implementation reach-through was found in this slice.
- `commodity.rolls` is now 333 LOC but remains one domain purpose: contract-path selection, roll evidence, and within-contract returns. **DEFER** splitting until an additional independent policy family or execution responsibility appears, or representative change evidence shows read-set expansion.
- `commodity.cli` remains orchestration-only despite high fan-out; no provider-specific roll logic was added there.

No structural cut is justified with current evidence.

## Independent Reviewer Limitation

Two read-only reviewer-wrapper attempts failed before returning findings: Codex CLI with `AGENT_BACKEND_FAILED:UnicodeEncodeError`, then the fallback backend with `AGENT_BACKEND_FAILED:NvidiaNimError`. These failures are not treated as approvals. The installed local `code-review` contract and the base `develop-code` Review Contract were applied directly instead.

## Verification Evidence

TDD evidence retained during implementation:

- Massive auth RED: query parameter credential test failed against inherited behavior; GREEN: header-auth targeted suite passed 3/3 and a live header-auth request returned `OK`.
- Roll RED: eight new behaviors initially failed because the continuous-series API did not exist; GREEN: 11/11 passed. Review regression RED: initial-session 3-DTE test failed against first implementation; GREEN: roll suite passed 12/12.
- Readiness RED: structured evaluator was initially absent; GREEN: market-data suite passed. Config-semantic drift RED then GREEN after full v1 contract enforcement.
- Doctor RED then GREEN after assumptions-owner wiring.

Fresh final full-suite/lint/diff/hygiene results are recorded below after the exact final tree is verified.

## Final Verification

Post-reconciliation current-tree evidence:

- `PYTHONPATH=<worktree>\src python -m pytest -q` -> **78 passed** after rebasing onto PR #2's landed changes.
- `PYTHONPATH=<worktree>\src python -m ruff check .` -> **All checks passed**.
- `git diff origin/main...HEAD --check` -> exit 0 after removing one trailing blank line in `plan.md`.
- `PYTHONPATH=<worktree>\src python -m commodity.cli doctor` -> source/history ready `true`, roll method ready `true`, licensing ready `false`, canonical evidence allowed `false`; LIVE trading and model order submission remain `false`.
- `git status --short --ignored` confirms all four Massive validation files under `data/raw` / `data/interim` are ignored; only `.gitkeep` is tracked in those directories.
- Exact-value secret scan across `git ls-files --cached --others --exclude-standard` -> `secret_present_in_committable_files=false`, hit count 0.

These checks are rerun after this reconciliation note before the final PR head is published.

## Pull Request and Landing

- Initial verified implementation commit: `ad80f2201ce8b1f48026facde1849be6608d5d79`.
- Final approved PR head: `09e173a82766e38b00fe5fb6f1b33eb695dd13a6`.
- GitHub PR: **#3**, merged on 2026-08-12 through the registered exact-head landing gate using the `merge` method.
- GitHub merge commit: `0f0c710c43cec046be1e70a131c46d42df2a2607`.
- Pre-landing verification on the approved head: 78 pytest tests passed, Ruff passed, and `git diff origin/main...HEAD --check` passed.
- The residual canonical-evidence blocker remains Massive non-display/backtesting licensing; landing did not change that gate or LIVE-trading policy.
