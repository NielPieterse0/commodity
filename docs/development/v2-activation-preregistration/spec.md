# V2 Executable Contract Preparation (#81)

## Scope

This slice is Agent 2's #81 lane only. It prepares the V2 executable contract against the landed #78 longitudinal metrics/comparability authority. It does not perform or authorize model fitting, prediction generation, feature computation, data acquisition, tuning, results-driven design, #88 audit work, or empirical V2 execution.

## Current gates

1. #78 is closed/reconciled and landed in PR #95 at `3e2aa9117a82368782eb5c674eb33c62ef2fd9ee`.
2. PR #92 is landed in the current base at `e11a891b58e67b61593b9c2ec5c86974e64cb0bc`, but #15 itself remains open pending final operator/Work Management closeout. Therefore #81 is **prepared but not frozen or activated**.
3. After #15 closes/reconciles, Agent 2 may freeze the executable #81 identities and candidate records.
4. Agent 3 then independently executes #88 against the frozen #81 record. #82/#83 remain empirically blocked until #88 passes.

## #78 binding

`activation-contract-draft.json` binds directly to `contracts/research_metrics.schema.json` and `artifacts/research-metrics/longitudinal-ledger.json`. It inherits the exact #78 comparison kinds `previous_stage` and `best_comparable`, policy `strict-no-silent-regression-v1`, and the landed required metric set: `model_rmse`, `baseline_rmse`, and `rmse_improvement_vs_baseline`.

The contract does not invent a singular primary metric because #78 declares three required metrics. Optional longitudinal diagnostics remain inherited exactly from the #78 policy.

## V1-comparable control preparation

The landed Phase D stage `phase-d-full-v1-hist-gb` is recorded as the planned V1 control because it carries the final governed V1 target, dataset/OOS, split/protocol, baseline, PIT-availability, and evidence identities. The control is **not frozen** while #15 is open. At freeze time, the hard-context identity must still match; otherwise the V2 primary comparable claim fails closed or receives a separate non-comparable experiment identity.

## Resolved authority values

The preparation now resolves from #78 the V1 target/horizon/timestamp semantics; dataset ID, freeze/vintage ID, dataset SHA, OOS window and coverage signature; evaluation protocol/split identities; baseline identity; PIT-availability rule; and required/optional metric identities and materiality policy.

Mutable V2-only fields such as final candidate IDs, component-control IDs, exact V2 code revision, deterministic artifact namespace, seeds, leakage guard, uncertainty/multiplicity rule, thresholds, and compute/data-cost caps remain explicitly unresolved until the #15 gate closes and #81 is frozen. Their unresolved state is a block on activation, not permission to guess them.

## Execution boundary

`config/experiment_candidates.json` remains untouched by this preparation slice. `execution_authorized` and all empirical release flags remain false. No result-producing command is part of this change.
