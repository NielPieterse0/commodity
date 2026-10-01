# Historical Evidence Recombination Joint Advantage Discovery Implementation Plan

> **Execution:** native in this governed worktree; preserve exact trial/evidence identities and use TDD for implementation slices.

**Goal:** Build a complete historical evidence graph, freeze a joint-search contract from it, then execute broad cross-variable development search until a robust candidate is found or the declared search budget is exhausted.

**Architecture:** Separate repository-history indexing from empirical search. The indexer reads durable research/change artifacts and emits deterministic raw evidence plus curated priority clues. A later #459 runner consumes only the frozen map/preregistration and existing PIT-safe feature/replay machinery.

## Global constraints

- Development data only through 2022-12-31.
- Protected confirmation, paper, SIM and LIVE remain sealed.
- Historical dispositions are immutable inputs, not labels to reinterpret.
- Every empirical configuration must have an immutable identity and ledger row.
- Search must include cross-variable interactions rather than serial one-family optimization.

### Task 1: Deterministic repository-wide advantage map

**Files:**
- Create: `scripts/research/build_issue459_advantage_map.py`
- Create: `tests/test_issue459_advantage_map.py`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-advantage-map-v1.json`

- [ ] Write tests for disposition classification, raw-source traceability, deterministic ordering and critical retained clues.
- [ ] Implement recursive structured-evidence extraction across Programmes 001-004 and governed change closeouts.
- [ ] Add curated priority clues with source/object-path references and exact historical metrics.
- [ ] Generate the map and verify repeated generation is byte-identical.
### Task 2: Freeze joint-search preregistration

**Files:**
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-prereg-v1.json`
- Test: `tests/test_issue459_advantage_map.py`

- [ ] Derive admissible search lanes from the map without reading protected evidence.
- [ ] Freeze side-specific specialist roles, retained V2 signal roles, lifecycle/risk/execution dimensions, economic hurdles and pruning rules.
- [ ] Freeze effective-sample, stability, cost and complexity gates before scoring.

### Task 3: Implement joint-search primitives

**Files:**
- Create: `src/commodity/v2_joint_advantage.py`
- Create: `tests/test_v2_joint_advantage.py`

- [ ] Implement immutable configuration identities and cross-product/pruned candidate generation.
- [ ] Implement side-conditional specialist modifiers, lifecycle variants and state-dependent risk/sizing interfaces.
- [ ] Implement chronological selection and executed-trade effective-sample accounting using existing PIT-safe replay semantics.

### Task 4: Broad discovery runner and progressive pruning

**Files:**
- Create: `scripts/research/run_issue459_joint_advantage.py`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-trials-v1.jsonl`
- Create: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-result-v1.json`

- [ ] Run no-scoring source/preflight gates.
- [ ] Execute cheap broad screens across thousands of structured combinations.
- [ ] Prune dominated, sparse and unstable regions; allocate heavier replay/model work only to surviving islands.
- [ ] Re-evaluate finalists across chronological outers, costs and risk perturbations with ablations.
- [ ] Freeze a candidate only if material economics, effective sample and stability gates all pass.

### Task 5: Governed verification and landing

- [ ] Run focused tests, Ruff/compile and deterministic evidence checks throughout.
- [ ] Run `scripts/change-workflow.ps1 check`, KIS review and canonical repository verification.
- [ ] Commit/PR, require exact-head GitHub Actions, merge and reconcile the programme evidence.