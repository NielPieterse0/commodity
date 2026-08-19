# External Research Audit: The "Commodity" Natural-Gas Quantitative Research Programme

*Independent external review. All programme materials treated as hypotheses, not authority. Full text was read where legally accessible; abstract/secondary-only sources are flagged explicitly.*

## TL;DR
- **H-GLOBAL-LNG-1 is SUPPORTED WITH REVISION as a conditional economic mechanism but NOT ESTABLISHED as a forecasting edge** — the programme's own seed paper (Rubaszek & Szafranek 2025) concludes the European crisis affected the U.S. market only "marginally" and that "EU and US natural gas markets evolve independently," and the most current spillover study (Farag & Ruhnau 2026) shows gas-market transmission is dominated by *contemporaneous* (non-tradable) spillovers.
- **The programme is targeting the wrong horizon.** The strongest real-time forecasting evidence (Baumeister et al. 2026) finds Henry Hub is beatable versus a no-change benchmark at monthly-to-2-year horizons but is essentially a random walk at the near/daily horizon — exactly consistent with V1's null result. Storage surprises, weather-forecast *revisions*, and curve state are better-supported signals than the LNG-transmission channel.
- **Trading is VIABLE WITH CONDITIONS, but MNG is the wrong primary instrument.** CME Henry Hub futures are accessible to a Norway resident via Saxo and Interactive Brokers, but Micro Henry Hub (MNG) is far too thin (open interest ~6.3K; daily volume ~3.1K) versus standard NG (futures ADV ~650K–710K/day in late 2025); MNG belongs in simulation/sizing, not as the execution vehicle for a few-tick edge.

## Key Findings
1. **U.S. and global gas markets are structurally distinct; there is no transoceanic price convergence.** Loureiro, Inchauspe & Aguilera (2023) find "outside of Europe, there is no clear evidence of gas price convergence" and that "the increase in LNG trade has not yet been sufficient to create fully integrated transnational markets." Europe and Asia are now tightly linked (IEA: TTF–JKM correlation 0.955 in 2025), but the U.S.–Europe link is weak and conditional.
2. **The programme overstated its own supporting evidence.** It cited Rubaszek & Szafranek (2025) as supporting future U.S.–EU dependence; the paper's headline conclusion is the opposite for the present regime.
3. **Transmission is largely contemporaneous, not lead-lag.** Farag & Ruhnau (2026): "Contemporaneous spillovers dominate return and volatility transmission, even during crises." This is fatal to naive spread/spillover *trading* but not to conditional forecasting.
4. **Best-supported forecast signals are storage surprises, weather-forecast revisions, and curve state** — all with cleaner PIT feasibility than the LNG channel.
5. **V1's null result is expected, not anomalous** — daily Henry Hub returns are near-random-walk in the literature.
6. **Execution is real but liquidity-constrained** — standard NG, not MNG, is the practical instrument.

## Details

### Deliverable B — Literature Review

**U.S. price formation.** The modern reference chain is Rubaszek, Uddin & Szafranek (2021, *Energy Economics* 103:105526, Bayesian SVAR of supply/demand/inventory shocks) and Rubaszek & Uddin (2020, *Energy Economics* 87:104713), which shows underground storage tightness changes U.S. market dynamics *nonlinearly* via a threshold model — direct support for regime/state-conditional modelling. Rubaszek & Szafranek (2025, *Int. Economics and Economic Policy*, DOI 10.1007/s10368-024-00636-6, read in full, open access) extends the SVAR to EU–US trade and concludes: "a shock even as major as the European energy crisis has only marginally affected the US natural gas market, thus confirming the results from the literature that the EU and US natural gas markets evolve independently." This is the single most important qualification to H-GLOBAL-LNG-1.

