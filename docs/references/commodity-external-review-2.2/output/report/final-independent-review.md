# Independent External Research Review -- Commodity Natural-Gas Research Programme

**Prepared for:** Commodity repository (`NielPieterse0/commodity`), issues #86 and #109
**Prepared by:** Independent external research review (this engagement)
**Date:** 2026-08-16
**Status:** Final for this engagement -- bounded single-pass review, not an exhaustive systematic review (see Section 12, Limitations)
**Scope authority:** This document is evidence and recommendation only. It does not modify Commodity, `AGENTS.md`, `config/policy.json`, or any repository authority file.

---

## 0. How to read this pack

This markdown file is the narrative synthesis. It references, but does not
duplicate, the machine-readable evidence:

- `bibliography/bibliography.csv` / `.json` -- full source list with access status
- `evidence/paper-evidence-matrix.csv` -- per-paper scoring
- `evidence/driver-evidence-matrix.csv` -- per-driver scoring across geographies
- `evidence/negative-evidence-register.csv` -- documented negative/contradictory findings
- `hypotheses/hypothesis-portfolio.md` / `.json` -- 6 ranked, falsifiable hypotheses
- `data/data-feasibility-map.csv` -- PIT feasibility per candidate data source
- `execution/execution-feasibility.md` -- independent check against issue #109
- `papers/README.md`, `institutional-reports/README.md` -- access/verification notes

Every substantive claim below is tagged **[verified]** (independently retrieved
and read at least at abstract/key-findings level in this engagement),
**[secondary]** (found only via another source's citation of it, not opened
directly), or **[assumption/inference]** (this reviewer's own reasoning, not
a cited finding). Where a claim is [secondary], treat it as a lead, not
evidence.

---

## 1. Deliverable A -- Executive Assessment

**1. What predominantly drives natural-gas prices.** For the US: storage
level vs. seasonal norm, the weekly storage-change *surprise* specifically,
realised and forecast-revised weather, and LNG feedgas/export demand as the
structural channel connecting the US market to the rest of the world
**[verified]**. For Europe: storage-vs-target trajectory, pipeline/LNG
infrastructure state (not just volumes), and since 2022 a materially larger
and still-growing dependence on LNG (nearly half of EU supply; the US
supplied 58% of EU LNG imports in 2025) **[verified, ACER 2026]**. Crude oil
is a *former*, not current, primary US driver -- the HH-WTI cointegration
that once mattered broke down around January 2009 and forecasting models
built on it now perform *worse* than a random walk **[verified, Baumeister
et al. 2024]**.

**2. Which drivers appear genuinely forecast-relevant** (as opposed to
merely explanatory). Two, at the horizon that matters for Commodity's
current V1 target (1 trading session): the weekly US storage-change
*surprise* relative to a documented pre-release consensus **[verified,
though the core academic evidence predates the current market regime]**,
and short-lead-time weather-*forecast-revision* content (2-4 days)
**[verified only at the level of a single, non-peer-reviewed industry case
study]**. At longer horizons (9-24 months), the spot-futures spread has
demonstrated, real-time-validated forecasting content **[verified,
Baumeister et al. 2024]**. The global/EU LNG-transmission channel that
motivates H-GLOBAL-LNG-1 has strong *explanatory* and *contemporaneous*
support but **no demonstrated out-of-sample forecasting evidence for Henry
Hub specifically was located in this review**, at any horizon.

**3. How US, EU and global markets interact.** They are integrated in the
sense that matters for market structure (EU/Asian benchmark correlation hit
an all-time high of 0.955 in 2025 **[verified, IEA Q1-2026]**), but that
integration is *conditional and time-varying*, not constant. The clearest
and most consequential finding of this review is that the US market
specifically **decoupled** from EU/Asia during the most acute stress window
of the 2021-2022 crisis, precisely because LNG infrastructure was congested
**[verified, Farag, Jeddi & Kopp 2025]**, and that the single most on-point
peer-reviewed test finds the European crisis "only marginally" affected US
prices, with the two markets described as evolving "largely independently"
**[verified, Rubaszek & Szafranek 2025]**. Global gas-market convergence in
the strong (price-levelling) sense is explicitly rejected in the literature
**[verified, Loureiro, Inchauspe & Aguilera 2023]** -- consistent with, and
supportive of, H-GLOBAL-LNG-1's own decision *not* to assume unconditional
convergence.

