# #197 — Power-gated historical volatility confirmation preregistration

**Status:** frozen design; confirmation execution is not authorized by this slice
**Assessment date:** 2026-08-24
**Inherited model contract:** #191, exact contract SHA-256 `f89a381d...b29fe`

## Decision

Freeze a candidate path to confirm the fixed #191 next-session realized-variance hypothesis on **1,800 scored historical rows**, subject to two pre-scoring gates: nuisance-only power calibration and an independent lineage audit proving those scored rows did not influence the hypothesis or its thresholds.

The confirmation changes only the evidence window and its power budget. The #191 target, same-contract rules, 20-session baseline, fixed log-HAR OLS challenger, 252-row initial training window, five-row refit cadence, QLIKE loss, 40-session primary bootstrap block, 20/60-session sensitivities, robustness rules, 5% materiality threshold, and exclusions remain unchanged by exact contract inheritance.

The confirmation sample will be historical rather than the previously planned 504 future rows because #195 showed that 504 rows are underpowered. The existing 504-row future confirmation remains locked and is not combined with this design.

No confirmation outcome was loaded, scored, summarized, or inspected while creating #197.

## Power correction from #195

#195 correctly stopped before opening its 504-row confirmation, but its reported 59.2% relative MDE used incompatible statistical scales. The planner multiplied a block-equivalent standardized MDE by the row-level paired-QLIKE standard deviation.

#197 does not rewrite #195 historical evidence. It records the correction prospectively and preserves the original lock decision.

The corrected planning scale uses the variability of contiguous block means from the already-consumed 204-row paired QLIKE-improvement sequence. This matches the scale on which a mean is tested under moving-block dependence.
From #195 consumed evidence:

- mean baseline QLIKE = `0.2751895286`;
- 5% materiality = `0.0137594764` absolute QLIKE improvement;
- row-level paired-improvement SD = `0.2063868707`;
- overlapping 40-session block-mean SD = `0.0290534024`.

For 80% power and a two-sided 5% test, the primary 40-session calculation requires approximately **1,399.8 rows**. Rounding to full blocks gives 1,400 rows. #197 sets a governed floor of **1,440 rows (36 primary blocks)** and freezes the actual confirmation at **1,800 rows (45 primary blocks)**.

| Scored rows | 20-session MDE | 40-session primary MDE | 60-session MDE |
| --- | ---: | ---: | ---: |
| 504 | 7.90% | **8.33%** | 7.78% |
| 1,440 | 4.67% | **4.93%** | 4.60% |
| 1,800 | 4.18% | **4.41%** | 4.11% |

On the consumed #195 plug-in scale, 1,800 rows place the prespecified 5% effect above the estimated 80%-power MDE under every frozen block sensitivity. That is a **conditional planning pass**, not proof that the future historical segment is adequately powered: both the confirmation baseline QLIKE scale and dependence variance can differ. A frozen nuisance-only calibration segment must therefore re-estimate those quantities before any scored confirmation outcome is opened.

## Candidate historical sample

The proposed historical segment must be strictly earlier than the V1/V2 data boundary. Chronology alone is not enough to call it untouched: an independent source-bound lineage audit must also prove that the final scored rows and their performance summaries did not influence #191/#193/#195/#149 design choices.

Freeze the candidate pool to prediction times strictly before `2024-08-13T00:00:00+00:00`. Using the inherited #191 admissibility rules, select the **last 2,772 consecutive admissible prediction rows** before that boundary. The first 252 rows are initial training, the next 720 rows are nuisance-only power calibration, and the final 1,800 rows are the candidate scored confirmation.

Sample selection may use source identity, calendar, contract identity, PIT availability, row identity, and coverage. It must not use performance from the final 1,800 scored rows. If the exact 2,772-row window cannot be formed with 100% coverage, execution stops; rows may not be dropped, imputed, replaced across contracts, or shifted to a different window after performance is seen.

The existing 504 future rows strictly after the #191 diagnostic boundary remain a separate locked sample. They cannot be pooled with the historical holdout to reach a target count.

## Nuisance-only power calibration

The 720 calibration rows may be consumed before confirmation only to estimate nuisance quantities needed for power: mean baseline QLIKE and centered paired-loss block SD at 20, 40, and 60 sessions. They must not publish or expose mean challenger QLIKE, mean paired improvement, p-values, confidence intervals, period/regime performance, or secondary performance.

For each block size, the release gate uses the **larger** of the #195 consumed block SD and calibration block SD. For the relative-effect scale it uses the **smaller** of the #195 mean baseline QLIKE and calibration mean baseline QLIKE. Recompute the relative MDE for 1,800 rows from those conservative values.

All three 20/40/60-session MDEs must be at or below 5%. If any exceeds 5%, stop before opening the final 1,800 scored rows and create a new preregistration. The calibration result may change sample planning only through a future freeze; it may not change the target, model, features, lags, evaluator, or materiality threshold.

## Inherited forecasting contract

The exact #191 contract is inherited by SHA-256. #197 does not create a new model or target.