**Forecasting.** Baumeister, Korobilis & Lee, "Forecasting Natural Gas Prices in Real Time" (NBER WP 33156; *Journal of Applied Econometrics* 2026, DOI 10.1002/jae.70018) is the gold-standard real-time study: using assembled historical vintages, "considerable reductions in mean-squared prediction error relative to a no-change benchmark can be achieved in real time for horizons of up to 2 years," best delivered by a six-variable Bayesian VAR of fundamentals. Crucially, at the nearest horizon the most recent daily observation (i.e., near random walk) is the best forecast — daily-horizon edges are hard. Consistent with this, the futures-predictability literature ("Are natural gas spot and futures prices predictable?") finds "almost all of our models... do not perform any better than our benchmark random walk model." The ML literature (e.g., MDPI *Energies* 2021) reports high accuracy but relies on k-fold cross-validation on time series (look-ahead leakage) and price-level fitting; it is inadmissible as evidence of genuine forecastability.

**European connectedness.** Papież et al. (2022, *Resources Policy* 79:103029, abstract + verified secondary text): European connectedness is high and rising since 2015, with TTF and German NCG as net transmitters. Szafranek et al. (2023, *Resources Policy* 85:103917): connectedness "declined markedly after the Russian invasion," driven by UK NBP divergence — connectedness is regime-dependent and breaks under stress. Farag & Ruhnau (2026, *Energy Economics* 154:109115, abstract/highlights + econstor working-paper version; published text paywalled): "Contemporaneous spillovers dominate return and volatility transmission, even during crises," and "pipeline congestion, especially on BBL, significantly weakens return and volatility connectedness."

**Global integration.** Loureiro, Inchauspe & Aguilera (2023, *Journal of Commodity Markets* 32:100368, abstract + verified secondary description): no transoceanic convergence; Asia and Europe converge only within their own regions; achieving true integration would require far greater LNG-trade expansion. This confirms the programme's framing that H-GLOBAL-LNG-1 must NOT be a hypothesis of unconditional global convergence.

**Volatility/extreme events.** The augmented-GARCH literature ("Asymmetric impacts of fundamentals on natural gas futures volatility," *Energy Economics*) shows volatility "is much higher on the natural gas and crude oil storage report announcement days, on Mondays and during winters," and that low storage raises volatility only in winter (higher storage raises it off-season). Markov-switching volatility models beat single-regime GARCH out-of-sample for gas. This supports event-window and regime-conditional *volatility* modelling — a more tractable target than direction.

**Institutional sources (verified against primary documents).**
- *IEA Gas Market Report Q1-2026:* "The correlation between European and Asian benchmark prices rose to a new all-time high of 0.955 in 2025" — a **TTF–JKM (Europe–Asia)** figure, not US-inclusive; Henry Hub month-ahead "rose by 50% compared with 2024 to an average of USD 3.6/MBtu." The programme's citation is accurate but must be labelled Europe–Asia, not global-including-US.
- *ACER 2026 LNG Monitoring Report:* "The United States supplied 58% of EU LNG imports in 2025," "TTF... used to price 74% of EU spot LNG trades," record 146 bcm EU LNG imports; EU 2025 gas mix "50% pipeline gas, 40% LNG... and 10% domestic." The programme's "nearly half of EU supply is LNG" slightly overstates ACER's ~40%.
- *ECB Economic Bulletin 1/2023 ("Global risks to the EU natural gas market"):* confirms EU–Asia LNG interlinkage and shows the EU–Henry-Hub correlation rising *less* than EU–JKM. Accurately characterized.
- *EIA LNG-startup scenario (Today in Energy id=64884):* "higher LNG exports in the Earlier scenario would result in lower volumes in underground storage and likely higher natural gas prices, all else being equal," with the converse for later startup. Supports the *direction* of the mechanism but is scenario analysis, not an OOS forecasting result.

### Deliverable C — Evidence Tables

