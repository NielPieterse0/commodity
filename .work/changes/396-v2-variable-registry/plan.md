# V2 Variable Registry Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** Register the authoritative V2 variable search space for Programme #393, restore deterministic generated documentation required by CI, and land issue #396 without starting optimization or opening any protected evidence boundary.

**Architecture:** Describe only the smallest repository implementation needed. For research-originated work, reference the L3 authority instead of reproducing scientific reasoning.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific/requirements authority; implementation planning cannot redefine it.
- Use focused tests/verification during development and let the live KIS lifecycle decide what evidence is missing or stale.
- Do not rerun valid implementation evidence merely because the workflow was interrupted.

### Task 1: Restore the registered V2 search-space artifact

**Files:** `config/v2_variable_registry.json`

- [x] Bind implementation to issue #396 and the existing PR #423 registry.
- [x] Restore the registry without changing its registered variable/search semantics.
- [x] Confirm the registry remains registration-only and preserves protected evidence boundaries.

### Task 2: Reconcile deterministic documentation

**Files:** `docs/reference/config/v2_variable_registry.md`, `docs/reference/README.md`

- [x] Run the repository documentation generator from the worktree-local `.venv`.
- [x] Confirm the missing generated config page is produced and the reference index is updated.
- [x] Run generated-document rule verification.

### Task 3: Verify and land through KIS

- [ ] Run current-tree repository/KIS verification selected for this bounded change.
- [ ] Review the exact diff for scope and protected-boundary regressions.
- [ ] Commit and reconcile the exact verified tree onto PR #423 through the governed Git/GitHub path.
- [ ] Require exact-head GitHub Actions success before merge and closeout.
