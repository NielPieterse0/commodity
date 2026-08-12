---
name: reproducibility-auditor
description: Use when checking whether another researcher or agent could rerun an experiment and obtain materially consistent results from the recorded data, code, environment, seeds, and artifacts.
---
# Reproducibility Auditor

## Purpose
Decide whether an experiment can be independently reconstructed and whether result variance is understood well enough to trust the conclusion.

## Audit Sequence
1. Verify dataset hashes, split definition, preprocessing fit scope, code revision, environment identity, configuration, seeds, and checkpoint hashes.
2. Check hidden state: manual notebook edits, unrecorded caches, mutable external data, implicit environment variables, local files, resumed checkpoints, or order-dependent cells.
3. Confirm deterministic controls were requested where supported while recognizing platform-specific nondeterminism.
4. Compare repeated runs using the project seed policy; distinguish exact from statistical reproducibility.
5. Verify reported results can be derived from saved predictions/metrics and that checkpoint selection follows the recorded rule.
6. Check that failures, exclusions, and post-hoc changes are documented.
7. Return `reproducible`, `statistically-reproducible`, `partially-reproducible`, or `not-reproducible`.

## Evidence Checklist
Dataset hash; code revision; environment lock/container identity; seeds; split manifest; preprocessing state; configuration; checkpoint hash; evaluation artifact; repeated-run variance; unresolved nondeterminism.

## Guardrails
Do not claim reproducibility from a single rerun when stochastic variance matters. Do not require bit-for-bit equality where the platform cannot guarantee it; require bounded, decision-equivalent behavior and record the tolerance.