**C1. Paper-level evidence**
| Citation | DOI/ID | Market | Target/Horizon | Method | Main result | Class | OOS | PIT | Supports H-GLOBAL-LNG-1 | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|
| Rubaszek & Szafranek 2025 | 10.1007/s10368-024-00636-6 | US (EU shock) | elasticities | Bayesian SVAR | EU crisis affected US "marginally"; markets independent | Structural/causal | No | Revised hist. | Contradicts strong form / Partial conditional | Retain as caution |
| Loureiro et al. 2023 | 10.1016/j.jcomm.2023.100368 | Global | convergence | Cointegration | No transoceanic convergence | Structural | No | n/a | Contradicts unconditional | Retain |
| Papież et al. 2022 | 10.1016/j.resourpol.2022.103029 | Europe | connectedness | TVP-VAR-SV | High, rising EU connectedness | Contemporaneous | No | n/a | Indirect (EU) | Test (EU block) |
| Szafranek et al. 2023 | 10.1016/j.resourpol.2023.103917 | Europe | connectedness | TVP-VAR-SV | Fell in crisis (UK) | Contemporaneous | No | n/a | Regime caution | Retain caution |
| Farag & Ruhnau 2026 | 10.1016/j.eneco.2025.109115 | NW Europe | R² connectedness | R²-decomp. | Contemporaneous dominates; congestion weakens | Contemporaneous | No | n/a | Contradicts lead-lag tradability | Retain caution |
| Baumeister et al. 2026 | 10.1002/jae.70018 | US HH | real price 1–24mo | BVAR/futures/expert | Beats no-change monthly+; daily≈RW | Demonstrated OOS | Yes | PIT-ready | Neutral | Retain — template |
| Rubaszek & Uddin 2020 | 10.1016/j.eneco.2020.104713 | US HH | dynamics | Threshold SVAR | Storage→nonlinear regime | Structural | No | Revised | Supports state-conditioning | Test |
| Augmented-GARCH | *Energy Economics* | US NG futures | volatility | GARCH-X | Report-day/winter vol | Structural/OOS(vol) | Partial | n/a | Supports vol regime | Test (vol) |
| ML gas forecasting | 10.3390/en14185782 | US spot | 1–10 day | SVM/trees CV | High-accuracy claims | Contemporaneous fit | Weak (leakage) | No | Neutral | Reject as evidence |

**C2. Driver/mechanism matrix**
| Driver | US | EU | Norway | Asia/global | Forecast evidence | Causal/expl. | PIT | Horizon | Stability | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| Storage tightness/surprise | Strong | Strong | n/a | Mod | Moderate (surprise vs consensus) | Causal | Vintage capture | Days–months | Stable | High |
| Weather forecast revision | Strong | Strong | Mod | Mod | Mod–strong (revisions>levels) | Causal | If issued vintages stored | Days | Stable | High |
| LNG utilisation/feedgas | Mod | Mod | Low | Mod | Weak–Mod | Structural | Possible w/ work | Weeks–months | Changing | Medium |
| TTF–HH spread | Weak | Strong | n/a | Strong (TTF-JKM) | Weak (contemporaneous) | Contemporaneous | PIT-ready | Days | Regime-dep. | Medium |
| Norwegian outage | Low | Strong (→TTF) | Strong | Low | Weak for HH | Causal (TTF) | Possible (GIE IIP/Gassco) | Days | Stable | Medium |
| Curve state | Mod | Mod | n/a | n/a | Moderate | Structural | PIT-ready | Days–weeks | Stable | Medium |
| CFTC positioning | Weak | n/a | n/a | n/a | Weak | Contemporaneous | Lagged PIT | Weeks | Stable | Low |

**C3. Contradiction/negative-evidence register**
| Claim | Contradictory evidence | Source | Failure mode | Disposition |
|---|---|---|---|---|
| EU crisis strongly transmits to HH | "only marginally affected the US"; markets independent | Rubaszek & Szafranek 2025 | Overstated transmission | Weaken prior |
| LNG integration = global convergence | No transoceanic convergence | Loureiro et al. 2023 | False assumption | Conditional only |
| Spillovers are tradable | Contemporaneous spillovers dominate | Farag & Ruhnau 2026 | Not lead-lag | Reject naive spread trade |
| Daily HH forecastable w/ fundamentals | Daily ≈ RW; edge at monthly+ | Baumeister et al. 2026 | Wrong horizon | Revise horizon |
| Futures predict spot | Don't beat random walk | predictability lit. | No edge | Caution |
| ML high accuracy | k-fold CV leakage on time series | MDPI 2021 et al. | Look-ahead | Reject as evidence |

### Deliverable D — Hypothesis Portfolio (ranked; candidates only, do not run)

