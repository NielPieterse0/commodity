# Commodity hypothesis experiment methodology

Issue: #249
Parent programme: #244
Status: implemented by issue #249 for adoption on merge. This methodology governs new/design-stage research after merge; it does not rewrite completed V1/V2 evidence and does not grant trading authority.

## Purpose and accepted source

This slice records the accepted methodology developed in the 2026-08-28/29 project discussion and then strengthened by independent review. The accepted final scope is the governing source; earlier drafts are historical context only.

The central lesson is that Commodity operates on low-signal financial history where independent observations are scarce. Methodological rigor is necessary, but rigor alone is not enough: the programme must also control statistical power, repeated reuse of the same history, data snooping, and the opportunity cost of spending scarce confirmation evidence.

Governing principle:

> **Optimize the research programme for information gained per scarce independent observation, not for the number of rigorously documented experiments completed.**

The methodology must be rigorous in evidence and deliberately lightweight in paperwork: store facts once, reference them elsewhere, and generate prose only when a human needs to read it.

## Big-picture research hierarchy

Every artifact declares a zoom level:
- **L0 â€” Mission:** can Commodity develop a defensible natural-gas forecasting/trading edge?
- **L1 â€” Research programme:** where might economically useful predictive information come from, and what does the accumulated evidence say?
- **L2 â€” Research line:** one mechanism/information family or economically distinct question.
- **L3 â€” Confirmatory experiment:** one frozen hypothesis and design.
- **L4 â€” Run/analysis:** one execution under an L3 contract.
- **L5 â€” Diagnostic/exploration:** bounded investigation that cannot silently become confirmatory evidence.

Evidence from L4/L5 never silently becomes an L0/L1 claim. Promotion upward is explicit and evidence-linked.
## Programme flow

The required research flow is:

1. **L0 big-picture objective.** Keep the North Star and major programme questions short and stable.
2. **L1 current evidence scan.** Refresh the best external academic/web evidence and combine it with accumulated internal evidence and the experiment/inference ledger.
3. **L1 feasibility map.** For candidate target Ã— horizon Ã— information-family combinations, estimate MEPI, available raw/effective information, detectable effect, expected signal-to-noise, costs and feasibility.
4. **L2 choose a research line.** Proceed only where external/internal evidence and feasibility make an informative experiment credible.
5. **L3 select one experimental slice.** State the parent question, the one uncertainty being reduced now, and what remains outside scope.
6. **Detailed slice-specific literature review.** Freeze the relevant mechanism, prior results, known pitfalls, expected magnitude and appropriate tests.
7. **Mechanism + H0/H1 + MEPI.** State the causal/economic rationale, formal hypotheses and practical effect threshold before protected results.
8. **Power/detectability gate.** If an economically/scientifically useful effect cannot be distinguished with useful power, redesign, hold or stop rather than consume a confirmatory experiment.
9. **Frozen design + preregistration SHA.** Bind the exact commitment before unblinding.
10. **Execution â†’ raw results â†’ E0â€“E6 classification.** Preserve machine evidence before narrative interpretation.
11. **Symmetric predeclared coherence/leakage audit.** Unexpectedly good and unexpectedly bad outcomes receive equivalent scrutiny.
12. **Programme-level multiple-testing interpretation.** Interpret the result in the context of prior attempts and touched historical windows.
13. **Update the L1 evidence map.** Record what changed and what remains uncertain.
14. **Advance / replicate / refine / branch / hold / stop.** End every slice with an explicit human disposition.

No new slice is chosen merely because it is technically interesting. It must trace to strong external evidence, a clear unresolved contradiction, or a high-value gap in the programme evidence map.
## Programme evidence scan and literature

The programme evidence scan answers **Where should we look?** It is broader and lighter than the slice literature review, which answers **Exactly how should we test this?**

The L1 scan should cover, when relevant: return/price predictability, volatility, storage/fundamentals, weather, term structure/carry, positioning/flows, macro and energy cross-market effects, seasonality/regimes, foundation/time-series models, alternative targets/horizons, transaction costs and economic viability.

Refresh the programme scan when a major research line is exhausted, several experiments materially change beliefs, important academic/model/data developments appear, or the programme is choosing its next major branch.

The methodological canon should emphasize the actual financial-research failure modes while retaining general reproducibility/preregistration literature as support. Core references include White (2000) Reality Check; Sullivan, Timmermann & White (1999); Hansen (2005) SPA; Hansen, Lunde & Nason (2011) Model Confidence Set; Harvey, Liu & Zhu (2016); Bailey & LÃ³pez de Prado on Deflated Sharpe Ratio/backtest overfitting; and Diebold's later clarification on forecast-comparison use. The slice review stores stable reference IDs rather than copying long literature summaries into every experiment.

## Feasibility gate: MEPI before design

A confirmatory experiment cannot reach frozen design until it passes:

**Economic/scientific relevance â†’ detectable effect â†’ available information â†’ go/no-go.**

**MEPI â€” Minimum Effect of Practical Importance** is an L1/L2 programme quantity, not free-form prose invented after results. Where appropriate distinguish:
- `scientific_mepi`: smallest forecasting/statistical effect worth learning about;
- `economic_mepi`: smallest effect plausibly useful after spread, slippage, fees, turnover and risk constraints.

MEPI must be derivable from declared inputs. A trading-usefulness claim requires an economic MEPI; a pure volatility/forecasting question may legitimately use a scientific MEPI first.

Power/detectability uses the actual experiment design. No universal sample-size table is hard-coded. Serial dependence, overlapping horizons, event clustering, regimes and conditional sampling must be reflected in the chosen method.
## Dependence and effective information

`effective_n` is never a hand-entered number that the verifier simply trusts. Record raw observation count, the dependence structure relevant to the chosen statistic, estimator/method, parameters such as bandwidth/block/window/cluster choices, computed effective information and sensitivity to reasonable choices.

Depending on the experiment this may use HAC/Neweyâ€“West logic, block bootstrap, clustered/event structure, overlapping-horizon treatment or another justified method. Not every statistic requires one universal scalar effective sample size; the contract may record a more appropriate dependence-adjusted information quantity.

If the power gate fails, the normal action is redesign/hold/stopâ€”not execution followed by an excuse that the null result was underpowered. Redesign may change target, horizon, conditioning, frequency, sample construction or information source, but that redesigned question receives a new identity.

## Programme-level inference and stopping

Internal cleanliness of one experiment does not erase programme-level data snooping. Repeatedly testing the same natural-gas history changes the evidential hurdle.

Maintain an **L1 experiment/inference ledger** containing at least:
- `programme_test_id`, `family_id`, `research_line_id` and inference-ledger entry ID;
- confirmatory versus exploratory status and prior exploratory ancestry;
- target/horizon, information family, model family and primary metric;
- historical development/research-OOS/evaluation windows touched;
- sealed-window usage and opening history;
- outcome and whether it influenced later design choices.

The programme then chooses appropriate family-level interpretationâ€”Reality Check, SPA, Model Confidence Set, false-discovery control or another justified procedureâ€”rather than pretending every issue is statistically independent.

Research lines also require stopping rules. Endless formally clean tweaking is not acceptable. A line can stop because accumulated negative evidence, poor feasible power, weak economic relevance, exhausted independent confirmation capacity, or low expected information value makes further work unattractive.
## Data hierarchy and sealed confirmation

Evidence is classified by data exposure:

**Development â†’ rolling research OOS â†’ sealed confirmation â†’ true forward evidence.**

Rolling historical OOS remains useful, but after repeated programme reuse it is partly research-trained and must not be described as pristine independent confirmation.

A sealed confirmation window has a declared identity, no exploratory access, explicit eligibility rules, limited openings and immutable results after opening. Account for:
- `sealed_window_id`;
- eligibility status;
- opening number and total permitted openings;
- metrics/artifacts exposed;
- whether the window remains usable for any later claim.

Exploratory L4/L5 work is mechanically prohibited from accessing sealed confirmation data. This is a hard failure, not a warning. Newly arriving forward evidence remains the strongest independence class.

## Confirmatory scientific artifact model

The accepted confirmatory model has **three scientific artifacts**, plus one generated operator view:

1. **`prereg.json` â€” human-authored immutable scientific commitment.**
2. **`results.json` â€” machine-authored execution/result evidence, immutable or append-only by defined event semantics.**
3. **`interpretation.md` â€” human scientific interpretation written only after results are known.**
4. **`executive-summary.md` â€” short generated/operator-facing projection; not a fourth source of scientific authority.**

Programme/hypothesis origin, evidence maps and literature snapshots live at L1/L2 and are referenced by stable IDs from the preregistration. They are not duplicated into a fourth mutable experiment record.

Reference direction is one-way: `results.json` points to the frozen preregistration identity; `interpretation.md` points to both preregistration and result identities. The preregistration never contains its own hash.
## Cryptographic preregistration binding

The preregistration receives a deterministic content identity from canonical serialization and SHA-256. A practical solo-researcher release binds that content to a pushed Git commit/tag and records commit SHA, tag, remote publication evidence and amendment lineage.

The claim is deliberately narrow: `preregistration_remote_bound: verified` means that exact commitment existed remotely no later than the recorded repository event. It does **not** mechanically prove that nobody viewed relevant data elsewhere first.

An amendment never edits a released preregistration. It creates a new preregistration identity that explicitly supersedes and references the old one.

## `freeze` is the central control