**4. Whether H-GLOBAL-LNG-1 remains justified.** **SUPPORTED WITH REVISION**
-- see Deliverable E below for the full reasoning. The mechanism is
economically coherent and each link has partial support, but the strongest
single piece of directly relevant evidence leans skeptical of the aggregate
transmission strength, and no source demonstrates the mechanism operates at
Commodity's current 1-trading-session horizon.

**5. Which alternative hypotheses deserve testing.** In priority order: US
storage-surprise (H2), weather-forecast-revision (H3), then a re-horizoned
version of H-GLOBAL-LNG-1 itself (H1). Full specifications in
`hypotheses/hypothesis-portfolio.md`.

**6. Whether required data can be reconstructed PIT-safe.** Mostly yes for
the US-domestic candidates (EIA storage and STEO archives are genuinely
PIT-reconstructable; CFTC COT is clean). Mixed-to-weak for the global/EU
candidates: JKM specifically leans toward `UNSUITABLE` without a confirmed
Platts licensing budget; TTF, GIE AGSI/ALSI and ENTSOG are
`PIT_POSSIBLE_WITH_WORK` but were not fully verified in this pass (several
are genuine open items, not resolved facts -- see Section 9). Full detail in
`data/data-feasibility-map.csv`.

**7. Whether successful signals appear practically tradable.** **VIABLE WITH
CONDITIONS.** The instrument (`MNG`) and exchange infrastructure are real,
well-specified, and CME-confirmed. The blocking gap is account-level
entitlement verification for a Norway-resident Saxo (or IBKR) account, which
this external review cannot perform and which remains exactly the work
issue #109 already scopes. Full detail in `execution/execution-feasibility.md`.

---

## 2. Deliverable E -- H-GLOBAL-LNG-1 Verdict

> **VERDICT: SUPPORTED WITH REVISION**

**Why not `SUPPORTED AS WRITTEN`:** The hypothesis note's own evidence basis
leans on the *contemporaneous correlation* growth documented by IEA/ACER/ECB
and on a qualitative, non-tested forward-looking remark in Rubaszek &
Szafranek (2025) about *future* dependence. Independently reading that same
paper's actual *result* -- not just the note's characterisation of it --
shows the authors' central finding is that the 2021-2023 crisis only
marginally affected the US market and that the two markets evolve largely
independently **[verified]**. That is a materially more skeptical framing
than "evidence basis already identified" in the existing note conveys, and
it is the single most directly on-point peer-reviewed test available.
Separately, Farag, Jeddi & Kopp (2025) show the mechanism can *invert* --
the US market actually decoupled from EU/Asia specifically during the
highest-transmission-likelihood window (Oct 2021-Nov 2022) because of
infrastructure congestion **[verified]**. A hypothesis whose own best
evidence leans skeptical, and whose second-best evidence shows the
mechanism can vanish under stress rather than strengthen, should not be
accepted as written.

**Why not `NOT SUPPORTED` or `INSUFFICIENT EVIDENCE`:** The mechanism is
economically coherent, each individual link has *some* support (EU
connectedness is real and infrastructure-conditional **[verified, Papiez et
al. 2022; Szafranek et al. 2023; Farag & Ruhnau 2026]**; LNG destination
flexibility genuinely redirects cargoes based on netback spreads, richly
illustrated by the live 2026 Strait-of-Hormuz/Qatar episode
**[verified, multiple current sources]**; rising US LNG export share is a
real, measured, growing channel **[verified, ACER/IEA]**), and no source
reviewed *rejects* the conditional, capacity-utilisation-gated version of
the hypothesis specifically. The evidence base is genuinely mixed, not
absent or uniformly negative.

**Required revision, specifically:**

