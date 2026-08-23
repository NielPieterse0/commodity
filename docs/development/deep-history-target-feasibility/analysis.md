# #149 — Deeper-history and target/horizon feasibility decision

**Assessment date:** 2026-08-22

## Decision

Do **not** buy or reacquire more Databento Henry Hub history now. The preserved 2010-06-06 to 2026-08-12 `GLBX.MDP3` batch already contains the raw market depth needed for the next research stage, and its previously incomplete statistics payload was repaired and independently verified on 2026-08-14.

The remaining market-data blockers are not sample depth. They are project-use/licensing authority, canonical admission, and candidate-specific PIT alignment. Issue #51's review trigger is therefore met: deeper-history testing is now decision-relevant, so #51 should be released for the rights/adoption decision before Databento is used as canonical backtest evidence.

For target design, aggregation alone is rejected as a power strategy. Two-to-five-session and weekly returns do not create additional independent calendar information over the same span. They are worth testing only when a specific economic mechanism should produce a larger effect.

The two strongest deeper-history routes are still mechanism-led: NOAA GFS forecast revisions and EIA storage surprise. Weather has a plausible official issued-forecast archive back to 2006. Storage has attractive event-count power, but remains blocked until #113 verifies a fixed historical prerelease consensus source.

## Correction to the #155 starting state

#155 correctly treated the original 2026-08-13 acquisition evidence as quarantined because the statistics artifacts were incomplete after 2018. That was the state recorded in `evidence.json`, but it was not the final integrity state.

`repair-evidence.json`, dated 2026-08-14, verifies all 19 statistics artifacts against the provider manifest using member size plus SHA-256, with zero bad or missing artifacts and coverage complete through 2026-08-12. `config/data_sources.json` therefore correctly records `integrity_status: complete`.

Integrity repair does **not** make the batch canonical. The same repair record keeps `canonical_market_source: false`, `backtest_evidence_allowed: false`, and `licensing_rights_verified: false`. The raw files remain evaluation-only until those separate gates pass.

## What additional history buys

The planning calculation inherits #155's 204-row window, 20-session dependence assumption, and HistGB-derived paired-loss uncertainty anchor. For the 5/10/15-year comparison below, one additional year is approximated as 252 comparable trading sessions. These are planning upper bounds; actual usable rows will be lower after exchange calendars, training windows, contract rules, PIT overlap, missing data and target-specific exclusions.

| Added comparable history | Approx. total rows | 20-session block-equivalents | RMSE MDE: one primary | 9-member bound | 21-member bound |
| --- | ---: | ---: | ---: | ---: | ---: |
| current only | 204 | 10.2 | 2.33% | 3.00% | 3.22% |
| +5 years | 1,464 | 73.2 | 0.87% | 1.12% | 1.20% |
| +10 years | 2,724 | 136.2 | 0.64% | 0.82% | 0.88% |
| +15 years | 3,984 | 199.2 | 0.53% | 0.68% | 0.73% |
| full 4,223-weekday market-span proxy | 4,223 | 211.2 | 0.51% | 0.66% | 0.71% |

The standardized 80%-power MDE falls from 0.88 SD now to about 0.33 / 0.24 / 0.20 SD for one primary test after 5 / 10 / 15 additional years under the same planning assumptions.

This is a material improvement. Five additional comparable years move a 1% RMSE effect from clearly underpowered to approximately detectable for one isolated primary test, though not under the conservative nine- or 21-member bounds. Ten years bring a 1% effect inside all three illustrative bounds.

## What market depth does not solve

A longer CME history cannot extend a candidate past the oldest date on which all of that candidate's required inputs are PIT-safe and semantically stable. Market rows are therefore a ceiling, not the final sample count.

For a direct market-only target, the preserved batch can support much deeper design work once #51 and canonicalization pass. For exogenous candidates, the binding source may be elsewhere. NOAA GFS has a documented issued-forecast archive from 2006 onward, making weather revisions compatible with the full market-history window in principle. Storage surprise is different: the weekly EIA actual is not enough; a fixed historical analyst consensus with proven prerelease timing is mandatory, and #113 has not yet passed that gate.

