# Research Methodology

Commodity uses a simple rule: decide what would count as evidence before looking at the protected result. The repository enforces the detailed rules; this document explains why they exist and how a human should understand the process.

## Why

Trading research is unusually easy to fool ourselves with. A result can look convincing after enough choices about dates, targets, models, filters, metrics, or subgroups. Our methodology separates discovery from confirmation so that promising ideas can be explored freely without presenting hindsight as proof.

The goal is not paperwork. It is to make every important result answerable later: where did the idea come from, what exactly did we test, what did we observe, what does it mean, and what changes in the bigger project?

## Two research modes

**Exploratory research** is for learning, diagnostics, feasibility work, debugging, and generating hypotheses. It can adapt as evidence appears, but it must be labelled exploratory and cannot by itself establish a confirmatory claim.

**Confirmatory research** is for testing a specific claim under a frozen plan. Before protected results are exposed, the hypothesis, data identity, evaluation design, success criteria, statistical treatment, and other required commitments are preregistered and frozen.

## Confirmatory lifecycle

```text
IDEA -> PREREGISTER -> FREEZE -> EXECUTE -> VERIFY -> INTERPRET -> DECIDE
```

1. An idea enters from earlier evidence, theory, market structure, exploratory work, or an explicit research question.
2. The confirmatory experiment is preregistered under the machine contract.
3. The commitment is frozen before protected results are exposed.
4. Execution produces evidence and results separately from the frozen commitment.
5. Repository checks verify identity, eligibility, accounting, and required methodology gates.
6. A human interprets the verified result in context.
7. The completed experiment writes one compact durable `record.json` linking the big-picture origin, exact frozen setup, outcome, interpretation, learning, programme consequence, decisions, recommendations, and open questions.
8. Decisions and unresolved follow-ups are projected into the programme decision register and research backlog, while the experiment record remains their source authority.

## What is immutable

The preregistration is the commitment. Once frozen, it is not edited to fit the result. Machine-generated evidence, results, and later human interpretation are separate records. If a design must change after the freeze, that becomes a new or explicitly governed successor experiment rather than a silent rewrite.

Completed V1/V2 work remains historical evidence under the rules that governed it at the time. We do not pretend old experiments were preregistered under a methodology that did not yet exist.

## Human and machine responsibilities

Humans decide what questions matter, explain the economic reasoning, interpret results, and decide what should happen next. Machines verify the mechanical promises: identities, freezes, eligibility, evidence levels, accounting, result bindings, and other encoded gates.

For the operator, every completed confirmatory experiment and major research-line update must produce a short plain-English executive summary with exactly these six headings: **Where this fits**, **Where the idea came from**, **What we tested**, **What we saw**, **What it means for the bigger picture**, and **What next**.

## Maintained statistical canon

The machine contracts implement a small maintained finance/econometrics canon rather than relying on ad-hoc significance checks. White's Reality Check is the default reference for best-of-many/data-snooping questions; Hansen's Superior Predictive Ability test is the higher-power challenger; the Model Confidence Set is used when the correct conclusion is a set of statistically indistinguishable models rather than a single winner. Harvey, Liu and Zhu motivate programme-level multiple-testing discipline when many candidate predictors have been tried. Newey-West/HAC and dependence-aware block/bootstrap methods are the reference tools for uncertainty when observations are serially dependent or horizons overlap.

These names are methodological references, not automatic proof. The exact procedure, candidate family, dependence assumptions, inputs, seeds, thresholds and resulting evidence identity must still be frozen or machine-recorded for the experiment that uses them.

## Authority

This document is explanatory, not a second rulebook. `config/research_methodology.json` activates the methodology. `contracts/` defines the machine-checkable records. `src/commodity/research_methodology.py` and CI enforce them. Confirmatory records live under `research/experiments/`; exploratory records live under `research/exploratory/`. Programme evidence, inference, and sealed-window registries remain owned by their assigned `config/` files in `AGENTS.md`.

Research evidence never grants trading permission. `config/policy.json` is the sole owner of execution authority.