1. **Re-horizon.** Every piece of peer-reviewed evidence bearing on this
   mechanism operates at weekly, monthly, or quarterly frequency. None
   demonstrates next-session forecast content. Testing against Commodity's
   current 1-session V1 target is likely to produce a *horizon-driven* null
   result that would be wrongly read as a *mechanism-driven* rejection.
2. **Widen the conditioning set.** The existing note's "high-priority
   interactions" implicitly assume transmission strength moves smoothly up
   or down with the conditioning variables. The Farag/Jeddi/Kopp decoupling
   finding shows it can also *break entirely* under acute infrastructure
   stress -- the interaction design needs an explicit congestion/regime
   state, not just a utilisation level.
3. **Sequence after, not before, better-evidenced and better-horizon-matched
   alternatives.** H2 (US storage surprise) and H3 (weather-forecast
   revision) are cheaper, more directly evidenced at the relevant horizon,
   and do not carry the JKM licensing-cost risk. See `hypotheses/hypothesis-portfolio.md`.

**Falsifiability, restated (should not be weakened by this revision):**
Reject the refined hypothesis if, at a horizon actually supported by the
literature (weekly/monthly), the full interaction specification (including
the added congestion state) does not show a preregistered, PIT-valid,
material OOS increment over the frozen US-only comparator and the simpler
global-price control -- the existing note's stop conditions already say
this correctly and should be kept.

---

## 3. Deliverable G -- Trading/Execution Verdict

> **VERDICT: VIABLE WITH CONDITIONS**

