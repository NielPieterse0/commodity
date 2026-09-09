# Physical Balance Predictive Bottleneck Delivery Record

## Scientific result

- Frozen A→B research OOS: 212 monthly origins, 2003-01 through 2020-08.
- A RMSE: `0.1353102836565950`; B RMSE: `0.13409938812858335`.
- Relative A→B RMSE improvement: `0.008949028080413979` (0.895%), below the frozen 1% survival threshold.
- Primary 3-month paired MBB RMSE-delta 95% CI: `[-0.0032323013640507586, 0.005231112063812548]`; 2,000 resamples, seed 348.
- Chronological thirds: `[-0.002102321974483262, 0.00006534152230185108, 0.006663616983633713]`; two are non-negative.
- A→B disposition: `INCONCLUSIVE_REALIZED_PHYSICAL_SIGNAL`.
- C was not scored because A→B did not survive. Therefore the run does not establish a PIT information/timing bottleneck.

## Scientific acceptance review

- `acceptance-review.json` preserves the frozen scores while comparing rep-021 against #348's actual requirements.
- Baseline A is not the required target-matched futures/market benchmark plus calibration; it is current spot plus seasonal terms.
- B uses final-vintage origin-period production/storage/consumption rather than realized target-period physical inputs.
- The target's calendar-average/futures-delivery equivalence is not demonstrated by the frozen artifacts.
- The pre-outcome capacity gate proceeded without establishing adequate detectability of the 1% material-effect threshold under plausible dependence.
- No #348 issue comment or issue-body language explicitly authorizes those narrower substitutions.
- Therefore rep-021 is valid narrower historical evidence but **does not complete #348's intended diagnostic**. The intended mapping remains open; no C run or model tournament is justified from this evidence.

## Integrity evidence

- Experiment-contract SHA-256: `9f5c8bb8edea548c7bbdbb40c8835660b92aa675cf5712e356fee344a95cd148`.
- Capacity-gate SHA-256: `144acda0402f0e6173586732e2ff067d260de92dc990d68c73a13a360750e7e5`.
- Result SHA-256: `7dccf398ac6857608d2e820f73371cd9d0cdf73c86e85ff2f3a17b7354ac4fb3`.
- Predictions SHA-256: `8da7a7f1e974cb1e1275233c0da6e240727edc023444d2dabf3f0737bca50cd2`.
- Result/prediction byte identities changed only to normalize CRLF to repository-canonical LF; scientific values and frozen scores were not changed.
- BHLR source ZIP SHA-256: `8bdc295d8a5e45079738abad8ea7eabe52062536e1b0a490a2af119d44b4c8f1`.
- Henry Hub non-revision audit max absolute difference: `0.0`.
- Existing sealed-window openings after execution: `0`; all remain ineligible.

## Engineering evidence

- Worktree environment rebuilt from Projects-local Python 3.13.7 after Python 3.12.11 `_ssl` was blocked by Windows Application Control; the failed venv was retained recoverably under `.work/scratch/348-venv-blocked-py312`.
- Canonical `scripts/verify.ps1`: passed; `496 passed, 7 skipped`; documentation, Python environment, research methodology, research memory, lint and whitespace gates all green.
- `pwsh -NoProfile -File scripts/change-workflow.ps1 check`: passed on the reconciled tree.
- Exact implementation/governance commit `e20c43bf836b57dab1cd87679926c295d1c6e8c3` received a complete independent code-quality review with no findings and no omitted files.
- Scientific acceptance/docs review remains required before PR publication.

## Delivery disposition

This change may land the frozen rep-021 evidence and its acceptance review, but GitHub issue #348 must remain open. The next scientific work is an unscored data-and-capacity feasibility assessment for the intended target-matched diagnostic under a new research identity.
