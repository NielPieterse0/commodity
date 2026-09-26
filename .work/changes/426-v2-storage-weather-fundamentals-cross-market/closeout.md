# Closeout: V2 Storage Weather Fundamentals Cross Market

## Current result

#426 scientific execution is complete and remains Active only for delivery/review closeout. The initial snapshot-only HOLD conclusion is superseded by newly acquired, integrity-bound pre-2023 evidence:

- storage: EIA WNGSR original first-published weekly history from 2015-06-19 through 2022-12-30 is scorable;
- positioning: CFTC Henry Hub disaggregated futures-only history from 2010-01-05 through 2022-12-27 is scorable;
- issued weather: NCAR/GDEX GFS 0.25 00 UTC history is complete for all 2,908 expected issue dates and passes the strengthened integrity/PIT gate;
- power: PJM historical load forecasts remain `HOLD` because public publication-lag semantics are not yet defensibly promoted.

Authoritative development scoring is complete: 667 trials were retained in the durable ledger. Storage and positioning retain matched marginal value; standalone weather is held; the preregistered storage × weather × season × volatility interaction retains matched marginal value. No protected confirmation, true-forward, prospective paper, Saxo SIM, or LIVE evidence was opened.

## Evidence

- `issue426-search-plan-v1.json` preregisters the source gate, matched control, interactions and stopping rules.
- `issue426-source-plan-v2.json`, `issue426-weather-feature-contract-v1.json` and `issue426-interaction-contract-v1.json` bind the promoted historical sources and pre-score feature/interaction semantics.
- `issue426-result-v1.json` and `issue426-trials-v1.jsonl` are the final durable authoritative development result and 667-trial ledger.
- Focused verification passed 39/39 with Ruff clean; fresh canonical verification after the `AGENTS.md` governance addition passed 807 tests with 7 skipped, all repository checks passed, git-whitespace passed, exit code 0.
- Independent test-quality review completed with full evidence and no material findings. Source code-quality review followed KIS-declared `manual_fallback: exact-diff`; the exact 152,207-byte staged source diff is SHA-256 `7ac3796f35a764d95c14e03086cd2ceb9473197e673db85cc754b29200391252`, with no blocking findings. Durable receipt: `evidence/code-quality-review.json`.
- `AGENTS.md` now codifies the isolated-worktree staged/range KIS review pattern and exact-diff fallback so this review failure mode is not repeated.

## Claim boundary

This is a development-only source-availability result, not a confirmed edge claim. Reserved confirmation, true-forward, prospective paper, Saxo SIM and LIVE evidence were not accessed.

## Revisit

Reopen the held families only when admissible pre-2023 PIT evidence or independently verified historical issue/release timing is added under a new immutable input identity.
