# #147 — Target and horizon portfolio

**Assessment date:** 2026-08-23

## Decision

Do not revive generic next-session signed-return forecasting by changing model size or by sweeping horizons. The next empirical work should be mechanism-led and should use a target-native loss, a declared information budget, and untouched confirmation.

The ranked portfolio is:

1. **Next-session realized volatility / variance — TEST next after preregistration.**
2. **Event-window return tied to a named surprise/revision — TEST conditionally after the source/event gate passes.**
3. **Economically natural curve/spread change — DEFER, but keep as the strongest market-only alternative.**
4. **Generic 2–5 session return — DEFER unless a mechanism fixes the horizon in advance.**
5. **Settlement direction — RETAIN AS SECONDARY ONLY, not a new primary programme.**
6. **Generic weekly return — REJECT as a power-only redesign.**

No model was fitted, no prediction was generated, and no fresh OOS outcome was inspected for this ranking.

## Why the ranking changed

Phase D and corrected Kronos show that the exact next-session signed-return problem has weak usable information at the tested grain. HistGB was worse than zero return with slightly negative prediction/actual correlation, and corrected Kronos Mini/Small/Base were materially worse again. That argues against another unrestricted model search.

#155 shows the current 204-row OOS window has only about 10.2 twenty-session block-equivalent information units. Aggregating those same dates into 2–5 session or weekly targets does not create additional independent calendar information. A new horizon is justified only if the mechanism plausibly increases effect size.

Working #149 evidence further shows that deeper market history can materially improve precision once licensing/canonical gates are cleared, but market depth is only a ceiling: every candidate still needs matching PIT-safe inputs and an untouched confirmation path.
## Candidate 1 — realized volatility / variance

**Disposition: TEST after a dedicated preregistration; highest priority.**

Economic case: volatility is persistent, directly linked to storage/weather/supply uncertainty, and does not require predicting the sign of a near-efficient daily price move. The earlier V1 volatility coverage was only a shared trailing-history diagnostic, so it did not test a trained volatility challenger. Separate provider-boundary screening also found a very small, statistically uncertain absolute-return improvement from richer curve information; that is motivation only, not confirmation.

Preregistration requirements:
- freeze one positive realized-variance target before inspection; prefer a same-contract OHLC-based estimator if its source semantics are admitted, with squared/absolute settlement return only as a separately declared sensitivity;
- use **QLIKE** as the primary loss for a variance forecast, with RMSE/MAE only as secondary diagnostics if justified;
- compare against a simple frozen trailing-variance baseline; do not build a baseline zoo after seeing results;
- re-estimate the dependence/block scale for volatility rather than inheriting 20 sessions automatically, because volatility clustering may require a longer block;
- state the smallest economically useful QLIKE improvement and its 80% power/MDE budget before activation;
- require period/regime robustness and #137 untouched confirmation.

Data path: market-only versions could eventually use the preserved 2010–2026 market history, but current Databento canonical/project-use authority remains blocked. Exogenous variants may be shorter because PIT weather/storage history can become the binding window.

## Candidate 2 — event-window return after a named information event

**Disposition: TEST conditionally; second priority.**

This is not a generic longer-horizon return. The horizon must be tied to an event whose timestamp and mechanism are known before outcomes are inspected. Two live routes already exist:
- **storage surprise:** #113 requires actual EIA storage change minus one fixed prerelease consensus source and must stop if that consensus cannot be proven PIT-safe;
- **weather revision:** #114/#148 support NOAA GFS vintage-over-vintage revision as a plausible issued-forecast news signal.

The exact event target remains for the child preregistration: report-day, next-session, or a short fixed post-event window must be selected from market microstructure/economic timing, not from which window scores best on consumed data. Event studies budget events, not daily rows; five to ten years of weekly storage releases would be roughly 260–520 events before exclusions and is materially better powered than the current 204-row daily-return window if the source gate passes.
## Candidate 3 — curve/spread change

**Disposition: DEFER; strongest market-only alternative.**

A curve target is economically natural for a storage commodity because inventory, seasonality, transport constraints and scarcity can move relative contract values even when outright next-day direction is hard to predict. It also avoids requiring deep exogenous history for a first market-only study.

Do not use a vague “curve target.” A future preregistration must freeze one exact object, such as a roll-safe M1–M2 spread change or a named seasonal-spread change, together with rank/expiry rules, a zero-change or other economically defensible baseline, loss, transaction-cost interpretation, and roll exclusions. The target must never manufacture cross-contract returns.