The target remains next-session Garman–Klass realized variance on the contract selected at prediction time. Cross-contract target substitution remains prohibited. The sole primary baseline remains the 20-session same-contract realized-variance mean. The sole challenger remains the fixed three-feature log-HAR OLS model with no tuning or feature selection.

Training remains expanding, with 252 initial rows and refitting every five scored rows. Only labels whose target bars are already available may enter a refit.

Primary loss remains QLIKE. The primary comparison remains paired `baseline_qlike - challenger_qlike`, where positive means the challenger is better.

## Inference and promotion gate

Inference remains the #191 moving-block bootstrap: 1,000 resamples, seed 0, 95% interval, primary block 40 sessions, sensitivities 20 and 60, and one primary hypothesis with `p <= 0.05`.

A confirmation passes only if all inherited #191 primary gates pass: positive mean QLIKE improvement, positive 95% CI lower bound, primary p-value at or below 0.05, at least 5% relative QLIKE reduction, positive improvement in at least two of three chronological thirds, and positive improvement in at least two of three frozen volatility regimes.

Secondary RMSE of square-root realized variance and the last-observation comparator remain descriptive only. They cannot rescue a failed primary result.

The 1,800-row sample size is a detectability gate, not evidence that the hypothesis is true. Confirmation performance remains unknown until a separately authorized execution opens the frozen outcomes.
## Data and rights gates

#149 established that the preserved Databento `GLBX.MDP3 NG.FUT` batch already has enough raw history. Its integrity is now complete through 2026-08-12, so #197 authorizes **no new paid market-data acquisition**.

Integrity does not equal promotion authority. `config/data_sources.json` still records the Databento source as noncanonical, disallows backtest evidence, and records project-use/licensing rights as unverified.

Confirmation execution therefore remains fail-closed until a separate authoritative decision makes all three conditions true for this exact use:

1. `canonical_market_source = true`;
2. `backtest_evidence_allowed = true`;
3. `licensing_rights_verified = true`.

#197 does not modify #51. Its operator-deferred state is outside this slice.

## Independent release audit

No confirmation run may start from #197 alone. A separate independent audit must bind the exact hashes of this preregistration, `contract.json`, and `power-analysis.json`.

Before execution, that audit/release must also bind the exact admitted market-source manifest and deterministic 2,772-row identity. It may inspect row identity and coverage but must not inspect performance from the final 1,800 scored rows.

The same audit must be source-bound to #191, #193, #195, #137, and #149 evidence and prove that neither the final scored rows nor summaries of their model performance influenced the target, model, features, lags, thresholds, regimes, sample rule, or materiality decision. If that lineage cannot be proved, the historical confirmation path is invalid and confirmation must remain prospective or be separately preregistered.

The audit must fail closed if the sample boundary, inherited #191 hash, target/model/loss settings, source authority, rights, nuisance-calibration rule, or power rule differs from this freeze.

## Stop rules

Stop before fitting if rights/canonical admission are incomplete, the exact historical window cannot be formed, the lineage audit cannot prove scored-row freshness, inherited #191 semantics changed, target rows cross contracts, or any final scored-confirmation performance was inspected before release. After the 720-row nuisance calibration, stop again unless every frozen 20/40/60-session relative MDE at 1,800 rows is at or below 5%.

Stop confirmation as failed if any inherited primary statistical, materiality, period, or regime gate fails. Do not extend the sample, add features, tune the model, change lags, combine the locked 504 rows, or substitute a secondary metric after seeing the result.
## Authority boundaries

This slice freezes research design only. It does not authorize confirmation execution, research promotion, paper trading, or live trading. `config/policy.json` remains the sole trading/execution authority.

No model fit, new prediction, confirmation score, confirmation summary, or paid acquisition is produced by #197. #137 remains the governing fresh-confirmation boundary.

## Evidence used

- `docs/development/volatility-preregistration/contract.json` — exact inherited #191 model/target/evaluator contract.
- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/predictions.csv` — consumed paired-loss sequence used only for power planning.
- `artifacts/volatility-diagnostic/volatility-195-gk-har-v1/summary.json` — consumed diagnostic and historical 504-row power-lock evidence.
- `docs/development/volatility-successor-preregistration/power-analysis.json` — corrected power calculation and sample decision.
- `docs/development/deep-history-target-feasibility/analysis.md` — #149 history, rights, and untouched-holdout constraints.
- `docs/development/databento-full-history-acquisition/repair-evidence.json` — repaired 19/19 acquisition integrity.
- `config/data_sources.json` — current canonical/backtest/licensing gates.
- `config/policy.json` — research and execution authority.
- GitHub issue #137 — fresh-confirmation rule.

The key scientific consequence is narrow: #195 produced a promising consumed-history volatility result, but it is not confirmatory. #197 freezes a **candidate** historical confirmation path that may proceed only after independent lineage proof and nuisance-only power calibration establish that the final 1,800 scored rows are both fresh enough for #137 and adequately powered under the frozen rule.