**H1 — Storage-surprise (highest).** Mechanism: the signed EIA WNGSR change *relative to analyst consensus* reveals the hidden balance. Variable: EIA storage change minus survey median (Reuters/Bloomberg/NGI). Timing: Thursday 10:30 ET. Predicted effect: larger-than-expected build → negative front-month return over release window. Target: NG front-month event-window/next-session return. PIT: PIT-ready IF consensus captured pre-release. Falsification: no OOS predictability of the signed surprise after costs; edge only in one season without a documented winter/summer interaction.

**H2 — Weather-forecast-revision.** Mechanism: markets price issued forecasts; the *change* between issuances is the news. Variable: day-over-day revision in gas-weighted degree-day forecasts from issued vintages. Predicted effect: upward winter HDD revision → positive return. Target: NG next-session return. PIT: PIT-ready ONLY with archived issued forecasts; realized temperature is not a valid substitute. Falsification: realized temperature outperforms revisions, or no OOS edge after costs.

**H3 — Curve-state/roll-yield.** Mechanism: backwardation encodes scarcity/carry. Variable: front-to-second spread, calendar-spread slope. Target: NG return, days–weeks. PIT: PIT-ready. Falsification: no increment beyond momentum/seasonality.

**H4 — LNG-transmission (revised H-GLOBAL-LNG-1).** Ranked below H1–H3 (see Deliverable E) because transmission is conditional, slow, and largely contemporaneous.

**H5 — EU refill-pressure × U.S. LNG utilisation.** Mechanism: when AGSI storage is far below target AND U.S. liquefaction runs near capacity, EU competes for U.S. cargoes, tightening the U.S. balance. Variable: AGSI deviation × EIA feedgas utilisation. Horizon: weeks. PIT: possible with work. Falsification: interaction adds no OOS value over U.S.-only control.

**H6 — Announcement-window volatility regime.** Mechanism: volatility elevated/forecastable around storage reports and in winter. Target: realized volatility (not direction), 1–5 days. PIT: PIT-ready. Falsification: regime-switching/GARCH-X fails to beat a seasonal volatility baseline OOS.

### Deliverable E — H-GLOBAL-LNG-1 Verdict

**SUPPORTED WITH REVISION (as a conditional explanatory mechanism); NOT ESTABLISHED as a forecasting edge.**

Link-by-link: TTF/JKM shock → cargo economics is strongly supported (IEA/ACER netback logic); → U.S. export incentive → utilisation is only directionally supported and *weak as a fast channel* because 2022–2025 U.S. terminals ran near full capacity (utilisation was capacity-constrained, hence price-insensitive at the margin — a conditionality the hypothesis correctly anticipates); → storage → Henry Hub is supported by EIA scenario logic but operates at monthly-plus, not daily, horizons. The decisive problems are (a) Farag & Ruhnau (2026): transmission is dominated by contemporaneous spillovers (non-forecastable), and (b) Rubaszek & Szafranek (2025): the U.S. market moved largely independently through the EU crisis.

Required revisions: downgrade priors; reframe to weekly/monthly; make the U.S.-LNG-capacity-state interaction mandatory (transmission should appear only with spare/expanding capacity); explicitly separate contemporaneous from forecastable increments. Keep the strong falsification criteria unchanged despite the hypothesis's economic appeal: reject if the full interaction spec shows no preregistered OOS increment over BOTH the U.S.-only control AND the raw global-price control; if the increment is only contemporaneous; if it survives only in the 2021–2023 crisis slice; if it disappears under PIT vintages; or if U.S.-LNG-state variables alone (no global prices) capture the same increment (signal would be domestic, not global).

