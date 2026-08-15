# Phase E V1 Closeout Preparation Plan

**Track:** E1 closeout preparation only
**Issue:** #21, dependent on #20
**Base:** `main` at `f754efe2b8080b52c2412fb611475e24e11633a2`
**State:** active preparation; final disposition is intentionally unset

## Purpose

Phase E defines how the V1 closeout will consume and judge final Phase D evidence before those results are known. Phase D owns tournament implementation, statistical conclusions, ablations, and artifact formats. Phase E consumes frozen Phase D evidence and must not reach backward to alter it.

The active operating structure is `C complete -> D primary active -> E secondary active`. Former Phase C capacity is reallocated rather than adding another concurrent V1 track: approximately 70-80% to Phase D empirical execution, 20-30% to Phase E preparation, and Phase C only for maintenance or defect response. This allocation is coordination guidance, not a Phase E authority to interrupt or modify Phase D.

E1 may establish the decision framework, traceability structure, authority-reconciliation backlog, risk/caveat structure, reproducibility checklist, and final verification/review procedure. E2 begins only after #20 satisfies its acceptance criteria and its evidence is frozen.

## Hard boundary

E1 must not select a V1 disposition, interpret preliminary Phase D runs as final evidence, alter model-selection criteria or robustness thresholds, modify the frozen dataset, change Phase D candidates or ablations, make a predictive-edge claim, change execution permissions, close #21, or start Kronos/V2/geographic expansion.

The only permitted eventual dispositions are:

- `V1 complete`: all #21 acceptance gates pass and no material unresolved caveat limits the scoped V1 system, interpretation, reproducibility, or evidence tier.
- `V1 complete with bounded caveats`: all #21 acceptance gates pass, but one or more explicitly bounded non-blocking caveats remain; those caveats must not invalidate Phase D evidence or silently promote the evidence tier.
- `V1 revise`: one or more #21 acceptance gates fail, including incomplete/non-reproducible Phase D evidence, unresolved stale authority at final closeout, failed exact-head verification/review, or incomplete traceability.

Predictive edge is not itself the system-completeness gate: a reproducible negative result can still support a complete research V1. No predictive-edge claim is allowed unless Phase D's predefined robustness criteria pass unchanged.

No disposition is selected in this document or its companion evidence index.

## Completion decision matrix

| Gate | Required evidence | E1 state | E2 closeout rule |
|---|---|---|---|
| E-AC1 reproducible evidence | Frozen Phase C dataset identity plus final Phase D tournament, ablation, predictions, evaluation, lineage, and reproducibility evidence | `waiting_on_phase_d` | Fail closed unless all required evidence is addressable and hash-bound. |
| E-AC2 authority reconciliation | Authority audit against `AGENTS.md`, authoritative config, current-state projections, and historical evidence | `audit_prepared` | Remove or supersede stale duplicated current-state claims without rewriting historical snapshots. |
| E-AC3 exact-head verification | Full verification and specialist review against the exact Phase E closeout head | `not_due` | A later change to the closeout head invalidates earlier final verification/review evidence. |
| E-AC4 traceability | #19 dataset evidence, #20 final evidence, #21 disposition, exact commits/PRs, evidence paths and hashes | `structure_ready` | Every final claim must trace to an authoritative owner or immutable evidence artifact. |

Two judgments remain separate throughout E2:

1. **V1 system completeness:** whether the scoped V1 research system and evidence contract are complete.
2. **Predictive edge:** whether Phase D demonstrates robust out-of-sample value under the predefined criteria.

System completeness never implies predictive edge. A negative predictive result may still support V1 system completeness if the experiment was complete, reproducible, and correctly fail-closed.

## Phase C input binding

Phase E accepts the Phase C handoff only from `phase-bc-empirical-closeout.json`. The admitted dataset is `us-ng-pit-0c0a39b36692`, freeze `b6aaf445500f2841`, dataset SHA-256 `0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f`, with 456 rows and 204 OOS rows.

