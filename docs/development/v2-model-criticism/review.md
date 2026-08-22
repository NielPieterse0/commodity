# #89 — V2 post-experiment model criticism and research-design review

**Assessment date:** 2026-08-22

## Decision summary

The completed evidence does not support continuing the same next-session Henry Hub return problem by simply trying a larger model or another unrestricted feature/model search.

The strongest comparable result remains the zero-return baseline. Phase-D HistGB was mildly but systematically worse than zero-return on the 204-row governed OOS sample. Corrected Kronos Mini, Small and Base were materially worse again. The #83 indicators challenger produced no model result because its preregistered weather-coverage rule failed before fitting. Fusion #84 and sensitivity #85 therefore never produced valid empirical performance evidence.

The next research stage should change the question only through separately preregistered hypotheses. Highest priority is to test whether information is better aligned with event/revision representations and with economically justified alternative horizons/targets, while first quantifying the effective-sample-size and detectable-effect budget.

## Evidence that is valid for this review

- Phase D: `docs/development/v1-research-completion/phase-d-closeout.json` and `phase-d-regression-diagnostics.json`.
- Longitudinal authority: `artifacts/research-metrics/longitudinal-ledger.json`.
- Indicators: `docs/development/v2-indicator-surprise-challenger/empirical-closeout.json`.
- Corrected Kronos: `docs/development/kronos-three-checkpoint-confirmation/results/closeout.md` and its frozen result artifacts.
- Weather-revision readiness: `docs/development/weather-revision-readiness/decision-record.md`.
- Frozen but unexecuted designs: #84 fusion contract and #85 sensitivity manifest.

## Result interpretation

Phase-D HistGB RMSE was `0.04650734` versus zero-return `0.04532306`, an RMSE improvement of `-0.00118428`. Its 95% moving-block bootstrap interval for improvement was entirely below zero and it was worse than zero-return in all three frozen chronological periods and all three frozen regimes.
Ridge RMSE was `0.05588330`. Its failure was partly tail-concentrated: one January fold dominated much of its excess loss and it emitted a `-23.2%` one-day return forecast. But removing the worst January fold, or both worst January folds, still left Ridge and HistGB worse than zero-return. Robust-loss ideas therefore remain only a low-priority future hypothesis, not an explanation that rescues Phase D.

HistGB behaved differently from Ridge. Its prediction standard deviation was only about `0.81%` versus realized-return standard deviation about `4.54%`, yet its OOS prediction/actual correlation was slightly negative (`-0.058`). This is evidence of weak information at this target/grain, not merely excessive prediction scale.

The corrected #180 experiment strengthens that conclusion for direct Kronos. Best checkpoint Small had RMSE `0.05529308`, direction accuracy `50.0%`, and prediction/actual correlation `-0.02436`. Mini and Base were also worse than both frozen baselines; all three had zero positive frozen periods and zero positive frozen regimes against either baseline. Larger checkpoint size did not improve performance monotonically.

#83 cannot be interpreted as a negative indicator model. Six required rows failed the frozen weather staleness rule, including two scored rows. No model was fit, no predictions were produced and no metrics exist. The valid conclusion is data/design infeasibility for that exact candidate, not lack of predictive value for all surprise/revision features.

Likewise, #84 fusion and #85 secondary-horizon sensitivity have no empirical result to criticize. Their frozen designs are historical design evidence only. They cannot be counted as failed models or used as support for a new claim.

## Assumption and design matrix

