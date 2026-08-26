# #205 — Non-overlapping volatility successor preregistration

**Status:** frozen design; no calibration or confirmation execution is authorized
**Assessment date:** 2026-08-26

## Decision

#203 rejected #197's daily confirmation design before any protected confirmation outcome was opened. Its frozen nuisance calibration put the 80%-power MDE for a 5% relative QLIKE effect at 16.59% to 21.64%, depending on the dependence block. Repeating that design with 1,800 rows is therefore prohibited.

Freeze a changed design that predicts **integrated realized variance over the next five CME sessions** at a fixed every-fifth-row schedule. Scored target windows do not overlap. The design remains market-only and uses the already-approved Databento Henry Hub batch, so it does not inherit the unresolved historical-consensus requirement of storage-surprise work.

This slice does not claim that the new design is powered. It freezes a nuisance-only power gate that must pass before any confirmation performance can be opened.

## Freshness and protected evidence

The exact #201 historical identity has 2,772 pre-2024-08-13 daily rows: 972 development/calibration rows followed by 1,800 untouched candidate confirmation rows. #203 consumed only permitted nuisance summaries from the earlier calibration role. It did not inspect performance from the final 1,800 rows.

The final 1,800 daily rows may supply raw market bars to this **changed target** only because the new design is frozen before their model performance is inspected. The locked 504 future rows remain completely separate and are not reused.

An independent source-bound audit must reconstruct the new event identities from the fixed daily identity before any model output. Row identity, calendar, contract identity, PIT availability and target coverage may be inspected; performance may not.

## Target and schedule

Within each frozen role window, start from its first daily row and take every fifth row as a prediction anchor. An inadmissible anchor is dropped without shifting later anchors. This prevents the sample schedule from adapting to outcomes or roll gaps.

For each anchor, the target is the sum of Garman–Klass daily variance over the next five chronological CME trade dates for the contract selected at prediction time. All five target bars must exist on that same contract and must become available strictly after the prediction cutoff. Cross-contract substitution is forbidden.

## Models and loss

The primary baseline is the mean of the prior four non-overlapping five-session integrated-variance blocks on the prediction contract.

The sole challenger is a fixed OLS log-HAR model using exactly three inputs: the last one-block log variance, the log mean of the prior four blocks, and the log mean of the prior twelve blocks. There is no feature selection, hyperparameter search or alternate model family.

Training is expanding. The first 80 admissible development events are initial training. Refit every four scored events, using only labels available by that prediction time.

Primary loss is QLIKE on integrated variance. Positive paired improvement means baseline QLIKE minus challenger QLIKE is positive. The materiality threshold remains a 5% relative QLIKE reduction.

## Information budget

At the old #197 primary dependence assumption, 1,800 daily outcomes represented only 45 forty-session block-equivalent units. At the new minimum of 300 non-overlapping events, a four-event primary block represents 75 block-equivalent units. The corresponding standardized 80%-power MDE improves from about 0.418 to 0.323.

The new design also improves the conservative sensitivity comparison: 300 events with an eight-event block provide 37.5 block-equivalent units versus 30 units for #197's sixty-session sensitivity.

These are information-scale comparisons only. They do not establish the relative QLIKE MDE because the new target changes both baseline scale and paired-loss variance.

## Nuisance-only calibration gate

After the first 80 training events, freeze the next 80 admissible development events as nuisance calibration. The calibration may emit only mean baseline QLIKE, centered paired-loss block SD for 2/4/8-event blocks, and the resulting relative MDE at the exact frozen confirmation event count.

It must not expose mean challenger QLIKE, mean paired improvement, p-values, confidence intervals, chronological/regime results or secondary performance.

All 2/4/8-event relative MDEs must be at or below 5%. If any exceeds 5%, stop before confirmation and create a new preregistration. The materiality threshold may not be weakened after calibration.

## Confirmation sample and inference

The confirmation sample is every admissible fixed-schedule event from the untouched 1,800-row historical role. The theoretical maximum is 360 events. The independent audit must establish the exact count before model output; at least 300 events are required. If fewer than 300 survive same-contract/PIT checks, stop rather than shift the window or relax admission rules.

Primary inference is a 1,000-resample moving-block bootstrap of event-level paired QLIKE improvement, seed 0, with a four-event primary block and two/eight-event sensitivity blocks. There is one primary hypothesis and a two-sided 5% significance level.

Confirmation requires positive mean QLIKE improvement, a positive 95% interval lower bound, p <= 0.05, and at least 5% relative QLIKE reduction. Secondary metrics cannot rescue failure.

## Data and authority

Current `config/data_sources.json#sources.databento_henry_hub_probe` is authoritative for this use and records the already-purchased `GLBX.MDP3` NG batch as canonical, backtest-evidence allowed, integrity complete and licensing verified for private-project research/backtesting. No new paid acquisition is authorized.

Research design does not grant trading authority. `config/policy.json` remains the sole execution authority.

## Independent release audit

A separate audit must bind the exact hashes of `contract.json`, `power-analysis.json`, this preregistration and `freeze.json`; reconstruct the fixed event identity; prove the final 1,800 daily performance remained unopened when #205 froze; and release only the nuisance calibration first.

Confirmation remains unauthorized until the nuisance gate passes and a subsequent release binds the exact confirmation identity and calibration result. No feature/model rescue search is permitted.

## Stop rules

Stop if protected #197 performance or the locked 504-row performance is opened before release; if the fixed confirmation identity has fewer than 300 events; if same-contract/PIT semantics fail; if any nuisance MDE exceeds 5%; or if the frozen target, model, baseline, loss, schedule, inference or materiality rule changes.

The scientific point of #205 is not that weekly aggregation creates information from nothing. It removes overlapping scored targets and changes the economic horizon before outcomes are opened, then requires the new loss process to prove its own detectability before confirmation.