Why not activate now: current deeper Databento market data remain non-canonical pending the operator-deferred #51 rights/adoption decision, and the two-year Massive evidence is too short to make a broad confirmation claim. Keep this route ready, but do not spend confirmation evidence until the market-data authority and exact spread mechanism are fixed.

## Candidate 4 — generic 2–5 session return

**Disposition: DEFER unless mechanism-led.**

Two-to-five-session aggregation does not increase the effective information count over the same calendar span. It can still be useful if a preregistered mechanism genuinely unfolds over several sessions—for example, delayed response to a supply revision—but the mechanism must choose the horizon before result inspection.

A future candidate must name one horizon, not test 2/3/4/5 days and keep the winner. Overlapping returns require explicit dependence handling; non-overlapping returns reduce row count. Either way, #155’s information-budget discipline still applies.

## Candidate 5 — settlement direction

**Disposition: RETAIN AS SECONDARY ONLY.**

Direction is easier to communicate but not demonstrably easier to predict. Phase D probability forecasts did not improve Brier/log-loss over the naive direction baseline, and corrected Kronos Small was 50.0% accurate. With only about 10.2 block-equivalent units, direction-accuracy power is especially poor.

If carried beside a primary target, use a prespecified probability loss such as Brier score or log loss and a frozen naive/historical-rate comparator. Do not promote a model because accuracy exceeds 50% when its primary target-native loss fails.
## Candidate 6 — generic weekly return

**Disposition: REJECT as a standalone power redesign.**

Weekly aggregation is the clearest case where fewer rows do not mean more independent information. On the current calendar it gives roughly 41 non-overlapping weekly observations and still about ten block-equivalent units under a four-week dependence scale. It also blurs event timing that is central to storage and weather mechanisms.

A weekly cadence can still arise naturally from a weekly event source, but then the research object should be the event response, not an arbitrary Friday-to-Friday return target.

## Preregistration-ready ordering

| Rank | Candidate | Decision | Primary loss direction | Main gate before execution |
| --- | --- | --- | --- | --- |
| 1 | realized volatility / variance | **test** | QLIKE | freeze variance proxy, dependence/MDE, baseline and untouched confirmation |
| 2 | event-window return | **test conditional** | RMSE/MAE or event-native return loss fixed in child contract | PIT-safe event/news source and exact event horizon |
| 3 | curve/spread change | **defer** | fixed regression loss vs zero-change/economic baseline | canonical market-data rights plus exact roll-safe spread target |
| 4 | generic 2–5 session return | **defer** | RMSE against zero return where valid | mechanism selects one horizon before outcomes |
| 5 | settlement direction | **secondary only** | Brier/log loss | must accompany a primary target; no accuracy-only promotion |
| 6 | generic weekly return | **reject** | n/a | reconsider only if a specific weekly mechanism creates the target |

## Mandatory contract for any promoted child hypothesis

Before empirical execution, freeze: target formula; horizon/event clock; prediction cutoff; eligible inputs; PIT/source identity; training and scored calendar; economically distinct information-event count; dependence/block rationale and sensitivity; primary loss and baseline; smallest useful effect; 80% power/MDE; multiplicity family; robustness slices; realistic cost assumptions; and the #137 untouched-confirmation route.

For an adaptive target shaped by V1/V2 evidence, consumed 2024–2026 outcomes remain hypothesis-generation evidence only. A historical confirmation set is valid only if it was frozen untouched before its outcomes influenced design; otherwise use prospective walk-forward or another explicitly controlled sequential design.

## Routing

- Volatility target/loss preregistration should be created as the first child execution slice from #147.
- Event-window target definition should be coordinated with #148; storage remains gated by #113 and weather revision by #114.
- Curve/spread execution remains blocked by market-data authority while #51 is operator-deferred.
- #150 may add only small ex-ante event/regime interactions after a target and mechanism are fixed.

## Evidence used

- `docs/development/v2-model-criticism/review.md`
- `docs/development/effective-n-detectable-effect/analysis.md`
- `docs/development/v1-research-completion/phase-d-closeout.json`
- `docs/development/v1-research-completion/phase-d-regression-diagnostics.json`
- `docs/development/weather-revision-readiness/decision-record.md`
- #149 working deeper-history evidence from held PR #189
- GitHub issues #113, #137 and #148

This slice changes research design only. It does not alter any existing negative empirical disposition or authorize trading.