Full reasoning and field-by-field status in `execution/execution-feasibility.md`.
In summary: the exchange-side facts (contract specs, fungibility, financial
settlement, Saxo's structural avoidance of physical delivery) are
independently confirmed and favourable. The blocking conditions are (a)
authenticated account/API-level entitlement verification for a
Norway-resident account at Saxo and/or IBKR, which no external web research
can substitute for, and (b) an explicit, deterministic mapping from
whatever continuous/reference series a model is trained on to the exact
`MNG` (or `NG`) contract-month that would actually be ordered -- a design
requirement, not a data problem, and currently unresolved in general in the
reviewed literature.

---

## 4. Literature review synthesis (Deliverable B)

### 4.1 United States

Storage (level and, more importantly, the weekly *surprise* against a
pre-release consensus) is the most directly forecast-relevant US driver at
short horizons **[verified]**. LNG feedgas/export demand is the structural
channel that both raises the US price floor as capacity grows and is the
literal mechanism by which global shocks could reach Henry Hub -- EIA's own
scenario analysis frames this cleanly (earlier LNG-facility start-up ->
higher feedgas demand -> lower storage -> higher HH price, all else equal)
**[verified, EIA 2025]**, and the current August-2026 STEO already reflects
this dynamic in the opposite direction (reduced feedgas demand from Freeport
LNG maintenance -> storage above five-year average -> lower near-term price
forecast) **[verified, EIA STEO Aug 2026]**. The single richest US
forecasting-methodology source located, Baumeister, Huber, Lee & Ravazzolo
(2024, NBER), is unusual in this literature for being a *genuinely
real-time-evaluated* study: it built an explicit PIT vintage database back
to 1991 specifically to avoid look-ahead bias, and it demonstrates that a
parsimonious 6-variable BVAR(1) beats a random-walk benchmark at every
horizon from 1 to 24 months, with futures-based forecasts also beating the
benchmark throughout, and that forecast *pooling* (via a real-time Model
Confidence Set selection) delivers the largest gains of all **[verified]**.
It also documents, as a directly transferable negative finding, that the
once-reliable HH-WTI cointegration relationship broke in January 2009 and
that a Markov-switching model built specifically to detect that break in
real time still failed to recover pre-break performance **[verified]** --
see the negative-evidence register.

### 4.2 Europe

European hub connectedness is high, has risen structurally since 2015, and
is centred on TTF and the German NCG as net transmitters **[verified, Papiez
et al. 2022]**, but that connectedness is *not* uniform: even within Europe,
the UK NBP decoupled from continental hubs specifically during the acute
2022 invasion-shock period even as the continental hubs stayed tightly
linked to each other **[verified, Szafranek et al. 2023]** -- direct evidence
that "European connectedness" is an interconnector-specific, regime-
dependent property, not a fixed geographic fact. The most current source
reviewed, Farag & Ruhnau (2026), extends this picture through mid-2024 and
finds contemporaneous spillovers dominate even during crises, connectedness
collapsed sharply in 2022 and rebounded by late 2023 as LNG capacity
expanded, and pipeline congestion (specifically the BBL interconnector)
significantly weakens connectedness **[verified]**. Since 2022, LNG now
supplies nearly half of EU gas, the US alone supplied 58% of EU LNG imports
in 2025, and TTF prices 74% of EU spot LNG trades **[verified, ACER 2026]**.

### 4.3 Norway

**This review did not independently search or verify Norway-specific
sources (Norwegian Offshore Directorate production data, Gassco flow/outage
messaging, SSB export statistics)**, despite these being explicitly in
scope. This is a genuine gap in this engagement, not a finding that
Norwegian data is uninformative -- see Section 9 (Research-Gap Analysis) and
the corresponding `UNKNOWN` rows in `data/data-feasibility-map.csv`. The
project's own data-manifest already lists these as candidate families
requiring verification; this review neither confirms nor disconfirms their
value and should not be read as having done so.

### 4.4 Asia / LNG

Asian LNG price formation is structurally less mature than US/EU markets --
a 2023 literature review found Asian markets still lack a transparent
pricing benchmark comparable to Henry Hub or TTF, delaying functional
Asia-Pacific hub formation **[verified, Hupka et al. 2023]**. The JKM-TTF
spread is the primary mechanism by which flexible cargoes are redirected
between basins, and the live 2026 Strait-of-Hormuz/Qatar disruption is an
unusually clean natural experiment: the spread flipped from a roughly
$0.9-2.1/MMBtu premium *in favour of Europe* (January-February 2026) to a
premium *in favour of Asia* of similar or larger magnitude by March-June
2026, tracked in near-real-time by vessel-diversion data **[verified,
multiple current trade-press and IEA Q2/Q3-2026 sources]**. This is strong
*contemporaneous* evidence of the mechanism's existence; it is not, by
itself, forecasting evidence for Henry Hub -- no source reviewed
demonstrates that the spread or its reversal leads, rather than
accompanies, US price moves.

### 4.5 Global

Global LNG destination flexibility has risen structurally (now roughly 70%
of new contracts per one industry source, not independently verified
against a primary source in this pass), and this is precisely the structural
change that makes cross-basin transmission *more plausible today than in any
historical academic sample* -- most of the peer-reviewed connectedness
literature reviewed here has a sample window ending before or during the
2021-2022 crisis and therefore does not fully capture the post-2023,
higher-flexibility regime. This is simultaneously the strongest argument for
taking H-GLOBAL-LNG-1 seriously and the strongest argument for distrusting
any single historical estimate of its strength.

---

## 5. Predictive vs. explanatory evidence -- classification summary

Applying the assignment's mandatory six-way classification across every
driver reviewed (full detail in `evidence/driver-evidence-matrix.csv`):

- **Demonstrated OOS forecasting evidence** exists for exactly two things in
  this review: (a) the spot-futures spread at 9-24 month horizons
  **[verified, Baumeister et al. 2024]**, and (b) the storage-change
  surprise at 1-day horizon **[verified, but on a pre-2011 sample]**.
- **Contemporaneous/structural association, not demonstrated forecasting
  value:** the entire EU/global connectedness literature (Papiez et al.,
  Szafranek et al., Farag & Ruhnau, Farag/Jeddi/Kopp), the TTF-JKM
  spread/cargo-diversion mechanism, CFTC positioning.
- **Hypothesis only / insufficient evidence:** weather-forecast-revision
  content specifically (only industry, non-peer-reviewed evidence located);
  the full H-GLOBAL-LNG-1 chain as a single, tested, end-to-end mechanism.
- **Contradicted / negative:** HH-WTI cointegration as a current forecasting
  tool; long-lag/high-complexity VAR models vs. parsimonious alternatives;
  simple price-levelling convergence.

---

## 6. Volatility, regime-dependence and structural change

The evidence assembled here supports treating natural-gas forecasting as
**genuinely regime-dependent**, not as a single stable relationship with
noise around it. Three independent lines of evidence converge on this:

1. Baumeister et al. (2024) explicitly periodise the US market into four
   regimes (pre-2006 oil-linkage; 2006-2009 shale transition; 2010-2016
   "shut-in fracking" decoupling from oil; 2016-present LNG-export
   recoupling) and show the *best-performing model class itself changes*
   across these regimes **[verified]**.
2. The EU connectedness literature documents sharp, event-driven collapses
   and rebounds in market integration (2022 collapse, 2023-24 rebound)
   **[verified, Farag & Ruhnau 2026]**, and infrastructure-specific
   fragmentation even within a single crisis (UK vs. continental Europe)
   **[verified, Szafranek et al. 2023]**.
3. The live 2026 Strait-of-Hormuz episode is a real-time illustration of a
   discrete regime shift materially repricing both TTF and JKM within
   weeks **[verified, IEA Q2/Q3-2026]**.

This supports models that *condition on observable market/economic state*
(H6 in the hypothesis portfolio) over a single unconditional relationship --
but the evidence for regime-dependence itself is much stronger than the
evidence for any specific, currently-available, PIT-clean regime-flagging
data source (see the outage/event-feed gap noted in Section 9 and in
`data/data-feasibility-map.csv`).

---

## 7. Technical / market-structure features

Evidence for technical/price-derived features in natural gas, evaluated
against the assignment's requirement to distinguish applicability across
continuous series, front-month, and exact tradable contracts:

- **Futures-spot spread:** demonstrated forecasting value at 9-24 month
  horizons using standard settlement data **[verified]**.
- **Calendar-spread mean-reversion:** an abstract-level result claims
  Sharpe ratios above 2 for natural gas after transaction costs
  (1992-2013), but authorship and full methodology were not independently
  confirmed in this pass -- **treat as unverified, not as evidence**, until
  the primary source is retrieved.
- **Roll/continuous-series construction risk:** this is flagged repeatedly
  across the reviewed curve-dynamics and roll-yield literature as a general,
  unresolved hazard: a model trained on a continuous or front-month
  reference series does not automatically produce the same behaviour as an
  order on a specific contract-month, particularly around roll dates in a
  contango market (documented qualitatively in the ICE white paper reviewed
  and consistent with the general commodity-futures roll-yield literature).
  No source reviewed offers a general fix; it is a design requirement (see
  Section 19-equivalent discussion in `execution/execution-feasibility.md`).
- **CFTC positioning:** contemporaneous association only, with real ambiguity
  about lead-lag direction (one reviewed academic source finds noncommercial
  positioning *follows* price rises at least as much as it leads them)
  **[verified via secondary academic source; author/year not independently
  re-confirmed]** -- see negative-evidence register.

---

## 8. Contradiction / negative-evidence summary

Full register in `evidence/negative-evidence-register.csv`. The single most
consequential entries for Commodity specifically:

1. The European crisis "only marginally" affected the US market -- directly
   undercuts a strong reading of H-GLOBAL-LNG-1's evidence basis.
2. The US market decoupled from EU/Asia during the 2021-2022 crisis due to
   infrastructure congestion -- the mechanism can invert under stress, not
   just strengthen.
3. HH-WTI cointegration broke in 2009 and now actively *hurts* forecast
   accuracy if assumed -- a template for how a Commodity researcher should
   treat any single historically-cointegrated relationship.
4. Long-lag, highly parameterised VAR models underperform parsimonious ones
   in real-time evaluation -- directly consistent with, and independent
   corroboration of, Commodity's own V1 result (HistGB RMSE 0.0465 > naive
   RMSE 0.0453; robust edge demonstrated: false).
