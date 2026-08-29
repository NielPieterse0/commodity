# Commodity Hypothesis Experiment Methodology â€” Future Implementation Plan

> **Implementation status:** operator authorization was granted on 2026-08-29. Issue #249 is the hard gate before further empirical experiments; implementation remains subject to repository verification, independent review, exact-head CI, merge, and Work/GitHub reconciliation.

**Goal:** Implement the accepted Commodity research methodology so future confirmatory experiments are informative before they are frozen, immutable after release, machine-verifiable without overstated claims, programme-aware under repeated testing, and concise for the operator.

**Architecture:** Keep programme-level evidence/feasibility and inference accounting separate from experiment artifacts. A confirmatory experiment uses three scientific artifacts (`prereg.json`, `results.json`, `interpretation.md`) plus a generated `executive-summary.md`. `freeze` is the central fail-closed gate. Exploratory work stays lightweight and cannot access sealed confirmation evidence.

**Spec:** `docs/development/249-hypothesis-experiment-methodology/design.md`

## Global constraints

- Final accepted scope in #249/design is authoritative over earlier drafts.
- No completed V1/V2 evidence may be rewritten or retrospectively preregistered.
- MEPI and power/detectability are preconditions to confirmatory freeze, not post-result explanations.
- Programme-level reuse of historical evidence must be accounted for through the inference ledger.
- Sealed confirmation evidence is scarce and inaccessible to exploratory workflows.
- Machine claims use PROVEN/CHECKED/RECORDED semantics; bounded leakage checks never claim universal proof.
- Evidence uses E0â€“E6; H0/H1 are reserved for statistical hypotheses.
- Human disposition enum is exactly `advance | replicate | refine | branch | hold | stop`.
- Method compliance, scientific evidence and human disposition remain orthogonal.
- Operator-facing summaries are short, plain English and big-picture-first/big-picture-last.
- Trading authority remains owned by `config/policy.json`.
- Operator authorization for #249 implementation was granted on 2026-08-29; no empirical experiment may resume until this implementation is merged and operational.
## Planned authority/artifact structure

Exact paths may be refined by the later governed change after impact analysis, but responsibilities must remain separate:

- programme evidence map â€” L1 current knowledge, confidence, best evidence, biggest gap and next high-value test;
- programme inference ledger â€” every confirmatory attempt, family/research-line identities, historical windows touched, sealed-window use and design ancestry;
- literature/reference registry â€” stable reference IDs used by evidence scans and preregistrations;
- preregistration schema â€” compact immutable L3 commitment;
- results schema â€” machine-authored L4 evidence and derived verification/evidence state;
- interpretation template/contract â€” RECORDED human scientific judgment after results;
- exploratory run schema â€” lightweight L4/L5 diagnostic record;
- sealed-window registry/accounting â€” eligibility, openings and remaining claim capacity;
- CLI/service layer â€” feasibility, freeze, verify, result verification, leakage audit and reproduction;
- generated executive summary â€” non-authoritative operator view.

Do not create a separate mutable `hypothesis.json` inside every experiment merely to repeat programme context. Hypothesis origin, evidence scan and literature live at L1/L2 and are referenced from `prereg.json`.

## Phase 1 â€” feasibility, immutable freeze and basic verification

### Task 1: Define programme evidence and feasibility contracts

- [x] Define the compact L1 evidence-map structure and refresh triggers.
- [x] Define MEPI records with `scientific_mepi` and optional/required `economic_mepi` derivations.
- [x] Define dependence-adjustment output: raw n, method/estimator, parameters, generated effective-information quantity and sensitivity.
- [x] Define the go/no-go feasibility result so a failed power gate cannot silently proceed to confirmatory freeze.
- [x] Add tests proving MEPI/effective information are generated from declared inputs rather than trusted hand-entered outputs.

### Task 2: Define the three confirmatory scientific contracts

- [x] Create compact schemas for `prereg.json` and `results.json`; define the required structured metadata for `interpretation.md` without turning it into a second numerical authority.
- [x] Ensure preregistration cannot contain result/evidence fields and never contains its own hash.
- [x] Require one-way identities: results â†’ prereg; interpretation â†’ prereg + results.
- [x] Include programme/research-line/slice IDs, evidence/literature refs, H0/H1, MEPI, design, benchmarks, dependence method, inference family, sealed policy and coherence triggers.
- [x] Enforce the exact human decision enum while ensuring the machine never chooses the disposition.
### Task 3: Implement canonical preregistration identity and remote binding

