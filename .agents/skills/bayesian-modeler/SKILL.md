---
name: bayesian-modeler
description: Use when a research question benefits from an explicit probabilistic model, prior information, posterior uncertainty, hierarchical structure, or posterior predictive checking.
---
# Bayesian Modeler

## Purpose
Build probabilistic models whose assumptions and uncertainty are explicit enough to criticize, simulate, and revise.

## Workflow
1. Define the generative story: observations, latent quantities, dependencies, and decision-relevant estimand.
2. Choose priors before posterior inspection; justify influential priors and plausible scales.
3. Run prior predictive checks to expose impossible scales or overly restrictive assumptions before fitting.
4. Fit the model and inspect convergence/diagnostics appropriate to the inference method; do not interpret an unstable posterior.
5. Run posterior predictive checks against features of the observed data the model should reproduce.
6. Compare alternatives using predictive performance and substantive adequacy, not parameter significance alone.
7. Test sensitivity to influential priors, likelihood choices, outliers, and model structure.

## Required Output
Generative assumptions; priors/rationale; inference method; diagnostics; posterior summaries; prior/posterior predictive checks; sensitivity results; limitations and decision interpretation.

## Guardrails
A posterior distribution does not rescue a misspecified likelihood or contaminated dataset. Distinguish credible intervals from frequentist confidence intervals. Avoid priors that simply encode the desired conclusion.
