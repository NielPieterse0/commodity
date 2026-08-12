---
name: hyperparameter-optimizer
description: Use when tuning model or pipeline hyperparameters under an explicit search space, metric, validation protocol, compute budget, and overfitting-control strategy.
---
# Hyperparameter Optimizer

## Purpose
Search configuration space without turning the validation set into an unacknowledged training target.

## Workflow
1. Require a fixed dataset version, validation protocol, baseline, primary metric, and resource budget.
2. Define the search space before trials; mark conditional parameters and invalid combinations explicitly.
3. Start with a bounded search; use adaptive search only when it offers a practical advantage over a simple sweep.
4. Record completed, pruned, failed, and invalid trials with configuration, seed, metric, duration, and artifact references.
5. Use pruning only when intermediate metrics are comparable and do not systematically favor certain configurations.
6. Check whether the apparent winner is stable across seeds, folds, or time windows rather than selecting one maximum validation score.
7. Re-evaluate only the selected configuration on the untouched final test set.

## Required Output
Search space; search strategy; validation protocol; optimization metric; trial budget/stopping rule; complete trial summary; selected configuration with stability evidence; final-test reference.

## Guardrails
- Do not expand the search indefinitely after near-misses.
- Do not treat validation-search significance as untouched confirmatory evidence.
- Distributed tuning is optional infrastructure, not a default requirement.
