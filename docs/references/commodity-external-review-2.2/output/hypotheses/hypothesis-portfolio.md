# Hypothesis Portfolio -- Ranked Candidates for Future Preregistration

Prepared as part of the independent external research review, 2026-08-16.
These are candidates for later preregistration. No experiments were run.
Ranking criteria (in order applied): economic plausibility -> academic support ->
PIT feasibility -> data availability -> expected independent information ->
ability to test cleanly -> trading relevance.

---

## H2 -- US storage-surprise short-horizon signal (top-ranked)

- **Economic mechanism:** Weekly EIA storage-change surprises (actual minus a
  documented pre-release consensus) carry information not yet in price because
  the release is a discrete scheduled news event; markets react to the surprise
  component, not the level.
- **Prior evidence:** Demonstrated in a reviewed event study (`linn_zhu_storage_surprise`,
  sample 2002-2011): a significant inverse relationship between storage-change
  surprise and same-day futures/spot price change. Corroborated qualitatively by
  extensive 2025-2026 trade-press evidence of 3-5% announcement-day moves.
- **Target:** Henry Hub / front-month NG next-session (or same-session
  post-release) log return -- this is the single best horizon match in the
  entire review to Commodity's current V1 target (`ng-next-session-return-baseline-v1`).
- **Horizon:** 1 trading session (report-day and the session immediately following).
- **Candidate inputs:** EIA WNGSR actual value; a fixed, documented consensus-forecast
  source (e.g., a specific vendor survey) captured *before* the Thursday release.
- **PIT requirements:** PIT_READY for the actual (EIA release archive exists);
  PIT_POSSIBLE_WITH_WORK for the consensus benchmark -- a consistent historical
  consensus source must be fixed and its own publication timing documented before
  this is fully PIT-clean.
- **Baseline/control:** Zero-return naive (already Commodity's existing V1
  control) plus a "surprise=0 / storage day only" dummy control to separate a
  pure day-of-week effect from the surprise-magnitude effect.
- **Expected direction:** Larger-than-expected withdrawal (or smaller-than-expected
  injection) -> positive same/next-session return; sign matches the
  reviewed event study.
- **Necessary interactions:** None required for the base test; a secondary,
  separately preregistered test could interact the surprise with current
  storage-vs-seasonal-norm tightness.
- **Falsification criterion:** No statistically and economically material
  improvement over the naive baseline on 2016-2026 (current-regime) data, using
  the same walk-forward/OOS discipline as the frozen V1/V2 contract.
- **Key risks:** (1) the underlying academic evidence predates the shale/LNG-export
  era and needs replication on current data before being treated as settled;
  (2) a clean, fixed, PIT-safe consensus-forecast source must be located and
  licensed/verified -- this is the main blocking data-acquisition item.
- **Recommended next action:** Locate and verify a PIT-safe consensus-forecast
  source for the weekly storage report; replicate the event-study design on
  2016-2026 data as a first, cheap, horizon-matched test before any global/EU
  hypothesis is prioritised.

---

## H3 -- Weather-forecast revision (vs realised weather) short-horizon signal

- **Economic mechanism:** Short-lead-time weather-forecast revisions move
  expected near-term heating/cooling demand before it is realised; if the
  market underreacts to revisions relative to levels, forecast-revision content
  should be more informative than realised-weather content at short horizons.
- **Prior evidence:** A vendor case study (`World Climate Service`, 2026,
  reviewed as industry evidence, NOT peer-reviewed) finds a statistically
  significant relationship between CONUS HDD-anomaly forecasts and Henry Hub
  spot-price volatility, strongest at 2-4 day lead and decaying sharply beyond
  10-14 days, consistent across GFS/GEFS/ECMWF. Academic corroboration was not
  independently located in this review and should be sought before this
  hypothesis is elevated above "plausible."
- **Target:** Henry Hub next-session return or short-horizon realised
  volatility.
