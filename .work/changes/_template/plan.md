# {{CHANGE_NAME}} Implementation Plan

> Execute through the live KIS lifecycle and keep `scope.json` current.

**Goal:** {{OUTCOME}}

**Architecture:** Describe only the smallest repository implementation needed. For research-originated work, reference the L3 authority instead of reproducing scientific reasoning.

## Global constraints

- Stay inside `scope.json`.
- Preserve upstream scientific/requirements authority; implementation planning cannot redefine it.
- Use focused tests/verification during development and let the live KIS lifecycle decide what evidence is missing or stale.
- Do not rerun valid implementation evidence merely because the workflow was interrupted.

### Task 1: Map authority to implementation

**Files:**
- Modify:
- Test:

- [ ] Identify the exact authoritative requirement/research references.
- [ ] Write failing acceptance evidence for the repository behavior.
- [ ] Implement the smallest complete change.
- [ ] Run affected checks and resolve review findings.
- [ ] Return to upstream research/design authority if implementation exposes a material scientific/design change.
