---
name: neural-network-engineer
description: Use when a neural model needs architecture choices, training-stability diagnosis, checkpoint strategy, transfer learning, fine-tuning, or parameter-efficient adaptation.
---
# Neural Network Engineer

## Purpose
Make neural-model changes that are testable, resource-aware, and separable from data or evaluation errors.

## Workflow
1. Establish a small baseline and confirm the pipeline can intentionally overfit a tiny sample before scaling.
2. Track tensor shapes, target/activation/loss compatibility, parameter counts, initialization, optimizer, schedule, batch size, precision mode, and gradient behavior.
3. Diagnose instability from curves, gradients/activations, numerical errors, data anomalies, and learning-rate sensitivity before adding complexity.
4. Use checkpoints with explicit selection criteria; record whether training is fresh, resumed, fine-tuned, or adapted.
5. For transfer or parameter-efficient adaptation, pin base model and preprocessor identity, trainable parameter scope, adapter configuration, and artifact state.
6. Compare architecture changes with controlled ablations and multiple seeds when variance matters.
7. Return candidates to `model-evaluator`; architecture work does not decide promotion by itself.

## Common Failure Modes
Loss/target mismatch; unstable precision; leakage mistaken for architecture lift; incomparable datasets/splits; test-driven checkpoint selection; adaptation artifact missing its base dependency.

## Guardrails
Prefer the smallest architecture that answers the hypothesis. Distributed training and complex adapters are optional infrastructure, not evidence of model quality.