- **Horizon:** 2-7 days (per the vendor study's own decay profile).
- **Candidate inputs:** Archived GFS/GEFS/ECMWF (or a re-packager such as
  Open-Meteo, already in Commodity's preferred-source register) issued
  forecasts, run-over-run change in demand-weighted HDD/CDD.
- **PIT requirements:** PIT_POSSIBLE_WITH_WORK -- forecast issuance is
  naturally PIT-correct (each run is a timestamped object), but archive depth
  and cost (especially for ECMWF) need confirmation.
- **Baseline/control:** Naive; a realised-weather-only control (to isolate the
  incremental value of the REVISION over the LEVEL, per the assignment's
  specific question).
- **Expected direction:** A cooling (bullish, winter) or warming (bullish,
  summer cooling-demand) revision at short lead time -> same-direction price
  move; effect should decay with lead time.
- **Necessary interactions:** Season (winter HDD-driven vs summer CDD-driven)
  should be modelled as a fixed interaction, not pooled.
- **Falsification criterion:** No material OOS improvement over the
  realised-weather-only control, or no decay pattern with lead time consistent
  with the vendor study's claimed profile.
- **Key risks:** No peer-reviewed replication located; possible vendor
  selection/marketing bias in the case study; ECMWF archive cost unconfirmed.
- **Recommended next action:** A dedicated academic-literature search on
  weather-forecast-revision (not realised-weather) effects in energy markets,
  which this review's time budget did not permit in full depth; treat as the
  second-priority near-term US-only test.

---

## H1 -- EU storage-deficit x US-LNG-utilisation interaction (H-GLOBAL-LNG-1, refined)

- **Economic mechanism:** This is H-GLOBAL-LNG-1 narrowed and re-horizoned.
  EU storage tightness (vs seasonal norm) raises the netback incentive to
  route flexible LNG cargoes toward Europe; this incentive only translates
  into a measurable US domestic effect when US liquefaction capacity is
  actually utilised near its ceiling (i.e., when the US export channel is the
  binding constraint, not idle capacity).
- **Prior evidence:** Mixed. Contemporaneous/explanatory support is strong
  (IEA, ACER, ECB all document rising EU-Asia and EU-US LNG interlinkage;
  `farag_ruhnau_2026` and `szafranek_papiez_rubaszek_smiech_2023` show EU
  connectedness is real but conditional on infrastructure state). Direct
  US-side transmission evidence is weak-to-negative: `rubaszek_szafranek_2025`
  finds the 2021-2023 European crisis only marginally affected the US market;
  `farag_jeddi_kopp_2025` finds the US market actually DECOUPLED from EU/Asia
  during the most acute 2021-2022 stress window due to infrastructure
  congestion -- the opposite of a strengthening-under-stress assumption.
- **Target:** Henry Hub -- but see the horizon warning below.
- **Horizon:** Weeks to months, NOT 1 trading session. **This is the single
  most important design-level finding of the review**: every piece of
  peer-reviewed evidence bearing on this mechanism operates at a weekly,
  monthly, or quarterly frequency (structural VARs, connectedness indices,
  cointegration tests). No source reviewed demonstrates next-session
  forecast content from this channel. Testing H1/H-GLOBAL-LNG-1 against
  Commodity's current 1-session V1 target is very likely to fail not because
  the mechanism is false, but because the horizon is mismatched.
- **Candidate inputs:** GIE AGSI EU storage-vs-norm; US LNG feedgas/export
  volume and liquefaction utilisation (EIA); TTF-JKM spread; US storage
  tightness.
- **PIT requirements:** PIT_POSSIBLE_WITH_WORK across the board (see
  data-feasibility-map.csv); JKM specifically leans UNSUITABLE without a
  confirmed Platts licence budget.
- **Baseline/control:** Frozen US-only comparator (per H-GLOBAL-LNG-1's own
  existing test ladder A/B/C/D), but evaluated at a WEEKLY or MONTHLY horizon
  in addition to, not instead of, the current daily target, so that a
  horizon-driven null result can be distinguished from a mechanism-driven one.
- **Expected direction:** Higher EU storage deficit x higher US LNG utilisation
  -> tighter US domestic balance -> higher HH price/volatility, per
  H-GLOBAL-LNG-1's own statement.
- **Necessary interactions:** EU-storage-deficit x US-LNG-utilisation (as
  already specified); should ALSO include an explicit infrastructure-congestion
  state variable given the `farag_jeddi_kopp_2025` decoupling finding, or the
  interaction term will silently average over a regime where the mechanism
  inverts.
- **Falsification criterion:** As already well-specified in the existing
  H-GLOBAL-LNG-1 note's stop conditions -- retained here, with the addition
  that a genuine test must first be run at a horizon where the mechanism has
  actual peer-reviewed support (weekly/monthly) before a 1-session-horizon
  failure is treated as informative about the mechanism itself.
- **Key risks:** Horizon mismatch (see above); JKM data cost/licensing;
  the single most on-point paper (`rubaszek_szafranek_2025`) leans skeptical.
- **Recommended next action:** Do not activate at the current V1/V2 1-session
  horizon. If pursued, re-scope as a weekly- or monthly-horizon test, run
  strictly after H2 and H3 (which are far cheaper, better horizon-matched, and
  better evidenced) have been tested and their results banked.

---

## H4 -- Futures-curve / calendar-spread state signal

- **Economic mechanism:** The shape of the futures curve (contango/backwardation,
  calendar-spread level) reflects storage/seasonal fundamentals and has been
  shown, for the SPOT-FUTURES SPREAD specifically, to carry predictive content
  for the future spot price.
- **Prior evidence:** Demonstrated at 9-24 month horizons for the
  spot-futures-spread forecast in `baumeister_huber_lee_ravazzolo_2024`
  (beats random walk at all evaluated horizons, largest gains 9-15 months).
  A separate mean-reversion calendar-spread strategy result (Sharpe >2 for
  natural gas after costs, 1992-2013) was found only at abstract level and is
  NOT independently verified in this review.
- **Target:** Henry Hub level (for the spread-forecast version) or a
  calendar-spread return (for the mean-reversion version -- unverified).
- **Horizon:** 9-24 months (verified result) vs days-to-weeks (unverified
  claim) -- these are two different hypotheses that should not be conflated.
- **Candidate inputs:** NG futures curve by contract-month (settlement
  prices).
- **PIT requirements:** PIT_READY for the raw settlement data; the
  CONSTRUCTION of any continuous or spread series must be fixed and
  documented (see negative-evidence register on continuous-series roll risk).
- **Baseline/control:** Naive; also compare against the pure futures-price
  no-change forecast (both are "model-free" per the NBER paper's own
  terminology).
- **Expected direction:** Not directional in the simple sense -- the spread
  model's forecast direction is data-determined by the current spread level,
  not a fixed sign.
- **Necessary interactions:** None required for the base 9-24 month test.
- **Falsification criterion:** No OOS improvement over the futures-no-change
  and random-walk benchmarks on current-regime data.
- **Key risks:** The 9-24 month verified horizon is far longer than
  Commodity's current 1-session target -- another horizon-mismatch risk,
  though a smaller one than H1's; the mean-reversion/calendar-spread version
  is unverified and should not be relied on without independent replication.
- **Recommended next action:** Treat the 9-24 month spread-forecast result as
  a candidate for a SEPARATE, longer-horizon experiment track, not a
  same-track competitor to H2/H3. Independently verify the mean-reversion
  calendar-spread claim (author/citation unconfirmed in this pass) before
  using it for anything.

---

## H5 -- Raw global LNG price-level transmission (H-GLOBAL-LNG-1's simplest form, H1a in its own ladder)

- **Economic mechanism:** TTF/JKM price levels or the TTF-JKM spread, used
  directly (without the conditioning interactions in H1 above) as predictors
  of Henry Hub.
- **Prior evidence:** Weakest in the portfolio. `loureiro_inchauspe_aguilera_2023`
  explicitly rejects a simple price-levelling/arbitrage read of LNG-flow data;
  no reviewed source demonstrates OOS forecast content from raw global price
  levels for Henry Hub specifically.
- **Target / Horizon:** Same ambiguity as H1, likely weeks-to-months at best.
- **Candidate inputs:** TTF, JKM raw price levels/spread.
- **PIT requirements:** JKM leans UNSUITABLE (licensing); TTF
  PIT_POSSIBLE_WITH_WORK.
- **Baseline/control:** Frozen US-only comparator (matches H-GLOBAL-LNG-1's
  own ladder step B).
- **Expected direction:** Not well-specified without the conditioning
  variables -- this is precisely why H-GLOBAL-LNG-1's own note already treats
  this as the weakest, most generic version of the hypothesis.
- **Necessary interactions:** None (that is the point of this version, and
  also its weakness).
- **Falsification criterion:** As per H-GLOBAL-LNG-1's own ladder.
- **Key risks:** Most likely to produce a spurious-correlation-driven false
  positive precisely because it lacks the conditioning that makes the
  mechanism economically coherent.
- **Recommended next action:** Retain only as the required baseline
  comparator inside the H1 test ladder (as H-GLOBAL-LNG-1's own note already
  specifies) -- do not treat this as a standalone hypothesis worth testing in
  isolation.

---

## H6 -- Regime/volatility-state conditioning overlay (not a standalone directional signal)

- **Economic mechanism:** Rather than forecasting the sign/magnitude of the
  next-session return, use observable state variables (LNG-terminal outage
  status, EU storage-vs-norm extremity, Strait-of-Hormuz-type disruption
  flags) to flag periods of elevated volatility / regime change, informing
  risk sizing and model-selection rather than direction.
- **Prior evidence:** Strong explanatory support that natural-gas forecasting
  is genuinely regime-dependent: `baumeister_huber_lee_ravazzolo_2024`
  documents that the best-performing MODEL CLASS itself changes across four
  historical regimes; `farag_ruhnau_2026` and `szafranek_papiez_rubaszek_smiech_2023`
  document sharp, event-driven connectedness collapses and rebounds; the live
  2026 Strait-of-Hormuz/Qatar episode is a real-time illustration.
- **Target:** Realised volatility / regime indicator, not the price-return
  target itself.
- **Horizon:** Event-driven, days to weeks.
- **Candidate inputs:** LNG terminal outage/force-majeure notices (GIE
  IIP/REMIT -- flagged CURRENT_ONLY_NOT_BACKTESTABLE pending a systematic PIT
  feed), EU storage-vs-norm extremity, a documented geopolitical-event flag.
- **PIT requirements:** Weakest in the portfolio for the outage/event
  component specifically (see data-feasibility-map.csv); stronger for the
  storage-based component.
- **Baseline/control:** Constant-volatility / unconditional model.
- **Expected direction:** Not applicable (state-conditioning, not directional).
- **Necessary interactions:** By construction, this IS the interaction
  layer for other hypotheses (H1, H2, H3) rather than a competing standalone
  signal.
- **Falsification criterion:** No improvement in conditional-coverage/volatility-forecast
  accuracy, or no improvement in the OOS performance of H1-H4 when the
  regime flag is added as a conditioning variable.
- **Key risks:** A systematic, PIT-archived outage/event feed does not appear
  to exist off-the-shelf (this review could not confirm one); building one is
  itself a data-engineering project, not a data-acquisition task.
- **Recommended next action:** Lowest near-term priority as a standalone
  build; revisit as an ENHANCEMENT to H1's interaction design once H2/H3 have
  established whether the underlying return-forecasting layer works at all.

---

## Summary ranking table

| Rank | ID | One-line mechanism | Horizon match to current V1 target | PIT readiness | Recommended sequencing |
|---|---|---|---|---|---|
| 1 | H2 | US storage-change surprise vs consensus | Excellent (1 session) | PIT_READY / PIT_POSSIBLE_WITH_WORK | Test first |
| 2 | H3 | Weather-forecast revision (not level) | Good (2-7 days) | PIT_POSSIBLE_WITH_WORK | Test second |
| 3 | H1 | EU storage x US LNG utilisation (H-GLOBAL-LNG-1, refined) | Poor at 1 session; good at weekly/monthly | PIT_POSSIBLE_WITH_WORK; JKM leg costly | Re-horizon before testing; test third |
| 4 | H4 | Futures-curve / spot-futures spread | Poor at 1 session; good at 9-24 months | PIT_READY (raw data); series-construction risk | Separate longer-horizon track |
| 5 | H5 | Raw global LNG price-level transmission | Same issue as H1, weaker evidence | Same as H1 | Baseline comparator only, not standalone |
| 6 | H6 | Regime/volatility-state overlay | Not directional | Weakest (event feed gap) | Enhancement layer, not a first test |
