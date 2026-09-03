<!-- GENERATED FILE. DO NOT EDIT. Source: config/research_methodology.json, config/research_dataset.json, contracts/*.schema.json -->

# Research Methodology

Source: `config/research_methodology.json`

## Big-picture research hierarchy

Every governed research artifact declares a zoom level.

- **L0 — Repository mandate:** Repository North Star defined by AGENTS.md: the durable Commodity platform purpose and primary objectives that direct all L1-L5 work.
- **L1 — Research programme:** Where might economically useful predictive information come from, and what does the accumulated evidence say?
- **L2 — Research line:** One mechanism/information family or economically distinct question.
- **L3 — Confirmatory experiment:** One frozen hypothesis and design.
- **L4 — Run/analysis:** One execution under an L3 contract.
- **L5 — Interpretation / diagnostic / exploration:** Post-result scientific interpretation and bounded diagnostic/exploratory investigation that cannot silently become confirmatory evidence or rewrite L4 results.

**North Star rule:** L0 is the North Star and directional authority for L1-L5. Every lower-level research artifact must state how it serves L0, and no L1-L5 result, experiment, run or diagnostic may redefine L0 from below.

**Promotion rule:** Evidence from L4/L5 never silently becomes an L0/L1 claim. Promotion upward is explicit and evidence-linked.

## Governed research workflow

This is the one authoritative end-to-end research workflow. Every governed experiment/run enters this 15-step workflow and may stop early only through the governed disposition/revisit rules.

| Step | Zoom level | Workflow stage | Required outcome |
| ---: | --- | --- | --- |
| 1 | **L0 → L1** | Helicopter view | Restate the fixed L0 North Star and the current L1 programme picture before choosing a local question. |
| 2 | **L1** | Gap | Identify the specific unresolved uncertainty that matters to a programme decision and bound what is outside scope. |
| 3 | **L1 → L2 → L3** | Evidence-led zoom-in | Select the research line and candidate slice from accumulated evidence and expected information value rather than novelty. |
| 4 | **L2 → L3** | Quality literature | Build the slice-specific literature snapshot that determines mechanism, expected effects, pitfalls, benchmarks and appropriate tests. |
| 5 | **L3** | Mechanism | State the economic or market mechanism and why it should produce a measurable effect. |
| 6 | **L3** | Hypothesis | State the falsifiable H0 and H1 for the bounded slice before protected outcomes are used. |
| 7 | **L3** | Expected and disconfirming observations | Freeze literature-derived expected and disconfirming observations and the practical-effect threshold before protected outcomes. |
| 8 | **L3** | Feasibility | Test data fitness, dependence, effective information, MEPI, power and confirmation capacity; only an informative design may proceed. |
| 9 | **L3** | Governed implementation + preregister and freeze if applicable | Implement and verify the exact runnable design, then preregister/freeze and remotely bind any confirmatory commitment before protected execution. |
| 10 | **L4** | Execute | Run exactly the governed exploratory or frozen confirmatory design and preserve raw machine result evidence before interpretation. |
| 11 | **L4** | Verify | Verify identities, data assurance, leakage controls, confirmation eligibility/accounting, reproduction and objective evidence classification without narrative promotion. |
| 12 | **L5** | Compare observed versus expected | Compare the preserved result explicitly with preregistered expectations, disconfirmers, MEPI and symmetric anomaly triggers. |
| 13 | **L5** | External post-result triangulation | Perform a genuinely independent post-result literature/evidence check rather than reusing the preregistration snapshot. |
| 14 | **L5 → L1/L2** | Programme conclusion | Retrace L4→L0, apply programme-level inference, update the evidence map and make the explicit advance/replicate/refine/branch/hold/stop disposition. |
| 15 | **L1/L2** | Active revisit triggers | For HOLD/DEFER, maintain machine-testable revisit conditions and evaluation history so any resumed work has a traceable successor identity. |

# Detailed governed research workflow

## Step 1: Helicopter view

**Zoom level:** `L0 → L1`

**Purpose:** Restate the fixed L0 repository mandate and the current L1 programme bigger picture before choosing a local question. The programme must reason from the complete governed history rather than starting from the newest model, dataset or idea.

**L0 authority:** `AGENTS.md#Commodity-and-Primary-objective`

**Core question:** Given the fixed L0 North Star and everything the programme has already tried and learned, what does the bigger picture currently say?

### Evidence inputs

- best available external academic and web evidence
- accumulated internal governed evidence
- experiment history
- programme inference ledger

### Accumulated programme-history sources

- research/programmes/<programme-id>/programme.json#line_refs
- research/programmes/<programme-id>/evidence-map.json#retrospective_synthesis
- research/programmes/<programme-id>/lines/<research-line-id>/line.json#experiment_history
- research/programmes/<programme-id>/inference-ledger.json
- research/programmes/<programme-id>/decisions.json
- research/programmes/<programme-id>/revisit-triggers.json

### Programme-level interpretation lenses

- Selection/data-snooping lens — repeated searches, model variants, predictor families and strategy variants count as accumulated search history rather than independent fresh ideas (White 2000; Sullivan, Timmermann & White 1999; Harvey, Liu & Zhu 2016; Bailey & López de Prado).
- Candidate-family lens — judge a claimed winner against the family of alternatives actually tried or implicitly searched, not only against the final reported comparator (Hansen 2005 SPA).
- Model-uncertainty lens — when evidence does not distinguish a unique winner, preserve uncertainty rather than manufacturing a champion (Hansen, Lunde & Nason 2011 MCS).
- Effective-information lens — calendar rows are not independent evidence; dependence, overlap, clustering, regimes and conditional sampling reduce effective information and must affect programme confidence.
- Forecast-comparison validity lens — do not generalize a test statistic or benchmark comparison beyond the design conditions under which it is interpretable (Diebold forecast-comparison clarification).
- Economic/backtest-realism lens — statistical improvement is not a platform edge unless it can survive selection effects, costs, turnover, execution, uncertainty and risk constraints.

### History reasoning rules

- Aggregate evidence across the complete governed experiment history; a new model name or nearby specification does not reset prior negative evidence or multiple-testing burden.
- Keep narrow negative evidence narrow: a failed model/target/horizon rules out that tested claim, not an entire information family or the Commodity platform mission.
- Keep diagnostics and replications distinct from trading evidence: interesting structure can justify a new branch without being promoted into an edge claim.
- Track historical-window reuse and confirmation capacity explicitly; reused development windows cannot silently become fresh confirmation.
- Prefer branches that test a materially different mechanism, target, horizon, instrument, information family or decision role when nearby variants have repeatedly failed.
- Use the whole history to decide what not to research again; stopping is a positive L0 programme decision when expected information value is low.
- Because Commodity is instrument-independent at L0, accumulated natural-gas evidence informs methodology and branch selection but cannot collapse the platform mission into one market.

### Governing principles

- Optimize the research programme for information gained per genuinely independent confirmation evidence, not for the number of experiments completed.
- Preserve and spend independent confirmation capacity deliberately; repeated reuse of the same historical outcomes does not create fresh independent evidence.
- Store governed facts once in their canonical machine-readable owner, reference them elsewhere, and generate prose only for human use.

### Evidence-exposure hierarchy

- Development — available for fitting, feature work, debugging, model selection and exploratory research.
- Rolling research OOS — multiple chronological historical test periods used for development-time evaluation; repeated reuse makes them partly research-trained and they must not be described as pristine confirmation.
- Reserved confirmation — a chronologically later block whose identity may be known but whose outcomes must not influence fitting, feature/model/hyperparameter/threshold selection, hypothesis formulation or redesign before freeze.
- True forward evidence — newly arriving post-freeze observations; the strongest independence class.

### Legacy evidence and migration rules

- Completed V1/V2 work remains historical evidence under the contracts that governed it and is not rewritten to manufacture retrospective preregistration.
- Frozen but unexecuted legacy work may migrate only when protected outcome evidence has not been consumed, using a new preregistration identity with explicit lineage.
- Known-defective historical evidence remains preserved with its defect disposition and cannot silently become current clean evidence.

### Stability and boundary rules

- L0 changes only when the repository purpose or primary objectives themselves change.
- L1-L5 work must remain directionally aligned to L0 but cannot redefine it from below.
- Market-, instrument-, venue-, contract-, data-source- and execution-specific differences remain bounded below L0.

### Methodological canon

Emphasize financial-research failure modes first, while retaining general reproducibility and preregistration literature as supporting methodology. Slice reviews should store stable reference IDs rather than copy long literature summaries into every experiment.

### Programme reasoning output

A concise L1 synthesis stating what the total governed history now supports, what it weakens, which search paths should not be repeated, what remains genuinely open, and which broad uncertainty has the highest expected information value before feasibility screening.

**Completion condition:** The fixed L0 mandate and current L1 evidence state are explicit, including prior negative evidence, reused history, confirmation capacity and the broad uncertainties that remain genuinely open.

## Step 2: Gap

**Zoom level:** `L1`

**Purpose:** Identify one specific uncertainty that matters to a programme decision before choosing an experiment.

### Required inputs

- current L1 programme synthesis from Step 1
- programme stopping state
- remaining confirmation capacity
- open recommendations/revisit triggers

### Gap rules

- The gap must be decision-relevant: resolving it could change a programme or research-line action.
- State one primary uncertainty and what remains outside scope so the work cannot silently expand.
- Do not define a gap merely because a technique, model or dataset is technically interesting.
- A repeatedly tested near-neighbour is not a new gap unless mechanism, target, horizon, information source, instrument or decision role changes materially.

### Required output

Artifact: `future research-line/slice candidate`

- `programme question`
- `decision-relevant gap`
- `why it matters`
- `outside scope`

**Completion condition:** One bounded, decision-relevant programme uncertainty is explicit and worth considering for evidence-led zoom-in.

## Step 3: Evidence-led zoom-in

**Zoom level:** `L1 → L2 → L3`

**Purpose:** Choose the research line and candidate experimental slice because the accumulated evidence says it has high expected information value, not because it is novel.

### Scope when relevant

- return/price predictability
- volatility
- storage/fundamentals
- weather
- term structure/carry
- positioning/flows
- macro and energy cross-market effects
- seasonality/regimes
- foundation/time-series models
- alternative targets/horizons
- transaction costs and economic viability

### Selection inputs

- current L1 evidence synthesis
- L1 feasibility map
- programme stopping state
- remaining independent confirmation capacity

### Selection rules

- Prefer a line that can materially change a programme belief or decision.
- Do not reopen a repeatedly rejected near-neighbour line without a materially new mechanism, target, horizon, information source, instrument or decision role.
- Keep negative evidence scoped to the tested claim; do not reject a whole information family merely because one implementation failed.
- A research line may be selected for scientific learning even when immediate trading usefulness is not yet established, provided the information value is explicit.
- Trace the selected slice to strong external evidence, a clear unresolved contradiction or a high-value gap in the programme evidence map.
- Do not select a slice merely because it is novel or technically interesting.
- The selected slice must state the parent question, the one uncertainty reduced now and what remains outside scope.
- Material changes to target, horizon, conditioning, frequency, sample construction, information source or mechanism create a new slice identity.

### Required output

Artifact: `research/programmes/<programme-id>/programme.json#line_refs + research/programmes/<programme-id>/lines/<research-line-id>/line.json plus future preregistration candidate`

- `research_line_id`
- `slice_id`
- `why_zoomed_in`
- `parent_question`
- `uncertainty_reduced`
- `outside_scope`

**Completion condition:** One evidence-led L2 line and bounded L3 candidate slice are selected; feasibility and detailed design remain unapproved until later stages.

## Step 4: Quality literature

**Zoom level:** `L2 → L3`

**Purpose:** Research the selected slice deeply enough that the mechanism, expectations, benchmarks, failure modes and test design are derived from reputable primary or high-quality sources rather than post-hoc storytelling.

### Detailed review scope

- mechanism and causal/economic rationale
- closest prior empirical results
- known failure modes and confounders
- expected effect magnitude and direction where literature supports it
- appropriate targets, horizons, estimators, benchmarks and statistical tests
- data requirements, timing semantics and known leakage risks
- evidence that would contradict or materially weaken the proposed mechanism

### Rules

- The review answers Exactly how should we test this? and is narrower/deeper than the L1 programme scan.
- Use stable literature/reference IDs rather than duplicating long summaries into each experiment.
- The experiment direction must be derived from the literature plus programme evidence, not reverse-engineered around available protected results.
- If the literature undermines the selected line or suggests the proposed test is not interpretable, return to L2/L1 rather than forcing an experiment.

### Required output

Artifact: `slice literature snapshot`

- `reference_ids`
- `mechanism_summary`
- `prior_results`
- `pitfalls`
- `expected_magnitude`
- `recommended_tests`

**Completion condition:** The literature review yields a defensible mechanism/test direction or sends the programme back for redesign/hold/stop.

## Step 5: Mechanism

**Zoom level:** `L3`

**Purpose:** State the causal/economic/market mechanism that connects the permitted information set to the target before protected outcomes are examined.

### Mechanism rules

- Tie every material mechanism claim to the Step 4 literature snapshot or explicitly mark it as a programme hypothesis.
- State the expected direction and relevant boundary/regime conditions when the literature supports them.
- Identify plausible confounders, measurement failures and timing assumptions that could mimic the mechanism.
- If the mechanism cannot produce a measurable effect under available data semantics, return to Step 2/3 rather than forcing a test.

**Completion condition:** The slice has a source-linked, economically interpretable mechanism with explicit boundaries and confounders.

## Step 6: Hypothesis

**Zoom level:** `L3`

**Purpose:** Translate the mechanism into a falsifiable null and alternative before protected outcomes are used.

### Hypothesis rules

- State formal H0 and H1 narrowly enough that success, failure and inconclusive outcomes are distinguishable.
- Keep statistical hypotheses distinct from E0?E6 scientific evidence levels.
- Do not broaden or rewrite H0/H1 after observing protected results; a material change creates a new experiment identity.

### Required output

Artifact: `future prereg.json#hypotheses`

- `H0`
- `H1`
- `claim scope`

**Completion condition:** A falsifiable H0/H1 pair exists for the exact bounded slice.

## Step 7: Expected and disconfirming observations

**Zoom level:** `L3`

**Purpose:** Derive both expected and disconfirming observations from Step 4 literature and the Step 5 mechanism before looking at the relevant protected result, and precommit the practical-effect threshold.

### Expected/disconfirming observation rules

- Expected and disconfirming observations must be symmetric enough that unexpectedly attractive results receive at least as much scrutiny as disappointing ones.
- Where literature supports magnitude or direction, record it before protected results; otherwise record the uncertainty rather than inventing precision.
- Define scientific MEPI and economic MEPI where a trading-usefulness claim is intended; MEPI must be derivable from declared inputs and cannot be invented after results.
- Define success, failure and inconclusive logic before protected outcomes.

### Design elements

- expected observations
- disconfirming observations
- scientific_mepi
- economic_mepi where applicable
- success/failure/inconclusive logic

**Completion condition:** The slice has source-derived expectations, disconfirmers and practical-effect thresholds that can be checked without post-result reinterpretation.

## Step 8: Feasibility

**Zoom level:** `L3`

**Purpose:** Determine whether the exact proposed design is informative enough to justify implementation and any use of reserved confirmation evidence.

**Redesign rule:** A material redesign changes the scientific question and receives a new slice/experiment identity; do not execute first and explain underpower afterwards.

### Gate sequence

- economic/scientific relevance
- detectable effect
- available information
- go/no-go

### MEPI rules

- MEPI must be derivable from declared inputs.
- A trading-usefulness claim requires an economic MEPI.
- A pure volatility or forecasting question may legitimately begin with a scientific MEPI.

### Power and detectability rules

- Power and detectability must use the actual experiment design.
- No universal hard-coded sample-size table is authoritative.
- Serial dependence, overlapping horizons, event clustering, regimes and conditional sampling must be reflected in the chosen method.

### Required dimensions

- target
- horizon
- information_family
- scientific_mepi
- economic_mepi where applicable
- raw_information
- effective_information
- detectable_effect
- expected_snr
- costs
- feasibility

### Gate inputs

- MEPI from Step 7
- raw observation count
- dependence-adjusted information
- target/horizon/sample construction
- planned estimator/statistic and uncertainty procedure
- reasonable dependence sensitivity choices

### Dependence and effective-information rules

- effective_n is never a hand-entered trusted number; record raw count, dependence structure, estimator/method, parameters, computed effective information and sensitivity.
- Use HAC/Newey-West, block bootstrap, clustered/event treatment, overlapping-horizon treatment or another justified method as appropriate.
- Not every statistic requires one universal scalar effective sample size; record the dependence-adjusted information quantity appropriate to the design.

### Confirmation-capacity and split rules

- Use multiple chronological rolling research-OOS periods across the development history rather than relying on one arbitrary middle holdout.
- Reserve the chronologically latest usable block for independent confirmation under the planning default declared by config/research_dataset.json; that default is not a universal rule, and the actual share must be justified by horizon, dependence, power, regime coverage, usable history and remaining confirmation capacity.
- Where targets or forecast horizons overlap across a split boundary, use purging, embargo or an equivalent design-specific boundary control.
- Do not spend reserved confirmation data on an experiment whose MEPI/power gate cannot make the opening informative.

### Failure actions

- redesign
- hold
- stop

### MEPI — Minimum Effect of Practical Importance

MEPI — Minimum Effect of Practical Importance — is an L1/L2 programme quantity and must not be invented after observing results.

- `scientific_mepi`: Smallest forecasting/statistical effect worth learning about.
- `economic_mepi`: Smallest effect plausibly useful after spread, slippage, fees, turnover and risk constraints.

### Canonical evaluation-data policy

- Sequence: development → rolling_research_oos → reserved_confirmation → true_forward.
- Reserved confirmation planning default: 20% of the usable chronological sample, using the latest usable block; this is a planning default, not a universal rule.
- The actual share must be justified by the experiment's horizon, dependence, power, regime coverage, usable history and remaining confirmation capacity.
- Reserved-confirmation identity may be known; its outcomes must not influence pre-freeze design, fitting or selection.

**Completion condition:** Only a scientifically/economically relevant, data-fit and adequately detectable design with justified confirmation capacity may cross into governed implementation.

## Step 9: Governed implementation + preregister and freeze if applicable

**Zoom level:** `L3`

**Purpose:** Cross from research design into active repository work: create a governed .work change for the selected experiment, implement the exact runnable experiment code/data/config/test slice, verify it, and only then freeze and bind the executable scientific commitment before protected execution.

**Repository transition:** .work begins here. The approved L3 experiment/preregistration is the implementation specification. Do not create a second implementation spec: translate the experiment contract directly into repository code, tests, configuration and evidence under the governed change.

### Rules

- Protected results remain unopened throughout implementation and freeze.
- Implementation may reveal engineering infeasibility; if it changes the scientific design, return to the appropriate earlier research step and issue a new design identity rather than silently mutating the preregistration.
- Released preregistration is immutable; amendments create a new identity that explicitly supersedes the previous one.
- .work is operational/change history, not scientific authority.

### Governed repository-change requirements

- create/claim the governed experiment change under .work/changes/<change-id>/ through the live KIS lifecycle
- reference the approved L3 experiment/preregistration as the implementation specification; do not restate, duplicate or redefine it in a second .work spec
- record only the implementation translation plan: affected repo owners, code/test tasks, TDD sequence, risks, review steps and verification evidence
- use the authoritative schema-v4 change classification — complexity, risk_triggers and work_management.documentation_impact — to determine any separate documentation work; documentation impact never creates another experiment/specification artifact
- load develop-code and every applicable TDD, data, research/statistics, code-review and code-verification skill before translating the experiment into repository behavior
- implement required reusable code, bounded adapters, data construction, configuration, schemas and tests in their canonical repository owners
- preserve experiment-specific scientific authority beneath its parent line at research/programmes/<programme-id>/lines/<research-line-id>/experiments/<experiment-id>/ rather than .work
- run deterministic pre-CI verification using the active worktree-local .venv

### Implementation quality gate

- derive tests from the intended scientific/software contract and acceptance criteria rather than from the implementation's own assumptions
- use test-driven development for behavior changes unless the governed KIS change records a justified exception
- add adversarial and regression coverage for boundary conditions, failure modes, leakage/PIT risks, identity mismatches and previously observed defect classes relevant to the slice
- use an independent oracle, reconstruction path, reference calculation or verifier wherever feasible so correctness is not self-certified by the code under test
- for data transformations or derived datasets, independently reconstruct and compare against authoritative inputs/semantics where feasible rather than only checking internal consistency
- prove the literature-derived implementation by replicating the relevant published/reference result on the repository's correctly normalized, semantically verified data before treating the new experiment direction as faithful to that literature
- record any material replication mismatch as a scientific finding that returns the slice to the appropriate earlier research step rather than hiding the mismatch inside implementation tuning
- run the focused tests plus the full affected regression suite; do not suppress, weaken or relabel regressions to obtain a green result
- perform code review against design intent, implementation correctness, test relevance, edge cases and failure handling
- obtain independent review for high-risk experiment/data/methodology implementation before freeze when feasible
- any implementation edit after review or verification invalidates the affected evidence and requires the applicable checks/review to be rerun

### Freeze gate

- validate preregistration schema
- resolve current programme evidence and inference-ledger context
- recompute MEPI
- recompute power/detectability and dependence-adjusted information
- check benchmark declarations
- check symmetric coherence/anomaly triggers
- allocate/register programme inference entry
- validate reserved-confirmation/sealed-window policy and eligibility
- refuse an uninformative design
- bind exact preregistration content to canonical SHA-256 and remote repository evidence
- record immutable freeze identity and amendment lineage

### What preregistration must freeze

- programme, research-line and slice identities plus evidence-scan and literature-snapshot references
- mechanism, H0/H1, expected and disconfirming observations, and scientific/economic MEPI derivation
- target, horizon, prediction-time, target-time and information-cutoff semantics
- dataset and vintage identities, sample roles, historical windows and the development/rolling-OOS/reserved-confirmation allocation
- dependence-adjustment method, parameters and generated effective-information calculation
- feature/preprocessing identities and permitted information families
- model/configuration/checkpoint identities and training rules
- primary and secondary metrics, uncertainty/inference procedure, statistical family and candidate family
- benchmarks including market-informed comparators where economically relevant
- programme multiple-testing/inference-ledger identity
- reserved-confirmation/sealed-window policy, eligibility and opening rules
- symmetric anomaly/coherence triggers frozen before unblinding
- success, failure and inconclusive logic plus the permitted human disposition enum
- environment identity and logical/byte reproduction tolerance policy
- lineage for any predecessor, amendment or exploratory ancestry

### Benchmark rules

- Where a liquid market-implied quantity is economically related to the target, normally include it as a benchmark or explanatory comparator.
- A market-implied comparator is a tradable market comparator and must not be described automatically as an unbiased forecast or true expectation.
- Depending on the target, valid comparators may include futures/curve, current settlement, carry-implied relationships, market-implied volatility, seasonal or naive forecasts, and simple econometric baselines.

### Reserved-confirmation rules

- The reserved confirmation block is governed by config/research_dataset.json and may be known by identity; independence is about non-use in design, fitting and selection before freeze, not secrecy.
- Exploratory/L5 work must not use reserved confirmation outcomes for fitting, feature/model/hyperparameter/threshold selection, hypothesis formulation or redesign.
- After freeze, the frozen design may generate predictions and evaluate them on eligible reserved confirmation observations.
- Once reserved confirmation outcomes influence redesign or selection, those observations are consumed as independent confirmation evidence for that design and cannot be reused as fresh confirmation.
- Opening/accounting for governed confirmation windows must record identity, eligibility, opening number, permitted openings, exposed artifacts and whether later claim use remains admissible.

### Preregistration binding semantics

- preregistration_remote_bound: verified means the exact canonical preregistration content existed remotely no later than the recorded repository event.
- Remote binding proves the repository publication event only; it does not prove that nobody viewed relevant outcomes elsewhere before freeze.
- Released preregistration content is immutable; amendment creates a new preregistration identity that explicitly supersedes the old one.

### Scientific artifact and projection model

- The linked GitHub Project issue is the human-facing research-slice record; do not create a second slice narrative/specification in repository Markdown.
- prereg.json — human-authored immutable L3 scientific commitment.
- results.json — machine-authored L4 execution/result evidence bound to the preregistration identity.
- interpretation.md — human L5 scientific interpretation written only after results exist and bound to both preregistration and results identities.
- executive-summary.md — generated operator-facing view, not an additional source of scientific authority.
- record.json — compact durable completed-experiment index linking origin, frozen setup, result, interpretation, programme consequence, decisions, recommendations and open questions; it references canonical authorities rather than duplicating or competing with them.
- Reference direction is one-way: results bind to preregistration; interpretation binds to preregistration and results; generated views and record.json project/reference those authorities. Per-slice Markdown is not required merely to narrate the slice.

### Automation and enforcement

- The methodology is enforced incrementally through schemas, freeze, verification, power checks, dataset assurance, programme-inference integrity, reserved-confirmation accounting, leakage/coherence checks and reproduction controls.
- Current experiment automation includes register, verify, verify-power, freeze, can-run, open-sealed, build-results, verify-results, audit-leakage, reproduce and executive-summary surfaces where implemented.
- Repository CI/pre-CI enforcement must reject methodology/schema drift rather than relying on operator memory or documentation alone.

### Environment identity and reproduction semantics

- **Logical reproduction:** Same dataset, prediction and result identities within the declared numerical tolerance contract.
- **Byte reproduction:** Exact bytes only where runtime, hardware and serialization semantics make bitwise identity meaningful.

Required identity:

- lockfile/dependency identity
- interpreter/runtime identity
- model/checkpoint identity
- hardware-sensitive facts where numerically relevant
- declared numerical tolerance policy

Bitwise equality is not universal scientific proof; the experiment must declare whether logical or byte reproduction is authoritative for each governed output.

**Completion condition:** The experiment has a verified runnable repository implementation and an immutable remotely bound preregistration/freeze identity; only then may protected execution begin.

## Step 10: Execute

**Zoom level:** `L4`

**Purpose:** Run exactly the governed exploratory or frozen confirmatory design and preserve machine-authored raw evidence before any human interpretation.

### Execution rules

- Execute only the frozen implementation/configuration and declared data roles.
- Write machine result evidence before human interpretation.
- Results point to the frozen preregistration identity; they do not rewrite it.
- Any deviation that changes the scientific question invalidates the run as confirmation and requires a new design identity.
- For confirmatory work, use reserved confirmation only after the design is frozen and only under its declared eligibility/opening policy.
- Exploratory runs remain explicitly exploratory and cannot be retroactively relabeled as confirmatory evidence.
- Write results.json before interpretation.md; execution evidence must bind to the exact preregistration, code, data, features, model and environment identities.

### Required output

Artifact: `research/programmes/<programme-id>/lines/<research-line-id>/experiments/<experiment-id>/results.json`

- `raw evidence`
- `benchmark comparison`
- `effect size and uncertainty`
- `primary/secondary metrics`
- `predeclared tests`
- `identity bindings`

**Completion condition:** The run is complete and immutable raw machine evidence exists, bound to the exact governed design, ready for independent verification.

## Step 11: Verify

**Zoom level:** `L4`

**Purpose:** Verify the mechanical and bounded-risk promises of the run before narrative interpretation or programme promotion.

### Verification truth classes

- PROVEN — deterministic/mechanical assertions
- CHECKED — bounded known-risk checks with honest scope
- RECORDED — human/scientific judgment

### Verification requirements

- verify schema, hashes, frozen-preregistration identity, code/data/feature/model/environment identities and declared cardinality/accounting
- verify dataset reconstruction and semantic correctness, including source-bound data assurance where required
- verify reserved-confirmation eligibility, opening number/permitted openings, exposed artifacts and whether those observations remain admissible for later claims
- verify benchmark output presence, MEPI/power arithmetic, inference-ledger membership and objectively encoded E-level rules
- verify reproduction under the declared logical or byte semantics and numerical tolerance contract

### Domain-specific leakage controls

- check declared point-in-time information cutoffs and target/prediction timing
- check vintage/release timing for fundamentals and exogenous data
- check futures roll and contract identity
- check release calendars, event windows and overlapping horizons
- check joins/cardinality and feature-family availability rules
- apply purging, embargo or an equivalent boundary treatment where target/horizon overlap can contaminate train/test boundaries
- report bounded wording such as 'No known PIT violations detected by the declared checks'; never claim 'No leakage' from a finite checklist

### Result preservation and lineage rules

- The original result is preserved even when verification fails or an anomaly is later explained.
- A correction or material design change creates a new run/preregistration identity with explicit lineage; consumed evidence is never overwritten.
- Method compliance, scientific evidence and human disposition remain orthogonal statuses.

### Truth-class rules

- PROVEN is reserved for deterministic/mechanical assertions such as schema, hashes, identities, exact test execution, derived E-level rules and objective accounting.
- CHECKED is bounded known-risk checking and must use honest scoped wording; passing a leakage checklist is not proof that leakage is impossible.
- RECORDED is human/scientific judgment including mechanism plausibility, coherence interpretation, literature reconciliation, hierarchy retrace and recommended next action.

### E0–E6 evidence definitions

- E0 — no useful evidence: no consistent useful benchmark-relative effect.
- E1 — interesting signal: direction or magnitude is potentially interesting but uncertainty is large.
- E2 — statistical evidence: predeclared inferential support exists.
- E3 — robust forecasting evidence: survives preregistered OOS, regime/reasonable-loss and robustness requirements.
- E4 — economically meaningful evidence: magnitude plausibly matters after realistic costs and constraints.
- E5 — replicated independent evidence: finding survives genuinely independent data, time, regime or later forward evidence.
- E6 — programme-level evidence: strong enough after programme-level inference controls to materially change the overall programme thesis.

### Evidence-level rules

- Scientific evidence remains E0–E6 and is machine-derived wherever objective rules exist.
- The preserved L4 result is never overwritten by interpretation, correction or later diagnostic work.
- L5 interpretation cannot upgrade the machine-derived E-level by prose.
- Unexpectedly attractive results receive at least as much scrutiny as disappointing results.

### Orthogonal experiment status

- Method compliance: VERIFIED | FAILED | INCOMPLETE
- Scientific evidence: E0 | E1 | E2 | E3 | E4 | E5 | E6
- Human disposition: ADVANCE | REPLICATE | REFINE | BRANCH | HOLD | STOP

**Completion condition:** The run has an honest PROVEN/CHECKED verification record and objective E0–E6 classification where mechanically derivable; unresolved scientific judgment remains for L5.

## Step 12: Compare observed versus expected

**Zoom level:** `L5`

**Purpose:** Interpret the preserved L4 result against the exact preregistered expectations, disconfirmers, hypotheses, MEPI and symmetric coherence triggers without rewriting the result.

### Questions this step must answer

- Did the observed direction, magnitude and uncertainty match what Step 6 literature and Step 7 expectations predicted?
- If not, is the mismatch evidence against the mechanism, a boundary/measurement issue, a data/implementation concern, or genuinely unresolved?
- Were any unexpectedly good or unexpectedly bad coherence triggers activated, and what bounded checks were performed?
- Did the observed result satisfy the frozen success/failure/inconclusive logic and MEPI threshold?

### Interpretation inputs

- immutable L4 results.json and verification record
- frozen L3 preregistration
- Step 4 literature snapshot
- Step 5 mechanism
- Step 7 expected/disconfirming observations and MEPI

### Symmetric coherence/anomaly trigger classes

- implausibly large benchmark improvement
- discontinuity at a data or provider boundary
- sign contrary to a strong preregistered mechanism
- effect concentrated in a few observations, events or regimes
- suspicious feature/target relationship or timing
- material result change after an apparently irrelevant implementation edit

### Coherence rules

- Coherence/anomaly triggers are frozen before unblinding and applied symmetrically to unexpectedly good and unexpectedly bad outcomes.
- A triggered anomaly causes investigation, not selective deletion or silent result repair.
- L5 prose cannot upgrade the machine-derived E-level or convert a failed/incomplete method-compliance state into verified evidence.

**Completion condition:** The interpretation states exactly where observations agree or conflict with frozen expectations and disconfirmers, with symmetric anomalies explicitly accounted for.

## Step 13: External post-result triangulation

**Zoom level:** `L5`

**Purpose:** Perform a fresh literature/evidence check after the result is known so interpretation is tested against independent external context rather than merely reusing the preregistration snapshot.

### External triangulation rules

- Use an independently identified post-result literature snapshot; do not relabel the Step 4 preregistration literature as post-result triangulation.
- Search for evidence that supports, contradicts or bounds the observed result, including regime/boundary explanations and failed replications where available.
- Record literature reconciliation as RECORDED scientific judgment; external agreement does not mechanically upgrade E-level.
- Preserve the original result and preregistered expectation even when later literature changes interpretation.

### Required output

Artifact: `post-result literature snapshot plus interpretation metadata`

- `independent snapshot identity`
- `supporting evidence`
- `contradicting evidence`
- `boundary/regime evidence`
- `literature reconciliation`

**Completion condition:** The result has been triangulated against a genuinely independent post-result evidence search with supporting and disconfirming external context recorded.

## Step 14: Programme conclusion

**Zoom level:** `L5 → L1/L2`

**Purpose:** Retrace the result from L4 through L0, interpret it inside the full programme search history, update programme evidence and make one explicit human disposition without rewriting prior evidence.

### Required inputs

- L5 interpretation
- programme inference ledger
- family inference result
- complete experiment history
- historical windows and sealed-window usage

### Hierarchy retrace: L4 back to L0

- L4 — state exactly what the run produced and what is mechanically PROVEN/CHECKED.
- L3 — compare observed versus frozen H0/H1, MEPI, expected/disconfirming observations and success/failure/inconclusive logic.
- L2 — state whether this strengthens, weakens, narrows, redirects or leaves unchanged the selected research line.
- L1 — state the programme implication only after accumulated-history and multiple-testing context; identify what belief or uncertainty changes.
- L0 — state how the updated L1 position serves the fixed repository mandate; never rewrite L0 from below.

### Programme-level inference rules

- Internal cleanliness of one experiment does not erase programme-level data snooping.
- Repeated testing of the same history increases the evidential hurdle.
- Use the preregistered Reality Check, SPA, Model Confidence Set, false-discovery procedure or other justified family-level method; do not pretend experiments are independent.
- A result may remain scientifically interesting while failing to justify a programme-level belief change.

### Programme conclusion questions

- What does the result mean for the exact L3 hypothesis and MEPI claim?
- What does it change, if anything, for the parent L2 research line?
- What does it change, if anything, in the L1 accumulated programme evidence after accounting for prior attempts and reused history?
- Does anything here affect how L1 should pursue the fixed L0 North Star? L0 itself is not redefined by the result.

### Programme evidence update rules

- append the experiment and immutable identities to the relevant research-line history
- separate supported, weakened, rejected, diagnostic and still-untested claims
- preserve narrow scope of negative findings
- record consumed confirmation capacity and historical-window reuse
- do not turn RECORDED interpretation into machine evidence

### Disposition and stopping rules

- advance only when evidence justifies moving the research line forward
- replicate when independent confirmation has high information value
- refine when the same underlying question remains valid but a bounded design improvement is justified
- branch when a valid unexpected finding creates a distinct research line
- hold when evidence or capacity is insufficient but revisit triggers remain credible
- stop when accumulated negative evidence, poor feasible power, weak economics, exhausted confirmation capacity or low information value makes more work unattractive
- the verifier validates the enum but does not choose the disposition

### Confirmatory and exploratory documentation model

- The linked GitHub Project issue is the human-facing research-slice document; do not create additional per-slice Markdown merely to narrate the slice.
- Confirmatory work keeps compact prereg.json, machine-authored results.json, concise interpretation.md and generated executive-summary.md; record.json links them without becoming a competing scientific authority.
- Exploratory/diagnostic work keeps a small structured run record containing run identity, parent question, purpose, inputs, change, result, promotion decision and optional promoted_to identity.
- Exploratory work may be discarded, continued or promoted, but promotion creates a new confirmatory preregistration; exploration is never retroactively relabeled as confirmation.
- Repository-level generated Markdown remains allowed for durable cross-slice methodology/configuration projections.

### Compact durable record rules

- A completed confirmatory experiment writes one compact durable record.json whose workflow array mirrors all 15 authoritative methodology stages in exact order.
- Each record stage stores only its stage identity, completion/not-applicable status, a concise statement of what that stage established, and references to the canonical evidence; the record is the durable argument spine, not a duplicate evidence store.
- The complete experiment must be reconstructable by following record.json from Step 1 through Step 15; no methodology stage may exist only in remembered reasoning, chat history or transient .work prose.
- record.json references canonical facts rather than duplicating mutable copies; decisions and unresolved follow-ups are projections from that record/canonical owners, not competing authorities.
- Programme evidence updates append immutable identities and preserve prior state/history rather than rewriting the past.

### Mandatory operator executive summary

- Every completed confirmatory experiment and major research-line update produces a short plain-English operator summary, normally about 120–200 words.
- Use exactly these six headings: Where this fits; Where the idea came from; What we tested; What we saw; What it means for the bigger picture; What next.
- Separate method compliance, scientific evidence and human disposition; include numbers only when they materially affect the decision and avoid methodology dumps or unexplained statistical jargon.

### Required output

Artifact: `interpretation.md + programme evidence/inference updates + record.json + generated executive-summary.md`

- `L4→L0 retrace`
- `programme-level inference`
- `evidence-map update`
- `ADVANCE/REPLICATE/REFINE/BRANCH/HOLD/STOP`
- `record links`
- `six-part executive summary`

**Completion condition:** The experiment closes its scientific loop with an evidence-bound L4→L0 conclusion, programme-level inference, updated L1 state, explicit disposition and durable linked operator record.

## Step 15: Active revisit triggers

**Zoom level:** `L1/L2`

**Purpose:** Keep HOLD/DEFER scientifically active rather than leaving a prose reminder: register deterministic revisit conditions, evidence inputs, thresholds and evaluation history, and require a traceable successor before research resumes when a trigger fires.

### Required inputs

- human disposition from Step 14
- current unresolved uncertainty and reason for HOLD/DEFER
- machine-observable evidence inputs or events that could change the decision
- canonical revisit-trigger registry

### Rules

- HOLD/DEFER must have a machine-testable trigger when future evidence could make the question worth revisiting.
- Each trigger declares its evidence source, condition/threshold, evaluation history and current state.
- Governed research preflight re-evaluates active triggers rather than relying on remembered prose.
- A satisfied trigger does not mutate the completed experiment; it releases or creates a traceable successor with a new governed identity.
- STOP does not require a revisit trigger unless a specific future condition is explicitly declared to reopen the line.

### Required output

Artifact: `research/programmes/001-commodity-natural-gas/revisit-triggers.json`

- `trigger identity`
- `parent experiment/research-line identity`
- `evidence inputs`
- `machine-testable condition/threshold`
- `evaluation history`
- `current state`
- `successor/release identity when triggered`

**Completion condition:** Every HOLD/DEFER that can be revisited has an active machine-testable trigger and evaluation history, while completed evidence remains immutable and any resumed work starts under a traceable successor identity.

## Exploratory research

Exploratory work uses the active exploratory schema and may investigate feasibility and mechanisms, but it does not establish a confirmatory claim.

## Confirmatory research

Confirmatory work is bound to the preregistration/results contracts and must satisfy the machine execution gates before protected evidence is used.

## What is immutable

Frozen preregistration and bound evidence identities are not rewritten after observing protected results.

## Confirmatory execution requires

- `complete_research_lifecycle`
- `quality_literature_snapshot`
- `valid_preregistration`
- `passed_mepi_power_gate`
- `programme_inference_registration`
- `revisit_trigger_preflight`
- `sealed_window_eligibility_if_used`
- `remote_bound_preregistration_freeze`
- `verified_dataset_reconstruction`
- `verified_dataset_semantics`

## Human and machine responsibilities

Humans select and interpret research questions; machine contracts verify the encoded commitments and evidence bindings. Research evidence does not grant trading permission.
