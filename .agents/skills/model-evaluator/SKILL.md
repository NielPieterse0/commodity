---
name: model-evaluator
description: Use when comparing trained models, checkpoints, baselines, or forecast outputs and deciding whether predictive performance is reliable enough for a research disposition.
---
# Model Evaluator

## Purpose
Evaluate forecast/model generalization, uncertainty, robustness, and failure modes on data isolated from model-selection decisions.

## Workflow
1. Verify evaluation dataset identity, point-in-time validity, split isolation, target integrity, and metric definitions before scoring.
2. Compare against predefined baselines and the prior promoted research model using the same protocol.
3. Report the primary metric with uncertainty and relevant secondary predictive metrics.
4. Analyze errors by meaningful segments and failure categories; do not hide regressions behind one aggregate score.
5. Test robustness across seeds, folds, periods, perturbations, or regimes when those dimensions are deployment risks.
6. Use `statistical-analyst` for permutation tests, bootstrap intervals, paired comparisons, or multiple-testing questions.
7. Make only a research disposition against predefined criteria and record unresolved caveats.

## Boundary
This skill owns forecast/model evaluation. It does **not** own signal construction, position sizing, transaction-cost policy, execution simulation, broker behavior, or trading authorization. Domain workflows may consume forecasts downstream without changing this boundary.

## Guardrails
Keep final-test evaluation separate from tuning. Preserve negative and failed evaluations. `promote` means research promotion only.