The 16-year market span also crosses major structural regimes: shale growth, LNG export build-out, COVID, the 2022 global gas shock, and later market states. More history improves statistical precision but increases regime-transport risk. Any eventual experiment must preserve period/regime robustness rather than treating all older rows as exchangeable.

## Target/horizon decisions

| Candidate | Power/sample view | Decision from #149 | Reason |
| --- | --- | --- | --- |
| next-session signed return, more model search | deeper history helps precision | **Reject as a generic revival** | V1/V2 already rule out large robust edges for the tested specifications; more model search without a new mechanism is adaptive fishing |
| 2–5 session return | similar independent information over a fixed calendar span | **Defer unless mechanism-led** | aggregation alone does not increase effective information |
| weekly return | fewer targets, similar block-equivalent budget | **Reject as a power-only redesign** | it is a new hypothesis, not a rescue of daily H1 |
| realized volatility / QLIKE | potentially more forecastable target | **Advance design in #147, not execution** | needs target-native loss and a new dependence/MDE budget |
| NOAA GFS forecast revision | official issued history plausibly reaches 2006 | **Prioritize preregistration/data-feasibility work** | mechanism and depth can both improve the experiment; #114 already defines the source constraints |
| EIA storage surprise | 5–10 years gives roughly 260–520 weekly events | **Defer at source gate** | statistically attractive, but #113 must first verify a PIT-safe historical consensus source |
| curve/spread target | deep market-only history is locally available | **Defer to #147 mechanism ranking** | requires an economically natural target and untouched confirmation plan, not just availability |

## Explicit acquire / defer / reject decisions

1. **Databento raw Henry Hub history — REJECT additional acquisition now.** The existing batch already reaches the provider's 2010 catalog boundary used by this project. Rebuying the same depth adds cost without adding information.
2. **Databento canonical research use — DEFER pending #51.** #51 must verify the intended project-use/licensing rights and decide adoption. If approved, canonicalization should use the repaired local batch rather than a fresh paid download.
3. **NOAA GFS issued-forecast history — ADVANCE bounded acquisition/readiness after preregistration.** This is the strongest route where deeper PIT-safe exogenous history appears technically plausible without consuming target outcomes. It remains subject to #114's exact product, cycle, horizon and model-version rules.
4. **Historical storage consensus — DEFER to #113's source gate.** Do not purchase or ingest a consensus history until one source can prove fixed historical coverage and prerelease publication timing. If verified, the weekly event design has a materially better information budget than the current 204-row daily-return window.
5. **Longer/weekly return solely for sample power — REJECT.** Reconsider only as a separately motivated hypothesis with its own target-native economics and preregistration.
6. **Realized-volatility target — ADVANCE design, DEFER empirical execution.** #147 should estimate a target-specific dependence scale and loss before any confirmation budget is spent.

## Confirmation boundary

None of these planning decisions authorizes fitting a model, generating a prediction, or inspecting unconsumed OOS outcomes. Any candidate shaped by the consumed V1/V2 evidence remains adaptive and must use #137's untouched confirmation path.

Deeper historical data can be split into development and untouched confirmation only if the split is frozen before outcomes are inspected and the confirmation portion was not used to formulate the candidate. Otherwise confirmation must be prospective or use another explicitly controlled sequential design.

## Sources

- `docs/development/effective-n-detectable-effect/analysis.md` and `power-budget.json` — #155 power budget.
- `docs/development/databento-full-history-acquisition/evidence.json` — original quarantined acquisition state.
- `docs/development/databento-full-history-acquisition/repair-evidence.json` — repaired 19/19 statistics integrity through 2026-08-12.
- `config/data_sources.json` — current Databento fail-closed canonical/licensing status.
- `docs/development/databento-offline-dbn/evidence.json` — validated offline canonicalizer on preserved real data.
- `docs/development/weather-revision-readiness/decision-record.md` and `evidence.json` — NOAA GFS archive feasibility and #114 constraints.
- GitHub issues #51, #113, #137, #147 and #148 — licensing/adoption, storage source gate, untouched confirmation, target portfolio and surprise/revision representation boundaries.

No new model fit, prediction generation, OOS result inspection, or paid acquisition was performed for #149.
