# #155 — Effective-N and detectable-effect budget

**Assessment date:** 2026-08-22

## Decision

The current 204-row governed OOS window is large enough to rule out only fairly large improvements under the existing dependence and multiplicity controls. It is not large enough to support broad claims that small forecasting edges do not exist.

For planning, the frozen 20-session block length implies about **10.2 block-equivalent information units** (`204 / 20`). This is not a mathematically exact effective sample size; it is a deliberately conservative information-budget proxy tied to the project's actual inference design. A block-length sensitivity of 10/20/40 sessions gives a planning envelope of **20.4 / 10.2 / 5.1** block-equivalent units.

The consequence is straightforward: change the target/representation only when there is an economic reason to expect a materially larger effect, or increase the amount of comparable PIT-safe history before consuming fresh confirmation evidence. Longer horizons do not manufacture more independent information from the same calendar span.

## Existing promotion gate

The current V1/V2 evaluator uses paired moving-block bootstrap RMSE improvement with block size 20, 1,000 resamples, 95% confidence, and Benjamini-Hochberg (BH) control. Promotion requires `ci_lower > 0`, BH-adjusted primary `p <= 0.05`, and the frozen period/regime robustness requirements. The non-overlapping 20-row sign-flip test is secondary only; on 204 rows it has 10 complete blocks.

Direction accuracy and correlation remain diagnostics for the current return target. They cannot rescue a failed primary RMSE gate.

## Power-planning conventions

The calculations below use 80% target power and a two-sided planning test. They are design approximations, not a replacement for the frozen bootstrap evaluator.

For a standardized paired effect, `MDE ≈ (z_(1-alpha/2) + z_0.80) / sqrt(N_block_eq)`, where `N_block_eq` is the declared block-equivalent planning proxy. This is a heuristic design screen, not an IID power calculation. For BH families, `alpha = 0.05 / m` is used only as a conservative **one-isolated-signal planning bound**; BH itself is data-adaptive and is not literally Bonferroni.

## Current-window MDE

Using the governed 20-session block-equivalent count (`N_eff = 10.2`), the standardized 80%-power MDE is approximately **0.88 SD** for one primary test, **1.13 SD** under the conservative nine-member planning bound, and **1.21 SD** under a 21-member bound. Corresponding Fisher-z correlation planning thresholds are roughly **0.78 / 0.87 / 0.89**. Those values are intentionally severe: they show why 204 daily observations cannot exclude realistic weak information coefficients once 20-session dependence is respected.

Block-length sensitivity is equally important:

| Assumed dependence block | Block-equivalent units | Standardized MDE: 1 test | 9-member bound | 21-member bound |
| --- | ---: | ---: | ---: | ---: |
| 10 sessions | 20.4 | 0.62 SD | 0.80 SD | 0.86 SD |
| **20 sessions** | **10.2** | **0.88 SD** | **1.13 SD** | **1.21 SD** |
| 40 sessions | 5.1 | 1.24 SD | 1.60 SD | 1.72 SD |

A direction-accuracy normal approximation gives about **93.9%** accuracy for 80% power with one primary test at `N_eff=10.2`; the nine- and 21-member conservative bounds exceed the mathematically possible 100% ceiling. Direction accuracy is diagnostic only, but this illustrates the information deficit. The correlation and direction calculations are heuristic screens at such a small block-equivalent count, not inferential substitutes for the repository evaluator.

For the primary RMSE gate, an empirical scale anchor is available without rerunning a model. Phase-D HistGB's frozen 95% bootstrap interval for RMSE improvement was `[-0.00196275, -0.00048633]`, implying an approximate standard error of `0.00037665`. Using that observed uncertainty as a planning anchor, the current 204-row window has an 80%-power RMSE-improvement MDE of:

| Planning family | Absolute RMSE improvement | Relative to zero-return RMSE `0.0453231` |
| --- | ---: | ---: |
| one primary | `0.001055` | **2.33%** |
| nine-member conservative BH bound | `0.001361` | **3.00%** |
| 21-member conservative BH bound | `0.001461` | **3.22%** |

This RMSE anchor is challenger-dependent because paired-loss variance changes with the forecast. It is useful as an order-of-magnitude budget, not as a universal gate value.

## Rows needed for smaller RMSE effects

Assuming the same dependence structure and approximately `1/sqrt(n)` uncertainty scaling, the HistGB-derived anchor implies:

| Relative RMSE improvement worth detecting | one primary | 9-member bound | 21-member bound |
| --- | ---: | ---: | ---: |
| 0.5% | 4,424 rows | 7,363 rows | 8,483 rows |
| 1.0% | 1,106 rows | 1,841 rows | 2,121 rows |
| 2.0% | 277 rows | 461 rows | 531 rows |
| 5.0% | 45 rows | 74 rows | 85 rows |

These counts are planning targets, not permission to reuse consumed outcomes. A redesigned adaptive hypothesis still needs untouched confirmation under #137.

## Target and horizon sensitivity

Changing horizon changes the question and may improve signal alignment, but it does not create new independent calendar information. If 20 daily sessions remain the dependence scale, non-overlapping 2-session returns give about 102 observations with a 10-observation block scale, and non-overlapping 5-session/weekly returns about 41 observations with a four-observation block scale. Both are still about 10.2 block-equivalent units over the same 204-session span.