- [x] Canonically serialize preregistration content and compute SHA-256 identity.
- [x] Prove semantically identical key ordering/formatting gives the same canonical identity and semantic changes do not.
- [x] Implement amendment/supersession lineage instead of in-place mutation.
- [x] Bind released preregistration to exact Git commit/tag and remote publication evidence.
- [x] Report the narrow mechanical claim `preregistration_remote_bound: verified`; do not claim proof that all external data access was impossible.

### Task 4: Make `freeze` the central command

Implement `commodity experiment freeze EXP_ID` so it fails closed unless it can:
- [x] validate prereg schema and programme context;
- [x] recompute scientific/economic MEPI;
- [x] recompute power/detectability and dependence-adjusted information;
- [x] validate required benchmark declarations, including market-implied comparators where relevant;
- [x] validate predeclared symmetric coherence/anomaly triggers;
- [x] register the programme inference-family entry;
- [x] validate sealed-window eligibility/accounting;
- [x] refuse an uninformative confirmatory design;
- [x] bind and remotely publish the immutable preregistration identity.

### Task 5: Implement basic `verify` and truth classes

- [x] Define structured verification findings tagged PROVEN, CHECKED or RECORDED.
- [x] PROVEN covers deterministic identities, schema, arithmetic, ledger/window accounting and executed required procedures.
- [x] CHECKED covers bounded known-risk PIT/leakage/integrity checks with explicit coverage language.
- [x] RECORDED covers human scientific judgments and cannot be upgraded to machine proof.
- [x] Add tests rejecting phrases/states equivalent to universal `no leakage` proof where only bounded checks ran.

### Task 6: Add `verify-power`

- [x] Recompute MEPI, raw/effective information and detectable effect from the frozen design.
- [x] Record method-specific dependence parameters and sensitivity.
- [x] Fail if stored derived quantities disagree with recomputation or if the experiment no longer meets its frozen feasibility gate.
- [x] Keep design-specific calculations; do not hard-code universal directional-accuracy sample-size tables.
## Phase 2 â€” results, leakage audit and coherence enforcement

### Task 7: Generate machine-authored `results.json`

- [x] Bind exact preregistration, code, data/vintage, split, model/checkpoint, runtime/environment and produced artifact identities.
- [x] Record raw evidence before interpretation: counts/coverage, benchmark comparisons, effects, uncertainty, tests and diagnostics.
- [x] Derive method compliance separately from scientific evidence.
- [x] Derive E0â€“E6 where rules are objectively encoded; reject manually asserted evidence levels that conflict with evidence.
- [x] Preserve failed/negative/inconclusive runs as immutable evidence rather than reopening rescue tuning.

### Task 8: Add domain-specific `audit-leakage`

- [x] Implement declared natural-gas/futures checks for PIT cutoffs, vintages, roll/contract identity, release timing, overlapping horizons, event windows, joins/cardinality and feature-family availability.
- [x] Return CHECKED findings with exact check coverage and limitations.
- [x] Treat required incomplete checks as fail-closed for promotion.
- [x] Keep exploratory access to sealed confirmation data as a hard failure.

### Task 9: Enforce symmetric coherence triggers

- [x] Require anomaly triggers in preregistration before unblinding.
- [x] Trigger equivalent enhanced audit for unexpectedly strong and unexpectedly weak outcomes.
- [x] Cover benchmark jumps, data-boundary discontinuities, mechanism-sign conflicts, observation concentration, suspicious feature/target relations and irrelevant-change sensitivity.
- [x] Preserve the original result; any correction receives a new run/preregistration identity with lineage.

### Task 10: Produce interpretation and executive summary

- [x] `interpretation.md` records RECORDED mechanism/coherence/literature/programme reasoning and the human disposition.
- [x] Generate `executive-summary.md` from authoritative refs, not copied mutable technical detail.
- [x] Enforce the six headings: Where this fits; Where the idea came from; What we tested; What we saw; What it means for the bigger picture; What next.
- [x] Keep the operator summary normally 120â€“200 words, plain English, no long tables or unexplained statistical jargon.
## Phase 3 â€” programme inference and sealed confirmation

### Task 11: Implement the L1 programme inference ledger

- [x] Record every confirmatory attempt, research line/family, primary metric, windows touched, exploratory ancestry, outcome and whether it influenced later design.
- [x] Track inference-family membership rather than only a classical alpha-spending number.
- [x] Provide integrity checks ensuring an experiment cannot disappear from programme history after an unattractive result.
- [x] Support appropriate family-level procedures such as Reality Check, SPA, Model Confidence Set or false-discovery controls without hard-coding one method for every family.
- [x] Feed programme-level interpretation back into the L1 evidence map.