The eventual command `commodity experiment freeze EXP_ID` is the strongest gate and must, before execution:
1. validate the preregistration schema;
2. resolve current programme evidence and inference-ledger context;
3. recompute MEPI;
4. recompute power/detectability;
5. check raw/effective information;
6. check required benchmark declarations;
7. ensure symmetric coherence/anomaly triggers are declared;
8. allocate/register the programme inference entry;
9. validate sealed-window policy and eligibility;
10. refuse a confirmatory design that is not informative;
11. bind the commitment through commit/tag/remote publication;
12. record the resulting immutable identity.

The methodology therefore prevents a weak or mutable experiment before it runs rather than merely documenting problems afterwards.

## Verification truth classes

Machine output must distinguish what is actually proved from what is bounded checking or human judgment:

- **PROVEN** â€” deterministic/mechanical assertions: schema, hashes, immutable identities, frozen-prereg resolution, declared cardinality/row checks, benchmark output presence, test execution, MEPI/power arithmetic, sealed-window accounting, ledger membership and objectively derived evidence rules.
- **CHECKED** â€” known-risk checks with bounded coverage: timestamp/cutoff violations, obvious split contamination, known vintage mismatches, declared data-family leakage rules, unexpected join expansion. Wording must be honest, e.g. `No known PIT violations detected by the declared checks`, never `No leakage`.
- **RECORDED** â€” human/scientific judgment: mechanism plausibility, coherence interpretation, literature reconciliation, programme implication and recommended next action.

These truth classes belong in both machine-readable output and human-facing verification summaries.
## What `prereg.json` must freeze

The compact preregistration stores or references, without essay duplication:
- programme/research-line/slice IDs, evidence-scan and literature-snapshot refs;
- mechanism, H0/H1 and scientific/economic MEPI derivation;
- target, horizon and prediction/target/information-cutoff semantics;
- dataset/vintage identities, sample roles and historical windows;
- dependence-adjustment method and generated effective-information calculation;
- feature/preprocessing identities and permitted information families;
- model/config/checkpoint identities and training rules;
- primary/secondary metrics, uncertainty/inference procedure and statistical family;
- benchmarks, including required market-informed comparators where relevant;
- multiple-testing/inference-ledger identity;
- sealed-window policy;
- symmetric anomaly/coherence triggers;
- success/failure/inconclusive logic and permitted human decision enum;
- environment/reproduction tolerance policy.

The logical completeness checklist may contain many concepts, but the physical artifact should remain compact JSON/YAML with stable references. There is no mandatory 22-section essay.

## Benchmark rule

Where a liquid market-implied quantity is economically related to the target, it must normally appear as a benchmark or explanatory comparator. It must be described correctly, not automatically as an unbiased market forecast.

A comparator may therefore declare `type: market_implied` with an interpretation such as `tradable market comparator, not assumed unbiased expectation`. Depending on the target, suitable comparators may include futures/curve, current settlement, carry-implied relationships, market-implied volatility, seasonal/naive forecasts or simple econometric baselines.

## Domain-specific leakage controls

The preregistration selects a natural-gas/futures leakage checklist appropriate to the slice. Checks should cover declared PIT cutoffs, vintage timing, roll/contract identity, release calendars, overlapping horizons, event windows, joins/cardinality and any feature-family-specific availability rule.

Passing bounded checks is never reported as proof that leakage is impossible. Unknown leakage risk remains outside the machine's proof claim.
## Results, evidence levels and coherence audit

Results are recorded before narrative interpretation. Raw evidence comes first: sample/coverage, benchmark comparison, effect size, uncertainty, primary/secondary metrics, predeclared tests and relevant diagnostics.

Use **E0â€“E6**, never H0â€“H6, for evidence classification so evidence levels cannot be confused with statistical hypotheses:
- **E0 â€” no useful evidence:** no consistent useful benchmark-relative effect;
- **E1 â€” interesting signal:** direction/magnitude is potentially interesting but uncertainty is large;
- **E2 â€” statistical evidence:** predeclared inferential support exists;
- **E3 â€” robust forecasting evidence:** survives the preregistered OOS, regime/reasonable-loss and robustness requirements;
- **E4 â€” economically meaningful evidence:** magnitude plausibly matters after realistic costs/constraints;
- **E5 â€” replicated evidence:** finding survives genuinely independent data/time/regime or later forward evidence;
- **E6 â€” programme-level evidence:** strong enough, after programme-level inference controls, to materially change the overall thesis.

Evidence level is machine-derived wherever rules are objectively encoded. Humans cannot simply type a preferred E-level. Any scientific judgment not mechanically derivable remains RECORDED in interpretation.

Coherence/anomaly triggers are frozen before unblinding and are symmetric. Unexpectedly attractive results receive at least as much scrutiny as disappointing ones. Trigger classes include implausibly large benchmark improvement, discontinuity at a data boundary, sign contrary to a strong mechanism, concentration in a few observations, suspicious feature/target relationships and material changes after apparently irrelevant implementation edits.

