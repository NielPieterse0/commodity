---
name: statistical-analyst
description: Use when estimating uncertainty, testing whether an observed effect is distinguishable from chance, comparing groups or models statistically, or checking whether a claimed pattern is robust.
---
# Statistical Analyst

## Purpose
Quantify evidence, uncertainty, and robustness without converting noisy patterns into confident claims.

## Workflow
1. State the estimand or hypothesis before choosing a test.
2. Check whether observations are independent, paired, clustered, time-dependent, censored, imbalanced, or otherwise structured.
3. Report effect size and uncertainty first; use significance tests as supporting evidence.
4. Prefer resampling when assumptions are weak: bootstrap intervals for uncertainty and permutation/randomization tests for exchangeable nulls.
5. Account for repeated experimentation or multiple comparisons across hypotheses, models, windows, or features.
6. Test sensitivity across seeds, periods, subgroups, preprocessing choices, and outlier treatments when those choices can change the result.
7. Separate confirmatory analysis from exploratory pattern discovery.

## Minimum Result
Hypothesis/estimand; sample definition; effect estimate; uncertainty interval; null/test when applicable; p-value or posterior probability when applicable; multiple-testing treatment; robustness results; conclusion and limits.

## Guardrails
- A significance threshold is not proof of practical importance.
- Do not random-shuffle dependent time series merely to satisfy a test assumption.
- Do not present post-hoc selected windows or subgroups as pre-specified evidence.