### Task 12: Implement sealed-window accounting

- [x] Register sealed-window identity, eligibility, permitted openings and what an opening exposes.
- [x] Enforce zero exploratory/diagnostic access.
- [x] Record opening number, artifacts/metrics exposed and remaining eligibility for future claims.
- [x] Keep sealed confirmation distinct from rolling research OOS and genuinely new forward evidence.
- [x] Add fail-closed tests for exhausted or improperly opened confirmation windows.

### Task 13: Encode research-line stopping and selection rules

- [x] Require each L2 line to expose continuation/stopping conditions based on evidence, feasible power, economic relevance, confirmation capacity and expected information value.
- [x] Prevent an experiment from being selected solely for technical novelty.
- [x] Require traceability to current external/internal evidence, a contradiction or a high-value evidence-map gap.
- [x] Preserve `advance | replicate | refine | branch | hold | stop` as human decisions, with programme history retained regardless of choice.

## Phase 4 â€” reproduction and richer automation

### Task 14: Add `reproduce`

- [x] Define logical reproduction against dataset/prediction/result identities and numerical tolerance policy.
- [x] Define byte reproduction only for artifacts whose environment/serialization contract makes exact bytes meaningful.
- [x] Record dependency lock, runtime/interpreter, model/checkpoint and hardware-sensitive identity where relevant.
- [x] Report tolerance-sensitive differences without pretending bitwise equality is universally required for scientific replication.

### Task 15: Add staged CI enforcement

- [x] Phase 1 checks: schema, freeze integrity, power verification and basic experiment verification.
- [x] Phase 2 checks: results integrity and domain leakage/coherence enforcement.
- [x] Phase 3 checks: programme inference and sealed-window integrity.
- [x] Add stronger required checks only after the corresponding mechanism is proven stable; do not build a research-management platform ahead of need.
## Migration and #244 integration

### Task 16: Preserve legacy evidence and migrate only eligible work

- [x] Classify existing experiment records as completed legacy, frozen-but-unexecuted, or future/new methodology.
- [x] Never rewrite completed V1/V2 artifacts or manufacture retrospective preregistration.
- [x] For unexecuted frozen work, require proof that protected outcomes were not consumed before creating a successor preregistration with explicit inheritance/supersession lineage.
- [x] Keep legacy readers/contracts operational until compatibility is independently verified.
- [x] Update `AGENTS.md` authority ownership only when successor contracts are actually operational.

### Task 17: Gate surviving #244 research candidates

- [x] Keep #244 as portfolio compression: merge, supersede, defer or reject overlapping proposals before empirical work.
- [x] Require survivors to enter the L1 evidence/feasibility map rather than becoming executable automatically.
- [x] Require L2 research-line selection, slice literature review, mechanism/H0/H1, MEPI/power pass and candidate-specific immutable freeze before execution.
- [x] Preserve genuinely different targets/research mechanisms as distinct lines rather than forcing artificial consolidation.
- [x] Verify portfolio closure alone never grants empirical execution authority.

## Verification before methodology adoption

A later implementation may be adopted only after focused contract/gate tests, migration/legacy-regression tests, full relevant repository verification, exact-head CI, independent review and Work traceability all pass on the same exact revision.

The implementation review must explicitly prove or demonstrate:
- the preregistration cannot be mutated after release without a new identity;
- result and interpretation artifacts bind to the exact released preregistration;
- MEPI/power and dependence calculations are recomputed rather than trusted;
- PROVEN/CHECKED/RECORDED claims cannot be confused;
- sealed confirmation data is inaccessible to exploratory paths;
- inference-ledger history cannot silently omit prior attempts;
- E0â€“E6 classification follows encoded evidence rules where derivable;
- method compliance, evidence strength and human disposition remain independent;
- completed historical evidence remains byte/content unchanged;
- the executive summary is only a concise projection of stronger underlying authority.

## Implementation sequence

Execute phases in order. Phase 1 must be useful on its own before Phase 2 starts; Phase 2 must be useful before programme-level automation in Phase 3; reproduction/reporting enrichment comes last. This is deliberate YAGNI control from the accepted review.

The operator explicitly authorized full #249 implementation on 2026-08-29. #244 alone never authorizes empirical execution.