5. CFTC positioning's predictive direction is ambiguous, not clearly
   leading.
6. Continuous-series-to-tradable-contract mapping is a general, unresolved
   hazard, not a solved problem.

---

## 9. Research-gap analysis (what this review did *not* establish)

Stated plainly, as required:

- **Norway-specific sources** (Norwegian Offshore Directorate, Gassco,
  SSB) were not independently searched in this pass. This is a coverage
  gap in this engagement, not evidence that Norwegian data lacks
  incremental information beyond TTF -- that specific question (posed in
  issue #86) remains open.
- **JKM-specific academic literature and licensing terms** were reviewed
  only via secondary/institutional framing, not a dedicated academic search
  or a Platts licensing-cost check.
- **Two expansion citations** (Ben Amar, Lmasrar & Bouattour 2025;
  Emiliozzi, Ferriani & Gazzani 2025) were surfaced only through other
  papers' reference lists and were **not independently opened** -- they are
  flagged as high-priority follow-up retrievals, not used as evidence
  anywhere in this report's substantive conclusions.
- **A dedicated citation-chain search** (papers citing or cited by the seed
  literature, beyond what surfaced incidentally during the seed-paper
  searches) was not exhaustively performed; this review located roughly a
  dozen expansion papers opportunistically rather than through a systematic
  forward/backward citation trace.
- **GIE AGSI/ALSI and ENTSOG revision behaviour and exact publication
  timing** were not independently verified -- flagged `PIT_POSSIBLE_WITH_WORK`
  rather than `PIT_READY` pending that check.
- **Post-2025 LNG-transmission literature specifically testing the current,
  higher-flexibility regime** does not yet appear to exist in peer-reviewed
  form (the newest connectedness paper reviewed, Farag & Ruhnau 2026, ends
  its sample in mid-2024) -- this is a genuine literature gap, not a search
  failure, and is consistent with the assignment's own framing that recent
  structural change may outrun the academic literature's ability to test it.

None of these gaps should be read as negative findings. They define what a
follow-up, better-resourced review should prioritise before Commodity treats
any Norway- or Asia-specific data source as either validated or ruled out.

---

## 10. Point-in-time / vintage feasibility -- summary

Full classification in `data/data-feasibility-map.csv`. Headline pattern:
**US-domestic sources are consistently the most PIT-ready** (EIA WNGSR and
STEO both have genuine, independently-demonstrated real-time reconstruction
precedent in Baumeister et al. 2024; CFTC COT is clean). **Global/EU sources
are consistently harder**: TTF's historical-data entitlement is unverified
(a gap the project's own data-manifest already flags, and which this review
could not close); JKM specifically is a licensed, proprietary benchmark and
leans `UNSUITABLE` absent a confirmed budget; GIE AGSI/ALSI and ENTSOG
revision behaviour is plausible but unverified. This asymmetry is itself a
reason to prioritise the US-only hypotheses (H2, H3) before the global
hypothesis (H1/H-GLOBAL-LNG-1) on cost and speed grounds, independent of the
horizon-mismatch argument in Section 2.

---

## 11. Repository recommendations (bounded; Commodity is not modified by this review)

Distinguishing category per the assignment's Section 28 requirement:

**Correctness requirements** (things the existing note should fix
regardless of new testing):
- Revise H-GLOBAL-LNG-1's evidence-basis summary of Rubaszek & Szafranek
  (2025) to state the paper's actual central finding (marginal/independent
  evolution), not only its forward-looking remark about future dependence.
