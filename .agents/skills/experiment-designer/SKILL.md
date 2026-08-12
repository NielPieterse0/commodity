---
name: experiment-designer
description: Use when turning a research question into a falsifiable ML or statistical experiment with explicit point-in-time data boundaries, temporal splits, baselines, controls, metrics, and research promotion criteria.
---
# Experiment Designer

## Purpose
Design experiments so a positive result can survive leakage checks, baseline comparison, repeated runs, and independent review.

## Workflow
1. Write a falsifiable hypothesis and the research decision the experiment should inform.
2. Define the forecast target, horizon, prediction timestamp, target observation timestamp, and information cutoff before training.
3. Bind every dataset to immutable identity, hash, as-of timestamp, and data-vintage/revision identity.
4. Define explicit training, validation, and test period boundaries and the split strategy.
5. Bind feature definitions and preprocessing to immutable identities; fit learned preprocessing on training data only.
6. Choose the simplest credible baseline and at least one control that can expose false signal.
7. Predefine primary/secondary metrics, uncertainty method, failure criteria, leakage checks, seed policy, repeats, resource budget, and stopping criteria.
8. Define research promotion criteria that require robustness rather than peak score.

## Experiment Contract
Every run conforms to `../../../ml-research-core/contracts/experiment.schema.json`. `promote` means research promotion only; operational or trading authorization is outside this contract.

## Failure Modes
Test-set tuning; weak baselines; temporal leakage; revised data used as if historically available; implicit split boundaries; unversioned preprocessing; metric hunting; promotion from one favorable seed or period.
