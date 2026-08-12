---
name: feature-engineer
description: Use when creating, selecting, transforming, or auditing predictive features while controlling leakage, temporal availability, stability, and reproducibility.
---
# Feature Engineer

## Purpose
Create features that are available at the decision point, reproducible from defined inputs, and stable enough to evaluate honestly.

## Workflow
1. Define source fields, transformation, expected type/range, and availability timestamp for every material feature.
2. Establish a simple raw-feature baseline before complex transformations.
3. Fit learned preprocessing only on training data: scaling, vocabularies, imputation, selection, embeddings, and dimensionality reduction.
4. Audit future data, target proxies, post-outcome fields, cutoff-crossing windows, duplicate entities across splits, and backfilled attributes.
5. Test missingness, sparsity, cardinality, drift, and stability by split, time, and important segment.
6. Prefer interpretable derivations with stable incremental value; remove complexity without repeatable lift.
7. Version feature definitions and bind them to dataset and experiment records.

## Required Evidence
Feature derivation; source and temporal availability; preprocessing fit scope; leakage status; quality profile; ablation/incremental-value evidence; known drift risks.

## Guardrails
- Never use information unavailable at inference time.
- Never infer usefulness from full-dataset correlation alone.
- Treat target encoding, rolling aggregates, entity history, and externally refreshed attributes as high-risk until cutoff logic is verified.