- Add an explicit horizon statement to H-GLOBAL-LNG-1: state plainly that no
  reviewed evidence supports a 1-trading-session forecast horizon for this
  mechanism, and that the frozen V1/V2 daily target is a horizon mismatch
  unless and until re-scoped.

**Research hypotheses** (candidates for future preregistration -- see
`hypotheses/hypothesis-portfolio.md` for full specification):
- H2 (US storage surprise), H3 (weather-forecast revision), H1 (refined,
  re-horizoned H-GLOBAL-LNG-1), H4 (futures-spread, separate longer-horizon
  track), H6 (regime-conditioning overlay, as an enhancement layer).

**Data-acquisition investigations** (not yet resolved, need dedicated
follow-up before any acquisition commitment):
- TTF historical-data entitlement (ICE) -- already flagged in the project's
  own data-manifest; unresolved here too.
- JKM/Platts licensing cost and terms.
- GIE AGSI/ALSI and ENTSOG revision behaviour and publication timing.
- Norwegian Offshore Directorate / Gassco / SSB access terms and PIT depth
  -- not searched in this pass at all.
- A documented, fixed, historical consensus-forecast source for the weekly
  EIA storage report (needed for H2).
- ECMWF archived-forecast licensing cost (needed for a rigorous version of
  H3; NOAA/Open-Meteo may suffice as a lower-cost substitute).

