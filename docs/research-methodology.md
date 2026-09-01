# Research Methodology

Commodity uses a simple rule: decide what would count as evidence before looking at the protected result. The repository enforces the detailed rules; this document explains why they exist and how a human should understand the process.

## Why

Trading research is unusually easy to fool ourselves with. A result can look convincing after enough choices about dates, targets, models, filters, metrics, or subgroups. Our methodology separates discovery from confirmation so that promising ideas can be explored freely without presenting hindsight as proof.

The goal is not paperwork. It is to make every important result answerable later: where did the idea come from, what exactly did we test, what did we observe, what does it mean, and what changes in the bigger project?

## Two research modes

**Exploratory research** is for learning, diagnostics, feasibility work, debugging, and generating hypotheses. It can adapt as evidence appears, but it must be labelled exploratory and cannot by itself establish a confirmatory claim.

**Confirmatory research** is for testing a specific claim under a frozen plan. Before protected results are exposed, the hypothesis, data identity, evaluation design, success criteria, statistical treatment, and other required commitments are preregistered and frozen.

## Governed research lifecycle

Every new governed research run follows the same 15-stage path, whether it stops during exploration or reaches confirmation:

1. **Helicopter view** — restate the programme's current bigger picture before choosing a local question.
2. **Gap** — identify the specific uncertainty that matters to a programme decision.
3. **Evidence-led zoom-in** — explain why this slice is selected from prior evidence rather than novelty.
4. **Quality literature** — capture reputable primary or high-quality sources and map each material claim to them.
5. **Mechanism** — state the economic or market mechanism being tested.
6. **Hypothesis** — state the falsifiable null and alternative.
7. **Expected and disconfirming observations** — derive both from the literature before looking at the relevant result.
8. **Feasibility** — test data fitness, dependence, effective information, MEPI, power, and other prerequisites.
9. **Preregister and freeze if applicable** — only a GO design may advance to protected confirmation.
10. **Execute** — run exactly the governed exploratory or frozen confirmatory design.
11. **Verify** — check identities, leakage controls, eligibility, accounting, and reproduction requirements.
12. **Compare observed versus expected** — explicitly record where the result agrees or conflicts with the prior expectations and disconfirmers.
13. **External post-result triangulation** — perform an independent literature check after the result rather than reusing the preregistration snapshot.
14. **Programme conclusion** — state what changes, or does not change, in the bigger picture.
15. **Active revisit triggers** — any HOLD/DEFER must have machine-testable conditions and evaluation history.

A completed confirmatory experiment still writes one compact durable `record.json` linking the big-picture origin, frozen setup, result, interpretation, programme consequence, decisions, recommendations, and open questions. Decisions and unresolved follow-ups are projections from that record, not competing authorities.

## What is immutable

The preregistration is the commitment. Once frozen, it is not edited to fit the result. Machine-generated evidence, results, and later human interpretation are separate records. If a design must change after the freeze, that becomes a new or explicitly governed successor experiment rather than a silent rewrite.

Completed V1/V2 work remains historical evidence under the rules that governed it at the time. We do not pretend old experiments were preregistered under a methodology that did not yet exist. The original #271 exploratory record is likewise retained unchanged as legacy evidence; its #273 conformance run is a separate successor record.

## HOLD and DEFER are active states

A scientific HOLD or DEFER is not a prose reminder. `config/research_revisit_triggers.json` owns executable trigger conditions, evidence inputs, thresholds, and evaluation history. Governed research preflight re-evaluates active triggers. If a condition becomes satisfied, the historical experiment remains immutable and the trigger must release or create a traceable successor before research proceeds.

## Human and machine responsibilities

Humans decide what questions matter, explain the economic reasoning, interpret results, and decide what should happen next. Machines verify the mechanical promises: identities, freezes, eligibility, evidence levels, accounting, result bindings, and other encoded gates.

For the operator, every completed confirmatory experiment and major research-line update must produce a short plain-English executive summary with exactly these six headings: **Where this fits**, **Where the idea came from**, **What we tested**, **What we saw**, **What it means for the bigger picture**, and **What next**.

## Maintained statistical canon

The machine contracts implement a small maintained finance/econometrics canon rather than relying on ad-hoc significance checks. White's Reality Check is the default reference for best-of-many/data-snooping questions; Hansen's Superior Predictive Ability test is the higher-power challenger; the Model Confidence Set is used when the correct conclusion is a set of statistically indistinguishable models rather than a single winner. Harvey, Liu and Zhu motivate programme-level multiple-testing discipline when many candidate predictors have been tried. Newey-West/HAC and dependence-aware block/bootstrap methods are the reference tools for uncertainty when observations are serially dependent or horizons overlap.

These names are methodological references, not automatic proof. The exact procedure, candidate family, dependence assumptions, inputs, seeds, thresholds and resulting evidence identity must still be frozen or machine-recorded for the experiment that uses them.

## Authority

This document is explanatory, not a second rulebook. `config/research_methodology.json` activates the methodology. `contracts/` defines the machine-checkable records. `src/commodity/research_methodology.py` and CI enforce them. Confirmatory records live under `research/experiments/`; exploratory records live under `research/exploratory/`. Programme evidence, inference, and sealed-window registries remain owned by their assigned `config/` files in `AGENTS.md`.

Research evidence never grants trading permission. `config/policy.json` is the sole owner of execution authority.
