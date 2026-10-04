# Change Closeout: V2.38 Adverse Path Add Guard

- **Change ID:** `470-v238-adverse-path-add-guard`
- **Authority:** GitHub issue #470 / `WORK-470`
- **Base:** `cc3422fd0f0350b7b19d1509d19b2575caba0ee2`
- **Scope:** Single causal same-side ADD guard only.

## Implemented behavior

V3 blocks an otherwise-valid increase in absolute exposure on an already-open same-side position when the matured current-position-instance `economic_path_pnl_fraction < 0`.

The guard is implemented consistently in the reference lifecycle, meta-controller lifecycle, and optimized replay kernel. It does not alter starter entries, reversals, ordinary reductions, exits, holds, or hard-risk reduction precedence.

The runner code identity now binds `v3_replay_engine.py`, preventing replay evidence from silently surviving optimized-engine changes.

## Causal / PIT boundary

Only outcomes with `outcome_available_at < decision_time` mature into current-position economic-path P&L. Outcomes available exactly at the decision timestamp remain unavailable. Position-instance IDs prevent realized outcomes from prior position instances contaminating the current instance.

## Verification and audit

Focused affected verification passed: **72 tests passed** across the #470 lifecycle/PIT suite, #468 optimized replay-engine suite, and V3 runner/controller suites. The closeout audit regression test also passes, bringing the dedicated #470 file to **12/12 passed**.

`git diff --check` and Ruff pass. Manual scope review confirmed the production/research implementation is limited to the guard, reason-code propagation, optimized-kernel parity, replay-engine identity binding, and one audit-checker bug fix found during closeout.

The scope audit initially produced two false failures because it treated `managed_money_net` as an age field by substring matching `age` inside `managed`. The audit now recognizes only semantic age metadata keys (`*_age` / `*_age_*`), and the rerun passes **66/66 checks**.

## Final replay/proof gate

The exact Block-1 replay completed all **96 structural candidates × 3 execution scenarios = 288 scenario replays** with exit code 0. Full future-invariance status is **PASS**, including all 288 structural scenario decision-prefix and matured-execution audits.

Final Block-1 net return is **+1.46%** (`$1,460` on `$100,000` initial capital). Transition-aware side contribution is **+3.695% short / -2.235% long**. Base post-warmup return is **+1.475%**; moderate and severe execution stresses are **-0.195%** and **-0.300%** respectively. The frozen decision-brain SHA is `561f853da7a9815e936775ed059b4df93861c7ab597bfd5c92b94967a57d264b`.

The replay cache and generation staging (~644 MB) were moved to repository-local ignored temp storage under `.work/temp/470-closeout-cache` rather than committed. The PR retains only the compact final replay result and 66-check completeness audit.

## Scope exclusions

No jump-state logic is part of #470. Jump research remains a separate post-#470 Block-1 development workstream so the #470 causal effect remains attributable.