| Assumption / design choice | Disposition | Evidence | Consequence |
| --- | --- | --- | --- |
| Next-session signed return is the primary research target | **revise** | Phase-D HistGB and all corrected Kronos checkpoints fail zero-return; information correlations are weak/negative | Compare alternative horizons/targets under #147, with power budget from #155 |
| Zero-return is the mandatory economic baseline | **retain** | It beats Phase-D HistGB, Ridge and all #180 Kronos checkpoints | Keep as a hard comparator wherever target semantics make it valid |
| Strict PIT eligibility and fail-closed coverage | **retain** | #83 correctly stopped before fit rather than imputing or dropping rows | Do not relax coverage to manufacture a result |
| RMSE as primary next-session return loss | **retain for comparable H1 tests; investigate for redesigned targets** | It exposed real deterioration; alternative targets may require target-native loss such as QLIKE | #147 owns target/loss portfolio; no retroactive metric switching |
| Moving-block uncertainty, BH multiplicity and frozen robustness slices | **retain** | Phase-D and #180 conclusions remain negative across these controls | Carry forward unless a new target requires a separately justified dependence model |
| Full-session aggregate feature levels are sufficient representation | **revise** | 0/21 Phase-D family tests passed; #83 could not test its revision increments | Prioritize news/surprise/revision representation under #148 |
| Direct one-step Kronos close forecast as return component | **retire for this target/grain** | Mini/Small/Base all materially fail both frozen baselines; best checkpoint correlation is near zero | Do not run a checkpoint-size search or calibrate #180 post hoc |
| Larger Kronos checkpoint should improve the result | **retire** | Small beats Mini; Base is worst | Model size is not a justified search axis for this problem |
| Kronos calibration alone is likely to rescue H1 | **retire as promotion hypothesis; diagnostic only** | Corrected checkpoints have weak information correlation as well as scale error | #153 may remain historical/diagnostic, but any calibration claim needs a new contract and untouched confirmation |
| Current #83 weather source/staleness design is feasible at 100% required coverage | **retire** | Six required rows violate the frozen 24-hour bound | Replacement weather design must use a new identity; #114/#148 own the redesign direction |
| Weather forecast revisions are worth a bounded future test | **investigate** | #114 records medium direct working-paper evidence plus PIT-feasible NOAA GFS history | Preregister under #148 before any empirical inspection |
| Storage surprise is worth a bounded event-window test | **investigate** | Economic mechanism is strong but current repo lacks a verified historical PIT consensus series | #113 owns PIT-source verification and preregistration; stop if consensus history is infeasible |
| Equal-weight Kronos + indicator fusion remains a priority | **retire as current V2 path** | One component is empirically poor and the other never became valid for fit | Any later fusion must follow separately successful component evidence, not revive #84 |
| H5 sensitivity can rescue failed H1 | **retire** | #85 explicitly had no rescue authority and never executed | Alternative horizons are new hypotheses under #147, not sensitivity rescue |
| Current 204-row OOS window is sufficient for broad negative claims | **revise** | About 10.2 effective 20-row blocks; conclusions are specification-specific | Quantify MDE/effective N in #155; deeper-history decision in #149 |
| More history is automatically better | **retire** | Historical smoke/full-V1 transition is non-comparable and regime drift remains possible | Acquire deeper canonical history only when #149 shows decision value |
| Regime/event conditioning should be searched post hoc | **retire** | Frozen aggregate failures cannot be rescued by favorable slicing | Only small ex-ante interactions under #150 |
| Ridge-like linear prediction scale is acceptable without robust controls | **revise if Ridge-like models return** | Severe January tail forecasts and loss concentration | Robust loss/scaling is conditional design work, not a current priority |
| Current selected-contract same-contract market semantics | **retain** | #178/#180 corrected the prior interface defect and produced clean comparable evidence | Do not reopen roll stitching as an alpha hypothesis without new evidence |
| Evaluator should report undefined correlation as zero | **revise for reporting correctness** | Constant prediction correlation is mathematically undefined | #170 owns successor evaluator semantics; no scientific conclusion changes |

## Ranked next-stage portfolio

1. **Power and effective-N gate — #155, then #149.** Before consuming new OOS evidence, quantify what effects the current dependence/multiplicity gate can plausibly detect and whether deeper canonical history materially changes candidate viability.
2. **Target/horizon portfolio — #147.** Compare next-session return with 2–5 session/event-window return, weekly return, volatility and economically natural curve/spread targets. This is design work first, not a target sweep on consumed outcomes.
3. **News/surprise/revision representation — #148.** Replace generic level accumulation with a small mechanism-led taxonomy. Weather revision is supported by #114; storage surprise remains conditional on #113 proving a PIT-safe consensus source.
4. **Bounded event/regime interactions — #150.** Only after the mechanism and sample budget are fixed. Thresholds and event definitions must be frozen before confirmation data are inspected.
5. **Untouched confirmation — #137.** Every adaptive candidate produced from this review must earn promotion on evidence not used to formulate it: future walk-forward data, a strict untouched historical holdout, or another explicitly controlled sequential design.
6. **Kronos diagnostic — #153, low priority.** Frozen-artifact information/calibration decomposition may remain useful historically, but corrected #180 already gives strong evidence against direct H1 Kronos. It cannot reopen checkpoint or calibration search.
7. **Evaluator reporting correction — #170.** Fix undefined-correlation semantics through its successor freeze. This improves reporting correctness but does not change RMSE or the negative research conclusions.

No new issue is needed for robust loss/scaling now. Ridge tail instability justifies retaining it as a conditional design consideration if a future Ridge-like model is proposed, but HistGB and Kronos failures show that robust loss alone is not currently the highest-value hypothesis.

## Rejected and null hypotheses retained

- Frozen Phase-D full V1 produced `no_robust_edge`; do not rewrite it as a software bug.
- The tiny PIT-core smoke advantage is not a stable prior edge and is not comparable to Phase D.
- None of the 21 predefined Phase-D family tests demonstrated material incremental value.
- Direct next-session Kronos Mini/Small/Base is rejected for the frozen role; larger checkpoint search is stopped.
- #83's exact indicator candidate is invalid-before-fit; do not silently retry it with looser weather staleness, row drops, imputation or reduced families.
- #84 equal-weight fusion is not an untested shortcut to rescue the programme; its prerequisites did not produce two valid promising components.
- #85 H5 sensitivity cannot be used as a rescue interpretation of H1 and generated no empirical evidence.

## Comparability and fresh-confirmation rules

Any future candidate retaining the exact H1 selected-contract return target, scored-row identity and evaluation semantics may use #78 longitudinal comparability where all required identities remain compatible. A changed target, horizon, event window, loss identity, data source, representation or model role must be classified as a new research stage rather than forced into a false like-for-like comparison.

Observed V1/#180 outcomes are hypothesis-generation evidence for #147/#148/#150, not confirmation evidence for those hypotheses. #137 remains the mandatory promotion boundary: no adaptive candidate may be promoted using the same observations that motivated its redesign.

## Overall disposition

The evidence supports **changing the research question before changing model size**. Keep the hard PIT/baseline/statistical controls. Stop direct H1 Kronos and the old V2 fusion path. First quantify the evidence budget, then preregister a small number of economically motivated target/horizon and news/revision hypotheses, and require untouched confirmation before any promotion.
