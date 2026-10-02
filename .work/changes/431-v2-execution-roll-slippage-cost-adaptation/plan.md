# Plan: V2 Execution and Adaptation

1. Bind #430, #429, #448, registry, simulation, research-dataset, and trading-policy identities.
2. Freeze #431 preregistration and trial budgets before any #431 scoring.
3. Implement execution-path transforms and chronological adaptation helpers under TDD.
4. Run a no-scoring preflight proving source identities, evidence boundaries, executable fill support, roll-path support, and frozen trial accounting.
5. Score the frozen execution/cost/liquidity stage against one conservative reference.
6. Score the frozen adaptation stage with prior-only model fitting and deterministic promotion rules.
7. Write every attempt to the trial ledger and summarize return, cost, drawdown, concentration, turnover, roll, and stability diagnostics.
8. Run focused tests, Ruff, canonical verification, and exact-diff independent review.
9. Commit, prepare PR, require exact-head CI, merge, reconcile Work/documentation state, and clean the worktree.

## Design rule

Selection occurs only inside chronological development. Protected confirmation remains sealed even when an execution/adaptation variant looks strong.
