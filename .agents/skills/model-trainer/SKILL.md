---
name: model-trainer
description: Use when running or reviewing model fitting across classical ML or neural models with controlled seeds, checkpoints, budgets, artifacts, and comparable training records.
---
# Model Trainer

## Purpose
Produce comparable, traceable training runs tied to exact data, configuration, code, environment, and evaluation inputs.

## Workflow
1. Require dataset identity, split strategy, baseline, primary metric, and leakage disposition before training.
2. Capture model family, configuration, hyperparameters, random seeds, environment identity, hardware, and resource budget.
3. Keep validation for model-selection decisions and preserve the final test set for final evaluation.
4. Record training/validation diagnostics, checkpoint selection rule, early-stopping rule, duration, failures, and warnings.
5. Save selected checkpoints with stable IDs or hashes; never overwrite prior promoted checkpoints.
6. Run the required seed/repeat policy and hand all candidates, not only the winner, to `model-evaluator`.
7. For adaptation, record base-model identity and method separately from the resulting checkpoint.

## Minimum Run Record
Dataset version/hash; split; model family/architecture; seeds; hyperparameters; code/environment revision; hardware; duration; checkpoint rule; selected checkpoint; training metrics; artifact locations.

## Guardrails
- Do not tune against the final test set.
- Do not silently resume from old checkpoints or cached state.
- Do not promote from one unusually favorable run.
- Keep untrusted model artifacts and training code inside approved execution boundaries.
