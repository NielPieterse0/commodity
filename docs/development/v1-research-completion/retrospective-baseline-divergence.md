# V0/V1 Retrospective Metric Reconstruction

**Issue:** #78

**Scope:** Agent 2 retrospective evidence only

**Authority revision inspected:** `eebc32da79f216d0de80a322d597c04d298d2d43`

## Finding

The committed history does not show a stable forecasting edge that later degraded. It shows:

1. provider-boundary screening: **no next-session return edge**;
2. noncanonical PIT-core tournament smoke: **tiny apparent edge**;
3. full-V1 Phase D: **no edge**, reproducibly;
4. post-Phase-E hardening: **same Phase D result reproduced**.

The PIT-core smoke is therefore the anomalous positive checkpoint, not an established prior research baseline. Its own evidence labels it pipeline-only, incomplete, noncanonical, and ineligible for research promotion.

No committed numeric empirical result predating August 13, 2026 was found in repository history. Earlier bootstrap/configuration history therefore cannot be backfilled with invented performance values.

## Preserved checkpoints

| Checkpoint | Evidence status | Data / OOS | Return RMSE | Historical interpretation |
|---|---|---|---|---|
| Provider-boundary screen | Screening only | 500 sessions; 290 OOS | zero `0.045274`; price-only `0.045928`; richer variants worse | No return edge before the PIT smoke. |
| PIT-core tournament smoke | Pipeline only | 2,898 rows; 2,142 OOS; 2015-02-02--2026-08-10 | naive `0.04604044`; Ridge `0.04598505`; HistGB `0.04579709` | Only preserved checkpoint with models slightly ahead of naive. |
| Full-V1 Phase B/C freeze | Fit-with-caveats | 456 rows; 204 OOS; 2024-09-12--2026-08-11 | No model metrics preserved | Methodology/comparability break before Phase D. |
| Full-V1 Phase D | Reproducible evaluation only | same 456-row freeze; 204 OOS | naive `0.04532306`; Ridge `0.05588330`; HistGB `0.04650734` | Both learned models worse than naive; `no_robust_edge`. |
| #77 locked reproduction | Reproduction, not a new checkpoint | same frozen V1 evidence | Phase D values preserved | Correctness hardening did not change the negative result. |

## Exact divergence statement

The **last preserved checkpoint with an apparent model edge** is the PIT-core smoke introduced by `e2da35e` and landed through PR #14 (`971ccd3`). HistGB beat naive by only `0.00024335` RMSE, about `0.529%`; Ridge beat naive by `0.00005539` RMSE, about `0.120%`.

The **first preserved later model checkpoint without that edge** is final Phase D, landed in PR #71 (`9bdcd4e`). HistGB was worse than naive by `0.00118428` RMSE (`-2.613%` improvement), and Ridge was worse by `0.01056024` RMSE.

However, this is **not a like-for-like performance regression**. The first comparability-changing repository edits occurred immediately after the smoke in Phase 0 (`7b8546a`): initial training changed from 756 to 252 rows, the naive baseline identity and bootstrap significance were formalized, and a canonical-contract dataset route was introduced. No performance rerun was preserved there.

Phase A (`2b301e5`) then made the material representation/target break: selected-contract settlement semantics, within-contract next-session returns, prohibited cross-contract returns, and M1-M4 market structure. Again, no model rerun was preserved. The Phase B/C empirical closeout later froze the complete 456-row full-V1 dataset, still without a model result.

Therefore the **first observed loss** is Phase D, but the exact point inside the Phase 0 -> Phase A -> full-V1 transition where the smoke ranking would have flipped is not observable from history.

## Comparability break

The PIT smoke used a noncanonical bootstrap market frame. Its target was the next-row log return of that frame's `close`, with market/calendar features only. It used 2,898 rows, 756 initial training rows, and 2,142 OOS observations.

By Phase D the governed dataset instead used provider-neutral futures contracts, the selected-contract path, settlement-based within-contract returns, explicit roll semantics, and prohibited cross-contract returns. The frozen dataset had 456 rows, 252 initial training rows, and 204 OOS observations.

It also added all required V1 information families:

- market structure;
- storage;
- weather;
- power;
- positioning;
- market and calendar/seasonality.

The evidence tier moved from incomplete `research_pit`/`pit_core` pipeline evidence to `evaluation_pit`/`full_v1` research-evaluation evidence with point-in-time audits and complete joins.

## Attribution supported by history

| Candidate explanation | Support | Evidence-backed conclusion |
|---|---|---|
| Changed data / target semantics | Strong | Market representation and return construction changed materially before Phase D. |
| Stricter PIT / leakage treatment | Strong | Full-V1 added contract validation, availability checks, exogenous audits, completeness and fail-closed eligibility. |
| Different train / OOS windows | Strong | OOS fell from 2,142 rows to 204; initial training changed from 756 to 252. |
| Changed baseline definition | Not material | Both checkpoints use the same zero-return naive economic benchmark; Phase D only made its identity explicit. |
| Changed feature set | Strong | The smoke omitted five required families; full V1 included all seven configured families. |
| Model retuning | Not supported | Ridge stayed at `alpha=10`; HistGB stayed at learning rate `0.05`, 20 iterations and 15 leaves. |
| Stricter statistical protocol | Strong for the edge claim | Phase D added uncertainty, multiple-testing, period and regime gates, but these cannot themselves reverse raw RMSE ranking. |
| Software/environment defect | Not supported by preserved evidence | #77 fixed reproduction/governance defects, then the locked environment reproduced all 24 Phase D prediction hashes and preserved `no_robust_edge`. |

The history therefore supports a **non-comparable transition from a tiny pipeline-only advantage to a negative governed evaluation**, not a demonstrated software regression and not proof that stricter methodology caused a genuine loss of predictive advantage. A legitimate loss remains plausible, but unproven; history cannot assign causal shares among representation, sample-window and feature-set changes.

## What remains unidentifiable

A controlled bridge experiment was not preserved. There is no historical sequence that holds the dataset fixed while changing one of the following at a time:

- bootstrap close returns -> selected-contract settlement returns;
- long bootstrap history -> two-year governed market window;
- market/calendar-only -> full-V1 features;
- smoke ranking -> full Phase-D evaluation protocol.

Running such experiments now would create new empirical evidence rather than reconstruct history and is outside this Agent 2 scope.

## Handoff boundary

This reconstruction is evidence input only. Agent 1 owns the authoritative longitudinal metrics schema, ledger, comparability rules and regression alarms. Agent 3 owns per-fold loss, outlier concentration, prediction dispersion and statistical decomposition. This slice changes none of those surfaces and performs no V2 experimentation.
