# Phase 0 Quantitative Research Knowledge Router Plan

**Goal:** Turn the approved quantitative-research corpus into one Commodity-owned, machine-readable authority router with executable playbooks and generated human guidance.

**Authority:** GitHub issue #354 and parent #353 define the outcome. `AGENTS.md` controls repository ownership and forbids a repository-local reusable skill catalogue, so the approved design uses canonical configuration plus generated documentation instead of `commodity-knowledge/SKILL.md`.

## Global constraints

- Do not open, score, inspect, or use protected confirmation outcomes.
- Do not copy copyrighted book prose; record source metadata, distilled principles, Commodity rules, and stable citations only.
- Keep existing Commodity methodology authoritative; map coverage and gaps rather than duplicating it.
- Use the router as repository knowledge, while reusable procedural skills continue to come from live KIS.
- Generate all `docs/**/*.md` through `scripts/docs/generate_docs.py`.

### Task 1: Define the router contract with RED tests

**Files:** `contracts/quantitative_research_knowledge.schema.json`, `tests/repository/test_quantitative_research_knowledge.py`

- [x] Require source metadata, routing domains, executable playbooks, methodology map, legacy inputs, copyright rules and protected-confirmation boundary.
- [x] Require the approved core-source routing and tier-2 DDIA boundary.
- [x] Confirm tests fail because the canonical router does not yet exist.

### Task 2: Implement the canonical knowledge router
**Files:** `config/quantitative_research_knowledge.json`, `AGENTS.md`

- [x] Record ML4T, FPP3, Fundamentals of Data Engineering, Designing Machine Learning Systems and tier-2 DDIA with access/license notes.
- [x] Encode authority routing for data engineering, forecasting, financial ML, leakage, tuning, backtesting and production monitoring.
- [x] Encode seven Commodity playbooks as ordered rules with source and canonical-owner references.
- [x] Map current Commodity controls to source authority, legacy issue evidence and explicit missing controls with later-phase targets.
- [x] Integrate the router into normal agent guidance without creating a local `SKILL.md`.

### Task 3: Make the router generated and verifiable

**Files:** `config/documentation.json`, `scripts/docs/generate_docs.py`, `scripts/checks/check_quantitative_research_knowledge.py`, `config/rule_verification.json`

- [x] Generate `docs/quantitative-research-knowledge.md` and the normal config/schema reference projections.
- [x] Add deterministic validation for router/schema/routing/playbook invariants and register it in repository verification.
- [x] Run the focused tests and generated-doc drift check.

### Task 4: Verify, review and land

- [x] Run affected verification and full `scripts/verify.ps1` from the worktree-local environment.
- [x] Resolve specialist review findings and rerun invalidated evidence.
- [ ] Commit, prepare the exact PR, require exact-head CI, merge, reconcile Work/docs and clean the worktree through KIS.
- [ ] Leave #348/#351 and other distinct science untouched; advance Programme 003 to #355 only after #354 is Done.
