# Databento vs Massive Futures Evaluation Review

## Outcome

The slice is implementation-complete subject to pull-request landing. Databento is integrated as a removable canonical-futures **candidate** behind the existing provider boundary. Massive remains the configured canonical provider. No canonical backtest-evidence or LIVE-trading authority changed.

The live Databento account probe is not complete: the configured Work runtime blocks direct outbound API calls and no authenticated Databento connector is mounted. The existing `DATABENTO_API_KEY` was checked only for presence/shape; its value was never printed, copied into the worktree, committed, or placed in review evidence.

## Implemented

- Added `commodity.databento_futures_provider` using the documented Databento Historical HTTP API and the existing `requests` dependency.
- Uses `DATABENTO_API_KEY` through HTTP Basic authentication; the key is excluded from query/body/manifest/error text.
- Uses `GLBX.MDP3` parent symbology `NG.FUT` with `definition` and `statistics` schemas.
- Performs metadata-only schema/range/cost/record-count preflight before any time-series request.
- Enforces both a `$1.00` default request-cost cap and a `50,000` default source-record cap.
- Normalizes final non-intraday CME settlement statistics to the existing canonical contract schema.
- Uses `ts_ref` as the trading reference date and conservative point-in-time availability: latest populated statistic availability, preferring `ts_recv` over `ts_event`.
- Captures a three-day statistics grace window so Friday cleared-volume publications on Sunday are not missed; canonical rows are filtered back to requested `ts_ref` dates.
- Excludes Databento numeric null/sentinel/negative cleared-volume values.
- Requires explicit provider `asset` and `exchange` identity and outright `instrument_class=F`; no exchange fallback is invented.
- Bounded archives preserve parsed provider source artifacts (`definitions.csv`, `statistics.csv`), canonical rows, and metadata preflight under the existing ignored snapshot contract.
- Added only candidate configuration/documentation; `sources.market_canonical.provider` remains `massive_futures`.

## TDD and regression evidence

Observed RED -> GREEN cycles covered:

1. Missing Databento module/provider surface.
2. Basic-auth request shape and credential redaction.
3. Metadata-only preflight.
4. Final settlement selection and cleared-volume join.
5. `ts_recv` availability preference.
6. Parent symbology output contract (`instrument_id` plus `map_symbols=true`).
7. Nested Databento JSON `hd` header flattening.
8. Cost-cap refusal before billable fetch.
9. Source-artifact preservation in archive capture.
10. Friday/Sunday statistics capture grace.
11. Conservative availability when volume publishes after settlement.
12. Required asset/exchange identity.
13. Record-count cap for flat-rate/zero-cost large requests.
14. Rejection of intraday settlement as canonical daily settlement.
15. Databento `INT64_MAX` cleared-volume sentinel exclusion.

Latest targeted Databento result: **15 passed**.

Latest full repository result: **137 passed**.

## Code review

The configured independent review backends were attempted first but failed before producing findings:

- Codex CLI reviewer: `UnicodeEncodeError` in the review runtime.
- NVIDIA NIM reviewer: backend execution error.

Those failures were not treated as review approval. A read-only evidence-first review was then performed against `AGENTS.md`, the slice specification/plan, the working-tree change, existing canonical-provider contracts, Massive snapshot precedent, and current official Databento HTTP/schema documentation.

Concrete findings discovered and fixed during that review:

- **P1 — prevent point-in-time volume leakage:** canonical `available_at` previously reflected settlement availability even when joined cleared volume arrived later. It now advances to the latest populated statistic availability.
- **P1 — preserve weekend-published roll evidence:** a one-day statistics grace could miss Sunday publication for Friday cleared volume. The statistics request/preflight now uses a three-day grace and filters output by `ts_ref`.
- **P2 — bound flat-rate downloads by records as well as dollars:** a zero-cost/flat-rate request could bypass the dollar cap. Metadata record counts now have a configurable hard cap before time-series retrieval.
- **P2 — preserve provider source evidence:** archive capture previously stored only canonicalized rows. It now preserves parsed definition/statistics source artifacts with manifest hashes.
- **P2 — reject non-daily and ambiguous provider data:** intraday settlement flags, missing asset/exchange identity, and invalid cleared-volume sentinels now fail closed or remain unavailable rather than being promoted into canonical fields.

No blocking code-review finding remains after these fixes.

## Modularity review

Qualitative modularity review: **pass; no decomposition proposal**.

- The Databento dependency is isolated in one provider-specific module, comparable in scope to the existing Massive provider.
- `commodity.cli`, `commodity.market_data`, and the provider-neutral protocol are unchanged.
- Dynamic provider loading means no central provider registry/case statement was added.
- The module depends only on existing bounded seams: config, canonical validation, credential error type, snapshot writer, pandas, and requests.
- Removal remains local: delete the Databento provider/tests/candidate config/docs without modifying provider-neutral market-domain or CLI code.
- Historical churn metrics for the new provider are unavailable by definition; no formal MAS score is claimed.

## Public capability vs account evidence

Public Databento documentation supports deeper CME `GLBX.MDP3` coverage and official settlement, cleared-volume, open-interest, definition, and OHLCV schemas. That is **screening evidence**, not proof of this account's entitlement, exact history, exact cost, or project-use rights.

Account-specific items still unverified:

- `GLBX.MDP3` entitlement on this account.
- Per-schema entitled start/end dates.
- Live `NG.FUT` parent-symbol resolution.
- Exact definition/statistics request cost and record counts.
- Tiny live NG payload normalization against the account.
- Project-specific contractual/non-display/backtesting rights.

## Verification

Latest pre-commit evidence:

- `python -m pytest -q` -> **137 passed**.
- `python -m ruff check .` -> **passed**.
- `git diff --check` -> **passed**.
- JSON parse: `config/assumptions.json`, `config/data_sources.json`, and `evidence.json` -> **passed**.
- Changed/untracked credential-pattern scan -> **12 files scanned, 0 hits**.

## Decision

Continue bounded Databento evaluation, but **do not switch providers yet**. Databento is the stronger technical candidate on documented source semantics/history depth, while Massive remains operationally proven on the configured account and already has a preserved M1-M12 snapshot.

The next external gate is deterministic: execute the metadata-only Databento account probe through an approved authenticated route, then allow only a record- and cost-bounded tiny NG sample if the preflight succeeds. Provider selection remains a separate explicit decision after that evidence exists.