The original result is preserved. A correction or changed design creates a new run/preregistration identity with lineage; it never overwrites the consumed evidence.

## Orthogonal experiment status

Never collapse three different questions into one status. Report separately:

`Method compliance: VERIFIED | FAILED | INCOMPLETE`

`Scientific evidence: E0 ... E6`

`Human disposition: ADVANCE | REPLICATE | REFINE | BRANCH | HOLD | STOP`

The verifier validates the decision enum but never chooses the human disposition. `refine` is the accepted term rather than `redesign`; `branch` remains available for a valid unexpected finding that creates a distinct research line.
## Environment identity and reproduction semantics

A future `reproduce` workflow distinguishes:
- **Logical reproduction:** same dataset/prediction/result identity within the declared numerical tolerance contract.
- **Byte reproduction:** exact bytes only where runtime, hardware and serialization make that meaningful.

Record lockfile/dependency identity, interpreter/runtime identity, model/checkpoint identity, hardware-sensitive facts where numerically relevant, and the declared tolerance policy. Bitwise equality is not treated as universal scientific proof.

## Two-tier documentation

Documentation is intentionally asymmetric:

**Confirmatory L3**
- compact full `prereg.json`;
- machine-authored `results.json`;
- concise `interpretation.md`;
- generated `executive-summary.md` for the operator.

**Exploratory/diagnostic L4/L5**
- very small structured run record containing run ID, parent question, purpose, inputs, change, result, promotion decision and optional `promoted_to` identity.

Exploration can be discarded, continued or promoted, but promotion creates a **new confirmatory preregistration**. Exploratory work is never retroactively relabeled as confirmatory evidence.

## Mandatory operator executive summary

Every confirmatory experiment and major research-line update produces one short plain-English summary, normally about 120â€“200 words, with exactly this narrative arc:

1. **Where this fits** â€” the bigger programme question and why it matters.
2. **Where the idea came from** â€” external research, prior internal evidence, market logic, contradiction or unresolved gap.
3. **What we tested** â€” the specific slice and hypothesis in plain English.
4. **What we saw** â€” the main result, benchmark comparison, and whether evidence was clear, weak or inconclusive.
5. **What it means for the bigger picture** â€” what programme evidence/confidence changed.
6. **What next** â€” the next action and why it is the highest-value step toward the objective.

No methodology dump, unexplained statistical jargon or long tables. Numbers appear only when they materially affect the decision. The summary clearly separates whether the experiment ran correctly, what the evidence showed, and what the human decision is.
## Staged automation target

The methodology is enforced by the #249 CLI/CI surface below, while remaining deliberately small and staged.

**Phase 1 â€” highest value**
- schemas for the accepted artifacts and programme references;
- `freeze`;
- `verify`;
- `verify-power`;
- preregistration Git/remote binding;
- basic CI enforcement.

**Phase 2**
- `verify-results`;
- domain-specific `audit-leakage`;
- symmetric coherence-trigger enforcement.

**Phase 3**
- programme inference ledger and family-level controls;
- sealed-window accounting/enforcement;
- multi-experiment statistical controls.

**Phase 4**
- `reproduce` with logical/byte semantics;
- richer generated reports;
- advanced automation.

The implemented CI surface is `experiment-schema`, `experiment-freeze-integrity`, `experiment-verification` and `programme-inference-integrity`. The CLI provides `experiment register`, `verify`, `verify-power`, `freeze`, `can-run`, `open-sealed`, `build-results`, `verify-results`, `audit-leakage`, `reproduce`, and `executive-summary`.

## Migration policy

Completed V1/V2 experiments remain legacy evidence under the contracts that governed them. Do not rewrite history or manufacture retrospective preregistration.

Frozen but unexecuted work may migrate only if protected outcome evidence has not been consumed. Migration creates a new preregistration identity with explicit inheritance/supersession lineage while preserving the legacy freeze as provenance.

New/design-stage hypotheses use the new methodology once this #249 implementation is independently reviewed and merged.

## Relationship to #244

#244 remains portfolio compression, not an experiment runner. It should merge/supersede/defer/reject overlapping ideas and retain only economically distinct research lines.

A surviving #244 idea cannot execute solely because portfolio closure is complete. It must pass the L1 evidence/feasibility map, L2 selection, detailed literature review, MEPI/power gate and candidate-specific freeze under this methodology.

This prevents the post-V2 backlog from becoming a feature zoo while preserving worthwhile ideas for disciplined later testing.

## Acceptance for this documentation slice

Before #249 is closed, the implementation must cover every accepted final-scope item above, pass focused and full-repository verification, preserve legacy V1/V2 evidence, pass independent review and exact-head CI, and be merged with Work/GitHub reconciliation. #244 remains the parent portfolio programme and cannot authorize empirical execution by itself.
