# Target Matched Physical Bottleneck Feasibility Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Persist and reconcile the unscored #351 feasibility decision without opening or scoring protected outcomes.

**Architecture:** Store the detailed source/timing/capacity evidence under a new Line-005 feasibility identity. Project only the resulting programme state into the canonical feasibility map, supporting ledger/setup, revisit registry, backlog, and Line-005 summary; generated documentation follows repository authority.

**Tech stack:** governed JSON research records, deterministic documentation generator, repository verification, KIS Git/GitHub lifecycle.

**Spec:** `.work/changes/351-target-matched-physical-bottleneck-feasibility/spec.md`

## Global constraints

- Stay inside `scope.json`.
- GitHub issue #351 is the scientific requirements authority.
- Do not fit or score A/B/C outcomes.
- Do not open sealed confirmation outcomes.
- Preserve rep-021 as narrower INCONCLUSIVE evidence.
- End the scientific slice with exactly `HOLD pending named data/capacity remedies`.

### Task 1: Persist feasibility evidence

**Files:**
- Create: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/experiments/feas-022-target-matched-physical-bottleneck/feasibility.json`

- [ ] Record source identities and target/delivery mapping semantics.
- [ ] Record the BHLR target-period/PIT availability audit and exact coverage limits.
- [ ] Record gross and exposure-restricted candidate counts before any development split.
- [ ] Record outcome-blind planning sensitivities for the 1% RMSE threshold, label their assumptions, and distinguish detection versus zero from the full survivor rule and precision to rule out improvements of 1% or more.
- [ ] Name confirmation and acquisition/engineering remedies with cost/authority boundaries.
- [ ] Assert that no outcome scoring or protected-outcome access occurred.

### Task 2: Reconcile Programme 002 state

**Files:**
- Modify: `research/programmes/002-henry-hub-fresh/evidence-map.json`
- Modify: `research/programmes/002-henry-hub-fresh/feasibility-ledger.json`
- Modify: `research/programmes/002-henry-hub-fresh/experiment-setup.json`
- Modify: `research/programmes/002-henry-hub-fresh/feasibility-readiness.json`
- Modify: `research/programmes/002-henry-hub-fresh/revisit-triggers.json`
- Modify: `research/programmes/002-henry-hub-fresh/decisions.json`
- Modify: `research/programmes/002-henry-hub-fresh/backlog.json`
- Modify: `research/programmes/002-henry-hub-fresh/lines/005-fundamental-balance/line.json`

- [ ] Add the new HOLD entry and update feasibility decision counts consistently.
- [ ] Add a machine-readable re-entry trigger that first validates the capacity rule/GO criterion, then stages exact mapping and PIT target-period physical forecast work only as justified.
- [ ] Close the completed feasibility backlog item and replace it with named remedy work.
- [ ] Return the new feasibility identity and interpretation to Line 005 without changing rep-021 evidence.

### Task 3: Verify and deliver

**Files:**
- Modify generated `docs/reference/**` only through the repository documentation generator.
- Update `.work/changes/351-target-matched-physical-bottleneck-feasibility/{tasks.md,closeout.md}` with exact evidence.

- [ ] Generate documentation from canonical owners; do not hand-edit generated research pages.
- [ ] Run JSON/schema/documentation/governance verification on the exact working tree.
- [ ] Review the bounded diff for scientific-boundary, data-lineage, and documentation consistency.
- [ ] Commit, reconcile onto current remote `main`, publish a fresh PR, require exact-head GitHub Actions success, then merge through KIS.
- [ ] Close #351 only after the HOLD disposition and exact landed evidence are observable on GitHub; keep #348 open.
