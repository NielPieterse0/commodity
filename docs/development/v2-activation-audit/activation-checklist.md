# #88 V2 Activation Audit — Preparation Checklist

**Owner:** Agent 3
**State:** Prepared, not executed, not passed
**Authority revision:** `3e2aa9117a82368782eb5c674eb33c62ef2fd9ee`

This checklist is fail-closed. A checked preparation item is not an activation approval. #88 may pass only after #15 is closed/reconciled and Agent 2 has frozen #81 at an exact revision.

## Current hard gates

- [x] #78 is closed/reconciled and the longitudinal metrics/comparability owner is landed.
- [ ] #15 is closed/reconciled. **BLOCKING: currently open.**
- [ ] Agent 2 has frozen #81 at an exact reviewable revision. **BLOCKING: not yet frozen.**
- [ ] Independent statistical/model/reproducibility review has run on that exact #81 revision. **Not run.**

## Inherited recommendation/control audit

- [ ] Every credible inherited recommendation from #77, #78, V1 caveats, #80, #81-#86, #51 and accepted staging discussion has exactly one disposition.
- [ ] Every disposition has an owner issue; deferred/rejected items also have an evidence-backed rationale and real review trigger.
- [ ] No mutable hypothesis is duplicated across issues unless the relationship and precedence are explicit.
- [ ] Fixed V1 correctness controls remain regression-protected controls, not research candidates.
- [ ] The governed `no_robust_edge` V1 result remains longitudinal history and is not rewritten as a bug.
- [ ] The PIT-core smoke → Phase D movement remains classified non-comparable/non-causal unless new separately governed evidence establishes otherwise.
- [ ] Roll-day and M1/selected-contract caveats are either bounded preregistered hypotheses or deferred; they do not mutate the primary comparator post hoc.
- [ ] Surprise/revision/anomaly, horizon/frequency, scaling/tails/effective-N, regimes, alternative targets, provider depth, seed semantics and diagnostics all have explicit dispositions.
## Frozen #81 contract audit

- [ ] Exact experiment/candidate IDs, code/config revision and deterministic artifact namespace are frozen.
- [ ] Strongest comparable V1 control identity is frozen from #78 authority before any V2 result exists.
- [ ] Dataset ID, data-vintage ID, evidence tier, lineage, target/horizon, PIT cutoff and split identity are immutable and fail closed if absent.
- [ ] Seed semantics, component controls, leakage guard and permitted feature/model inputs are frozen.
- [ ] Material-improvement threshold, uncertainty/significance rule, multiplicity treatment, compute/data-cost cap and stop/failure criteria are frozen.
- [ ] `previous_stage` and `best_comparable` longitudinal comparisons are required through the #78 owner rather than duplicated locally.
- [ ] Negative/non-increment and invalid/non-comparable outcomes are first-class dispositions; no rescue search is permitted.

## Release decision

- [ ] Independent review finds no activation-blocking statistical, model, reproducibility or governance gap.
- [ ] Every mandatory check above is satisfied on the same frozen #81 revision.
- [ ] #88 is explicitly recorded as passed only after the evidence above is complete.
- [ ] Only then may #82 and #83 empirical execution be released in parallel.

**Current decision: NOT ELIGIBLE TO AUDIT FOR PASS.**

Current next trigger: close/reconcile #15, then Agent 2 freezes #81. Until then, Agent 3 performs preparation only and does not run V2 models, predictions, acquisition, tuning or results-driven design.