### Deliverable F — Data Feasibility Map
| Source | Variable | Geo | Freq | Revision | PIT status |
|---|---|---|---|---|---|
| CME/NYMEX | NG/MNG history, curve | US | daily/intraday | minimal | PIT_READY |
| EIA WNGSR | Storage level/change | US | weekly Thu | revised | PIT_POSSIBLE_WITH_WORK (capture vintages) |
| Survey consensus | Storage expectation | US | weekly | none | PIT_POSSIBLE_WITH_WORK (capture pre-release) |
| Open-Meteo/NOAA | Issued weather/degree-day vintages | US/EU | 1–4×/day | reissued | PIT_POSSIBLE_WITH_WORK (store at issuance) |
| EIA | LNG feedgas/exports | US | daily/monthly | revised | PIT_POSSIBLE_WITH_WORK |
| CFTC COT | Positioning | US | weekly Fri (Tue data) | none | PIT_READY (lagged) |
| ICE | TTF curve | EU | daily | minimal | PIT_READY (licensed) |
| GIE AGSI/ALSI | EU storage / LNG terminal | EU | daily | revised | PIT_POSSIBLE_WITH_WORK |
| ENTSOG | Flows/capacity | EU | daily | revised | PIT_POSSIBLE_WITH_WORK |
| Gassco/GIE IIP | Norwegian outages | NO | event | updated | PIT_POSSIBLE_WITH_WORK |
| S&P Global | JKM | Asia | daily | minimal | PIT_POSSIBLE (licensing) |
| SSB | Norwegian gas exports | NO | monthly | revised | REVISED_HISTORY_ONLY |

### Deliverable G — Trading/Execution Verdict

**VIABLE WITH CONDITIONS.**

