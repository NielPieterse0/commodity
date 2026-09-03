# Issue #271 — Front-curve spread feasibility and preregistration plan

## Purpose
Planning record only. Do not fit models, inspect protected outcomes, freeze a preregistration, or alter trading policy during this intake slice.

## Outcome
Decide whether one precisely defined Henry Hub front-curve target is statistically and operationally viable enough to justify confirmatory research, and leave a fully specified preregistration-ready design if it passes.

## Research question
Can information available before decision time predict a predeclared change in the Henry Hub front curve better than a simple baseline by an economically meaningful amount?

## Primary target direction
Start with one target family only: M1-M2 calendar-spread change / front-curve slope change. Final target units, horizon, observation timestamp, decision cutoff, and roll convention must be fixed before any outcome-driven comparison.

## Core constraints
- Point-in-time contract identity and expiry/roll handling are mandatory.
- No future-active-contract knowledge or retrospective roll selection.
- No broad spread-target tournament or post-hoc target redefinition.
- Effective sample size and dependence must drive feasibility, not raw row count.
- A MEPI and explicit stop rule must exist before model evaluation.
## Planned execution sequence
1. Define the target/use contract: population, row grain, contract keys, target formula, horizon, timestamps, decision cutoff, units, calendar and roll policy.
2. Build or identify the canonical Databento source contract needed for M1/M2 observations and preserve source/dataset identities.
3. Prove roll safety, expiry handling, join cardinality, missingness provenance, and absence of future contract-selection knowledge.
4. Measure usable history, effective N, dependence, season/regime concentration and any structural gaps before predictive modelling.
5. Predeclare the MEPI, power target, uncertainty method, baseline, primary metric and feasibility threshold.
6. Apply the feasibility gate. Stop or defer if the design cannot detect an economically useful effect with credible power.
7. If feasible, fully specify the confirmatory experiment: immutable dataset/feature/split identities, baseline, minimal model ladder, seed/repeat policy, evaluation protocol and leakage checks.
8. Register programme-inference implications and any sealed-window requirements required by the current methodology.
9. Freeze the preregistration through the existing #249 gate only after all design choices are resolved and before protected outcomes are accessed.
10. Hand off a separate execution slice; this planning/intake work must not execute the empirical experiment.

## Promotion criteria
Proceed to confirmatory execution only if target construction is PIT-safe and reproducible, effective sample size is adequate, the predefined MEPI is statistically detectable under the chosen protocol, and no unresolved roll/expiry/data-rights issue can change the target meaning.

## Kill / defer criteria
Kill or defer if apparent target variation is primarily roll mechanics, effective N is too small, power is inadequate against the MEPI, the target requires repeated redefinition, canonical history is incomplete for the declared contract, or protected evidence would need to be inspected to finish the design.

## Later model ladder
If the feasibility gate passes, constrain later modelling to: declared persistence/seasonal baseline → regularized linear model → one tree booster. Additional families require a new governed rationale rather than opportunistic expansion.

## Intake state
GitHub issue: `#271`.
Implementation and empirical execution are intentionally not started in this slice.