Its audit verdict is `fit-with-caveats`, with `evaluation_only_market_evidence`; `research_evaluation_eligible=true` and `research_promotion_eligible=false`. E must preserve that distinction and may not upgrade this evidence tier.

## Phase D evidence handoff contract

E2 must consume final #20 evidence, not a preliminary worktree state. Phase D owns artifact naming and format; the Phase E index records the exact paths and hashes after D freezes them.

Required handoff evidence:

- Final #20 issue/PR/commit identity and the exact Phase D code/environment used for evaluation.
- Deterministic `plan_id` and `split_id`, chronological fold definitions, candidate order/configuration identities, ablation identities, and seeds.
- Complete candidate × ablation × seed coverage, including negative results; no winner-only evidence package is sufficient.
- Lineage records satisfying `src/commodity/phase_d_contract.py`: dataset ID/SHA/manifest SHA, feature-definition SHA, preprocessing SHA, experiment-config SHA, code commit, dependency-lock SHA, prediction SHA, and evaluation SHA.
- Return, direction-probability, and volatility/distribution evaluation required by #20, with calibration and regime/scenario analysis where applicable.
- Ablation effect sizes, uncertainty, and period/regime sensitivity for every material admitted V1 information family.
- Paired statistical comparisons using time-series-appropriate uncertainty and multiple-comparison control where material.
- Explicit predefined robustness-criteria results. A predictive-edge claim is inadmissible unless those criteria survive unchanged.
- Reproducibility evidence showing the final artifacts can be regenerated from the bound inputs/configuration/code/environment.
- A preserved negative-results inventory covering unsuccessful candidates, ablations, targets, regimes, and statistically unsupported gains.

E rejects a handoff if any required identity is missing, evidence only describes a selected winner, artifacts cannot be hash-bound, or the reported result depends on criteria changed after results were observed.

## Evidence and traceability index

`phase-e-evidence-index.json` is the machine-readable E1 scaffold. Known Phase C identities are bound now; all Phase D and final-closeout fields remain null/pending until E2. Null fields must never be filled from memory, preliminary output, or inferred filenames.

## Authority and stale-status audit

`AGENTS.md` remains the repository authority map. E1 found no reason to change ownership. This audit is bound to base commit `f754efe2b8080b52c2412fb611475e24e11633a2`. The empirical closeout inspected for comparison is `phase-bc-empirical-closeout.json` SHA-256 `8cd367eb8ceb242a1d2f9bbcedece8ae9825c8bda67e4a7c98d38fcec460a8e3`; it itself binds the inspected `config/data_sources.json` and `config/experiment.json` hashes below.

| Item | Bound audit finding | E2 treatment |
|---|---|---|
| `config/data_sources.json` SHA-256 `d368e7818d17f04686ba4f66ecd9e8a1a754b9c5cb2f92567bc842ab595e655d` | JSON pointers `/sources/eia_storage/status`, `/sources/nyiso_load_forecast/status`, `/sources/weather/status`, and `/sources/cftc_cot/acquisition_status` retain acquisition-pending wording while the empirical closeout records those V1 families ready with concrete source evidence. | Advisory only in E1. Reconcile from immutable acquisition/closeout evidence without changing evidence tier, provider policy, or the frozen dataset. |
| `config/experiment.json` SHA-256 `59711f48544995e2ca89d1c65c93c38540fb98f05954d46f9bf7666960aaef` | JSON pointers `/decision/disposition` and `/decision/rationale` retain the pre-#19 `repeat` / “full-V1 promotion still requires…” state. | Advisory only in E1. Reconcile after Phase D freezes its experiment evidence; do not change D criteria, candidates, ablations, splits, or thresholds. |
| `README.md` SHA-256 `0adfd11bb4123aef62023639ed2dc9aa4b12bf1041378d0067299c7f33ae7048` | The non-authoritative current-state projection still describes a generic PIT-core tournament rather than the admitted full-V1 / active Phase D state. | Refresh only after authoritative sources are reconciled. |
| `docs/data-manifest.md` SHA-256 `9f63d2aa8ceaf87d5a7931638e9e8909d4636f4770cfa716a40c734134c1d7d2` | The desired-data document repeats mutable acquisition-status prose such as pending weather/WNGSR/NYISO/CFTC capture even though it assigns operational status to `config/data_sources.json`. | Remove duplicated mutable status or replace it with references to the authoritative owner/evidence. |
| `phase-b-evidence.json`, `phase-c-evidence.json` | They contain blocked historical states superseded by the empirical closeout and are explicitly named there as preserved historical snapshots. | Preserve unchanged; do not “freshen” historical evidence. |
| external research reference | Its adoption note explicitly marks obsolete reconnaissance as non-authoritative. | Preserve as research input; never use it as closeout authority. |