| Candidate design | Information-budget view | #155 disposition |
| --- | --- | --- |
| next-session signed return | 204 rows; central 10.2 block-equivalents | **low-power for small edges; do not revive direct H1 by model search** |
| 2–5 session return | fewer non-overlapping targets; similar block-equivalent budget over the same span | **test only if mechanism suggests stronger signal-to-noise** |
| weekly return | about 41 non-overlapping weeks in the current span; still about 10 block-equivalents under a four-week dependence scale | **new hypothesis, not an H1 sensitivity rescue** |
| daily realized volatility / QLIKE | daily event count is similar, but volatility persistence may require a block length at least as long as 20 sessions | **promising only with target-native loss and a re-estimated dependence budget** |
| weather forecast revision | four GFS cycles per day do not create four independent daily-settlement outcomes | **potentially valuable because PIT GFS history extends much deeper; intraday-cycle tests are a separate design** |
| EIA storage surprise | weekly release events, not daily rows, are the natural information units | **potentially much better powered if a PIT consensus source passes its acquisition gate** |

The redesign therefore needs both **effect amplification** and **sample-budget discipline**. Aggregation alone is not a power strategy.

## Event-conditioned designs

Event studies should budget **events**, not daily rows. As planning scenarios, five years of weekly releases is about 260 events and about 65 four-week block-equivalents; ten years is about 520 events and about 130 four-week block-equivalents before holidays, missing observations, or exclusions. At 130 block-equivalents, the standardized 80%-power MDE is roughly 0.25 SD for one primary test and roughly 0.32–0.34 SD under conservative nine/21-member planning bounds.

That is materially better than the current daily-return confirmation window, but only if the event source and target are genuinely PIT-safe. #113 already requires a fixed historical prerelease consensus source and says the slice must stop as data-infeasible if that source cannot be verified. #155 does not assume that gate has passed or select a storage horizon on consumed outcomes.

## Deeper-history implication

The Databento history question has changed since #149 was opened. The committed acquisition evidence records a completed provider batch for `NG.FUT` `GLBX.MDP3` from **2010-06-06 to 2026-08-13 (end exclusive)**, but the local snapshot is explicitly quarantined: definitions and daily OHLCV passed hash verification, while the statistics payload is incomplete after 2018. #149 therefore should not start by buying the same history again or assuming every schema is canonical. Its next decision is candidate-specific **integrity repair/conditioning, canonical admission and PIT alignment** of the existing acquisition.

There are about 4,223 weekdays across that raw market span, used here only as an upper planning proxy for trading sessions. At a 20-session dependence scale that is about 211 block-equivalent units, roughly 20.7 times the current 10.2. Under unchanged paired-loss variance, the standard error would scale to about 22% of the current value.

Applying that scaling only as a planning illustration, the current HistGB-derived RMSE MDE would fall from about **2.33% / 3.00% / 3.22%** relative improvement to about **0.51% / 0.66% / 0.71%** for one/nine/21-member planning scenarios. Exact usable counts will be lower after exchange calendars, training requirements, contract semantics, missing rows and target-specific exclusions.

This does **not** mean the full V1 dataset can simply be extended to 2010. Market history is only one leg. Every exogenous feature must independently satisfy PIT history, representation and source-identity requirements. NOAA GFS makes a longer weather-revision study plausible; #113 must independently establish the usable PIT storage-consensus window; other families may bind later.

**Recommendation to #149:** do not reacquire Databento market history as the starting move. First verify/condition the quarantined acquisition, then determine for each preregistered candidate from #147/#148 how much of the existing 2010–2026 market history can be admitted canonically alongside its required PIT inputs. #149 remains the owner of the bounded acquire/defer/reject decision; any additional paid acquisition still requires its normal approval path.

## Mandatory budget for future preregistration

Before a new candidate consumes fresh confirmation evidence, its contract should state: calendar/scored rows; economically distinct information events; dependence/block rationale plus sensitivity; block-equivalent information count; primary target and target-native loss; prespecified multiplicity family; economically meaningful effect size; 80%-power MDE; approximate sample required for that effect; PIT coverage; realistic costs; and the untouched-confirmation path.

If the smallest economically worthwhile effect is below the design's MDE, the candidate should be **deferred, rejected, or supplied with more admissible history before confirmation**. Easier statistical detection is never sufficient reason to promote a target.

## Boundaries and interpretation

No new model was fitted, no new prediction was generated, and no unconsumed OOS result was inspected for #155. The numerical budget uses frozen evaluation settings, frozen historical closeout numbers, already-recorded acquisition metadata, and explicit planning approximations.

These calculations do not change the negative disposition of Phase D or #180. They narrow the claim: those experiments rule out large robust improvements for their frozen specifications; they do not prove that all small edges or better-aligned targets are absent.

Economic mechanism, strict PIT feasibility, zero-return or target-appropriate hard baselines, realistic costs, prespecified multiplicity, robustness across time/regimes, and untouched confirmation remain mandatory. Detectability is a gate on whether an experiment is worth consuming evidence on, not evidence that the hypothesis is true.

## Sources

- `config/phase_d_evaluation.json` — frozen V1 dependence and robustness settings.
- `docs/development/v2-activation-preregistration/statistical-evaluator.json` — paired bootstrap, BH and secondary sign-flip semantics.
- `docs/development/v1-research-completion/phase-d-closeout.json` — 204-row sample, RMSEs and frozen HistGB interval.
- `docs/development/v1-research-completion/phase-d-regression-diagnostics.json` — sample-history comparison and prediction/target dispersion.
- `docs/development/v2-model-criticism/review.md` — #89 research disposition and next-stage ranking.
- `docs/development/weather-revision-readiness/decision-record.md` — GFS history and future weather-revision design constraints.
- `docs/development/databento-full-history-acquisition/evidence.json` — durable acquisition identity, integrity status and no-reacquisition gate for the 2010–2026 Databento batch.
- GitHub issue #113 — storage-surprise PIT-consensus source and stop-if-infeasible activation requirement.
