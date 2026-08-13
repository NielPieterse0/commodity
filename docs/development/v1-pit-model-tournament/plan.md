# V1 PIT Dataset + Model Tournament Implementation Plan

> Required implementation discipline: isolated worktree, test-first behavior changes, focused verification, full verification, review, PR, merge, cleanup.

**Goal:** make a leakage-safe PIT core dataset and reproducible baseline tournament executable without weakening existing evidence gates.

**Architecture:** add one dataset module responsible for supervised-frame construction, PIT joins, completeness, and deterministic manifest identity; add one tournament module responsible only for common-protocol model comparison. Reuse existing availability, model, evaluation, provenance, configuration, and CLI boundaries.

**Tech stack:** Python 3.11+, pandas, NumPy, scikit-learn, pytest, Ruff.

## Global constraints

- No random/shuffled time-series evaluation.
- `screening` evidence is never accepted as a PIT tournament input.
- No package additions.
- No provider-selection or trading-authority changes.
- Data/results remain under ignored `data/processed/` and `artifacts/runs/`.

### Task 1 — Dataset contract

**Files:** create `src/commodity/research_dataset.py`; create `tests/test_research_dataset.py`; update `config/experiment.json`.

- [ ] Add failing tests for deterministic identity, screening rejection, future-safe PIT joins, and fail-closed full-V1 completeness.
- [ ] Run focused tests and confirm failures are caused by missing dataset behavior.
- [ ] Implement the minimal dataset builder/manifest contract.
- [ ] Run focused tests to green.

### Task 2 — Tournament ladder

**Files:** create `src/commodity/tournament.py`; create `tests/test_tournament.py`; update `src/commodity/models.py` and `config/models.json`.- [ ] Add failing tests for common split protocol, ranking, configured model discovery, and the gradient-boosting challenger.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add the bounded sklearn challenger and tournament orchestration.
- [ ] Run focused tests to green.

### Task 3 — CLI and experiment artifacts

**Files:** update `src/commodity/cli.py`; update CLI/pipeline tests.

- [ ] Add failing CLI tests for `freeze-v1-dataset` and `run-tournament`.
- [ ] Implement dataset CSV/manifest output and tournament summary/model artifact output.
- [ ] Smoke-run the commands against the local bootstrap market file into ignored output directories.
- [ ] Validate artifact hashes and chronological coverage.

### Task 4 — Authority projections and closeout

**Files:** update `config/experiment.json` and `config/models.json` first; update `README.md` / `docs/roadmap.md` only where projections materially changed; add `review.md` and `evidence.json`.

- [ ] Run focused tests, full pytest, Ruff, and local change review.
- [ ] Close material review findings and record bounded verification evidence.
- [ ] Deliver through the repository PR workflow linked to issue #13.
- [ ] Leave GitHub Project final status for operator closeout as requested.