**Model-design constraints** (evidence-based, not preference-based):
- Prefer parsimonious specifications (or explicit Bayesian shrinkage) over
  long-lag/high-complexity models as a default, given the consistent,
  real-time-demonstrated pattern that over-parameterised VARs underperform
  the random walk -- and given that this exact pattern already appears in
  Commodity's own V1 result.
- Any model relying on HH-WTI cointegration must include an explicit,
  tested contingency for the possibility that the relationship is not
  currently active (per the documented 2009 break).
- Any curve/spread-based feature must specify, in advance, the exact
  continuous-series or contract-month construction rule, given the
  documented general roll-artefact risk.

**Execution requirements:**
- Complete the Saxo SIM (and/or IBKR paper) authenticated verification
  already scoped in issue #109 -- this review confirms it cannot be
  shortcut from outside an account and identifies exactly which facts
  remain open (see `execution/execution-feasibility.md`).
- Resolve the continuous/reference-series-to-exact-`MNG`-contract-month
  mapping as an explicit design artifact before connecting any signal to a
  paper or live order path.

**Explicitly rejected ideas (do not pursue further without new evidence):**
- Using CFTC positioning as a presumptively *leading* short-horizon signal
  without first testing lead-lag direction explicitly.
- Treating raw TTF/JKM price levels (H5) as a standalone forecasting
  hypothesis rather than as the required baseline-comparator inside H1's
  test ladder.
- Assuming a crisis/stress period will mechanically *strengthen* global-to-US
  transmission -- the best evidence found says the opposite can happen.

---

## 12. Limitations of this review (state plainly, per the assignment's
independence and integrity requirements)

- This was a single-pass, time-bounded external review, not a multi-week
  systematic review. Roughly a dozen papers were reviewed beyond the five
  seed papers; a fully systematic forward/backward citation trace was not
  completed.
- Most peer-reviewed sources were reviewed at abstract/key-findings depth,
  not full text, because the published versions are paywalled (Elsevier,
  Springer, Wiley) and were not licensed for retrieval in this engagement.
  Exactly one source (Baumeister, Huber, Lee & Ravazzolo 2024, NBER) was
  reviewed at full-text depth. This is stated explicitly per paper in
  `evidence/paper-evidence-matrix.csv` and should not be conflated with a
  full-text review of the whole corpus.
- Two expansion citations were not independently verified beyond appearing
  in other papers' reference lists and are excluded from this report's
  substantive conclusions.
- Norway-specific institutional sources were not searched at all in this
  pass -- a genuine, stated gap, not a null finding.
- Execution verification is necessarily incomplete by design: this review
  has no authenticated broker account and should not be given one; the
  account-level facts in Section 3 and `execution/execution-feasibility.md`
  remain open pending #109's own verification work.
- Where a citation's exact venue/year could not be confirmed (notably the
  Linn & Zhu storage-surprise paper), this is flagged in the evidence
  tables rather than presented as a settled citation.

The highest-value output of this review is not confirmation of the existing
architecture. It is: a specific, evidence-based case for revising
H-GLOBAL-LNG-1's framing and horizon before further investment; a
higher-priority, cheaper, better-evidenced pair of alternative hypotheses
(H2, H3); a documented set of negative findings that generalise beyond the
specific hypothesis under audit; and a precise statement of which execution
facts remain genuinely unverifiable without an authenticated account, so
that work is not duplicated or skipped.