E2 reconciliation order is: authoritative configuration first, then current-state summaries/projections, then final Phase E evidence and disposition. Historical audit artifacts are not rewritten to look current.

## Final closeout structure

The E2 closeout must state, separately and with evidence links: V1 system completeness; predictive-edge conclusion; negative results; bounded caveats; residual risks; reproducibility status; Phase C dataset identity; Phase D tournament/split/candidate evidence; ablation evidence; statistical/robustness evidence; and unchanged execution authority.

## E2 reproducibility checklist

- [ ] #20 acceptance criteria are complete and its final evidence is frozen.
- [ ] Phase D dataset identity exactly matches the admitted Phase C dataset and manifest lineage.
- [ ] Plan/split/candidate/ablation/seed identities are complete and deterministic.
- [ ] All required predictions/evaluations exist, are hash-bound, and include negative results.
- [ ] Return, direction, volatility/distribution, calibration/regime evidence is present as required by #20.
- [ ] Ablation effect sizes, uncertainty, sensitivity, and multiple-comparison treatment are present.
- [ ] Robustness thresholds are demonstrably pre-result and unchanged.
- [ ] Reproduction binds exact code commit, dependency lock, experiment config, features/preprocessing, dataset and artifacts.
- [ ] System-completeness and predictive-edge conclusions are stated independently.
- [ ] Caveats and residual risks are bounded; any failed #21 acceptance gate maps to `V1 revise`, while caveats are non-blocking only when every acceptance gate passes.
- [ ] `config/policy.json` remains the sole execution-permission owner and is unchanged by closeout.
- [ ] Kronos/V2 and geographic expansion remain outside V1 closeout.

## Final verification and review gate

On the exact E2 closeout head, run the live KIS-selected verification for the final diff and retain its exact-head evidence. The commands below are an E1 baseline/proposal, not a substitute for the controller's final verification selection.

Baseline exact-head commands from the Phase E worktree are:

```powershell
C:\Projects\commodity\.venv\Scripts\python.exe -m pytest -q
C:\Projects\commodity\.venv\Scripts\python.exe -m ruff check .
C:\Projects\commodity\.venv\Scripts\python.exe -c "import json, pathlib; [json.load(p.open(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.json')]"
git diff --check main...HEAD
git status --short --branch
```

Use the KIS-selected verification workflow for affected checks and retain its exact-head evidence. Add a diff-scoped credential scan and Markdown/reference checker when those are selected or available in the final repository toolchain.

Final specialist review must include the #21 skills relevant to the final diff: `model-evaluator`, `statistical-analyst`, `reproducibility-auditor`, `dataset-auditor`, and `time-series-research`, plus the controller-selected documentation/code review and verification skills. Reviews must reference the exact closeout head; stale-head approval is insufficient.

Project/work traceability must bind #19, #20, #21, the E1/E2 commits and PRs, final evidence paths/hashes, and review/verification evidence. #21 remains open unless the user or the governed completion workflow explicitly closes it.

## E2 entry gate

E2 may start only when Phase D #20 has final, reproducible evidence satisfying its acceptance criteria. Until then this plan and the companion index are preparation artifacts only and carry no V1 disposition or predictive-edge conclusion.