- **Instrument facts (CME fact card, verified):** MNG = 1,000 MMBtu, tick $0.001/MMBtu = $1/contract, cash-settled, code MNG, terminates one business day before NG; NG = 10,000 MMBtu, physically delivered, tick $10/contract.
- **Liquidity is the binding constraint.** Per CME Group's Jan 5, 2026 full-year statistics release, Henry Hub Natural Gas *futures ADV* was ~708,000 contracts in December 2025 and ~655,000 in Q4 2025 (record annual futures-and-options ADV of 904,000). MNG is dramatically thinner — TradingView reports MNG volume ~3.09K and open interest ~6.31K contracts. This gap was structural from launch: Natural Gas Intelligence reported "Micro Henry Hub futures had 1.9% the open interest of the full-sized contract, with 99.8% of the micro futures open interest spread among the December 2023 through February 2024 contracts." For a signal whose edge is a few ticks, MNG's wider relative spread and shallow depth will likely erase it. **The programme's preference for MNG as the eventual instrument is not justified for a directional short-horizon strategy.**
- **Brokers.** Saxo Bank (Danish bank, serves Norway, listed CME broker) supports futures and its OpenAPI supports futures order placement (limit/stop/market, GTC/GTD/day, OCO, algo), positions and fills in real time; Classic accounts have no minimum funding. Saxo's NG futures commission is ~$3.00/contract per BrokerChooser real-money testing, plus ~$1.7/contract exchange/regulatory; the exact Norway rate and whether MNG specifically is listed must be confirmed in-platform. Interactive Brokers (fallback via IBIE) charges USD 0.85/contract for NG (confirmed against IBKR's tiered schedule and BrokerChooser: "the Natural Gas futures fee is $0.85 per contract"), plus ~$1.7/contract NFA/exchange fees, and USD 0.25/contract for MNG (symbol MHNG, from IBKR's schedule — not independently corroborated by a second named source); IBKR waives US futures real-time data at ≥USD 30/month commissions.
- **Delivery/roll.** NG is physically delivered; Saxo does not support physical delivery (auto-closes) and IBKR liquidates before delivery — a hard First-Notice-Day roll rule is mandatory.

Blockers: (1) no demonstrated edge yet (V1 null); (2) MNG liquidity; (3) PIT consensus/weather-vintage capture must be built before any backtest is valid; (4) Saxo MNG listing and Norway commissions unconfirmed from primary docs.

### Deliverable H — Repository Recommendations
- **[correctness_requirement]** Shift the primary forecast horizon from single-session daily returns to weekly/monthly, where OOS forecastability actually exists (Baumeister et al. 2026); daily targeting is contradicted by the random-walk evidence and by V1's own null.
- **[correctness_requirement]** Build storage/weather signals from PIT vintages only: store analyst consensus *before* each EIA release and issued weather forecasts *at issuance*; revised series are inadmissible as backtest evidence.
- **[correctness_requirement]** Mandatory NG roll/expiry rule before First Notice Day to avoid physical delivery.
- **[research_hypothesis]** Preregister H1 (storage surprise), H2 (weather revision), H3 (curve state) ahead of H4 (revised H-GLOBAL-LNG-1).
- **[research_hypothesis]** Reframe H-GLOBAL-LNG-1 with a mandatory U.S.-LNG-capacity-state interaction and an explicit contemporaneous-vs-forecastable test.
- **[data_requirement]** Acquire/store EIA WNGSR vintages; storage consensus; issued degree-day vintages; GIE AGSI/ALSI and ENTSOG with vintage capture; licensed JKM only if the Asia block is pursued.
- **[execution_requirement]** Default to NG, not MNG, for any live execution; use MNG only for SIM/position-sizing. Confirm MNG listing and exact Norway commission/data fees on Saxo in-platform before commitment.
- **[execution_requirement]** Build the SIM order-lifecycle proof on Saxo OpenAPI (place/fill/position/cancel/reconnect/reconcile) before requesting any live authority.
- **[future_investigation]** Volatility-target modelling (H6) as a separate track — volatility is more forecastable than direction.
- **[rejected]** Naive TTF–HH or TTF–JKM spread "spillover" trading — Farag & Ruhnau show these are contemporaneous, not lead-lag.
- **[rejected]** ML papers reporting high accuracy via k-fold CV on price levels — inadmissible as forecastability evidence.

## Recommendations (staged, with thresholds)
1. **Immediately (before any new empirical work):** Re-scope V2 away from single-session daily return prediction toward a weekly/monthly return or a volatility target. *Threshold to proceed to modelling:* a working PIT data pipeline that stores storage consensus pre-release and weather forecasts at issuance. Until this exists, no backtest is admissible.
2. **First empirical pass:** Preregister and test H1 (storage surprise) and H2 (weather revision) as the primary candidates, with a frozen U.S.-only comparator. *Threshold to continue:* a material, preregistered OOS improvement over the no-change/seasonal baseline that survives transaction costs and multiplicity controls. If not met, do not escalate to global variables.
3. **Only after a U.S.-only edge exists:** Run the revised H-GLOBAL-LNG-1 ladder with mandatory capacity-state interactions and the contemporaneous-vs-forecastable test. *Stop condition:* reject if the increment is contemporaneous only, crisis-slice only, or replicable by U.S.-LNG-state variables without global prices.
4. **Execution track (parallel, no live authority):** Complete a Saxo OpenAPI SIM order-lifecycle proof and confirm NG (not MNG) economics for a Norway account. *Threshold to request live authority:* a demonstrated net-of-cost edge in walk-forward evaluation AND a reconciled SIM execution record — both, plus human approval.
5. **Abandon now:** naive spillover-spread trading and any reliance on ML accuracy figures produced under k-fold CV.

## Caveats
- **Full text vs abstract:** Rubaszek & Szafranek (2025) was read in full (open access). Loureiro et al. (2023), Papież et al. (2022), Szafranek et al. (2023) and Farag & Ruhnau (2026) were accessed via abstract, highlights, and verified secondary/working-paper descriptions; the published Elsevier texts are paywalled — conclusions attributed to them rest on those sources and are flagged accordingly.
- **Execution specifics:** Saxo's exact Norway-resident commission and market-data fees, and confirmation that MNG specifically is listed on Saxo, could not be verified from Saxo primary documentation (rendered in-platform only) and rely partly on third-party testing (BrokerChooser). IBKR's MNG (MHNG) $0.25/contract figure comes from IBKR's own schedule but was not independently corroborated by a second named source; IBKR NG $0.85/contract is corroborated. MNG volume/OI figures are from market-data vendors (TradingView/Yahoo) and NGI, not CME's official statistics page; NG futures ADV (~655K–708K, late 2025) is from CME's own January 2026 statistics release.
- **Forecast vs realized:** All 2026 figures from EIA STEO and IEA Gas Market Reports are projections, not realized outcomes, and are labelled as such. IEA/ACER 2026 reports also contain forward-looking scenario language (e.g., Strait-of-Hormuz-closure supply shortfalls) which should not be treated as established fact.
- **Scope:** This is a literature/feasibility review; no empirical model tuning was performed, consistent with the mandate.