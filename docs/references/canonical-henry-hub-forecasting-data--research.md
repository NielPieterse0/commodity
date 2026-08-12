# Independent Research Report — Canonical Henry Hub Forecasting Data, Semantics & Execution

**Document ID:** EXT-RES-2026-001 (proposed; repo ID scheme unverifiable — see §0)
**Version:** 1.0 | **Date:** 2026-08-12 | **Status:** Draft for adoption
**Author:** External Research Consultant (independent)
**Client repo:** NielPieterse0/commodity
**Scope:** Data provenance, futures semantics, point-in-time fundamentals, weather-forecast vintages, positioning, feature/target design, and execution realism for a Henry Hub forecasting research programme.
**Non-scope:** Model implementation, live capital deployment, tax/legal advice.

> **Repository adoption note (2026-08-12):** This document is external research input, not authoritative repository evidence. Section 0 is obsolete relative to the live local repository and MUST NOT be used as governance evidence. The Databento recommendation is not adopted in the current slice. Adopted findings must be re-expressed through authoritative repo config, code, tests, or decision records.

---

## TL;DR
- **Canonical futures data:** Adopt **Databento GLBX.MDP3** (per-contract NYMEX NG, history from 2010-06-06) as `market_canonical`; keep `NG=F` (Yahoo) bootstrap-only. A genuinely free, backtest-grade, expiry-aware source that preserves open interest does not exist; EIA RNGC1–4 is a free deep-history cross-check only (and stopped updating 2024-04-05).
- **Roll/adjustment:** Store per-contract raw data in the data layer; set `roll_method: "volume_oi_crossover"` and `adjustment_method: "none_stored_raw"`, deriving any adjusted/continuous series in the feature layer. Ratio back-adjustment is specifically unsafe for NG.
- **Execution & target:** MNG micro futures are thin and friction dominates any daily-horizon edge; both Saxo and IBKR list NG/MNG, but **futures ARE PRIIPs-scoped (KID required — not exempt)**. The predictability literature says target **volatility and direction**, not daily returns.

---

## 0. Repository Governance Reconnaissance

**FACT.** Via the GitHub API: `NielPieterse0/commodity` **exists but is private and empty** (created 2026-08-12T12:55:44Z, size 0; API returns "Git Repository is empty"). `NielPieterse0/college` **exists but is private** (Python, created 2026-08-08, last push 2026-08-12). Neither is publicly readable. The account also holds private `vox-governance` ("Governance, document management, release control… for the company document library") and private `new-project-template` ("Canonical reusable repository code-as-docs governance and bootstrap template"), which strongly imply an established governance convention exists — but it **cannot be inspected**.

**INFERENCE.** Because the target repo could not be read, the precise governance/authority conventions (SKILL.md/AGENTS.md/CLAUDE.md, document-ID schemes, `config/data_sources.json` contents, EXP-001-style registers, Ridge/naive/Kronos-mini baseline configs, Saxo-as-unapproved-candidate) **cannot be verified**. Every reference in this report to `config/data_sources.json → market_canonical`, `roll_method`, `adjustment_method`, `NG=F` bootstrap tiering, the data→features→forecasts→evaluation→signal-policy→simulation→execution pipeline, and named baselines is taken **from the client's brief, not from repo observation**, and is labelled accordingly. This report therefore uses a **clearly-labelled generic controlled-document structure**; governance alignment is an explicit DECISION-NEEDED (see Open Questions). Confidence: HIGH on repo existence/state; LOW on governance detail. **No repo contents were fabricated.**

---

## Decision Register

| # | Decision | Value to set | Authoritative owner/file | Confidence | Evidence basis |
|---|----------|-------------|--------------------------|-----------|----------------|
| D1 | Canonical futures source | **Databento GLBX.MDP3** (raw per-contract) | `config/data_sources.json → market_canonical` | HIGH | Databento catalog/docs |
| D2 | NG=F status | remain **bootstrap-only** | `data_sources.json` | HIGH | Yahoo continuous opacity |
| D3 | Roll method | `volume_oi_crossover` | `roll_method` | HIGH | GSCI/BCOM & industry practice |
| D4 | Adjustment | `none_stored_raw` (derive in features) | `adjustment_method` | HIGH | NG seasonality/near-zero spreads |
| D5 | Storage as-of rule | knowable **Thu 10:30 ET** (+holiday shifts) | features/provenance layer | HIGH | EIA schedule |
| D6 | Weather forecast archive | **Open-Meteo Historical Forecast API** (primary); NOAA GFS on AWS + GEFS reforecast (fallback) | new data source | MED-HIGH | Open-Meteo/AWS/NCAR docs |
| D7 | CFTC series | **Disaggregated, Managed Money**, NYMEX "NATURAL GAS" **CFTC code 023651** | features layer | HIGH | CFTC |
| D8 | Primary target | **next-day realized volatility + settlement direction** | forecasts/evaluation | MED-HIGH | predictability literature |
| D9 | Execution venue | **defer**; MNG thin; friction-decisive; IBKR > Saxo | execution adapter | HIGH | CME/TradingView volume |

---

## 1. Canonical Henry Hub Futures History

**FACT — free CME continuous feeds are gone.** Nasdaq Data Link's free **CHRIS** continuous-futures database is **deprecated and no longer updated** (maintainer notice: "the CHRIS database has been deprecated and is no longer updated on Nasdaq Data Link… we do not currently have an alternate data feed"); SRF is similarly curtailed. Any pipeline assuming these is broken as of 2026.

**FACT — Databento GLBX.MDP3 (recommended canonical).**
- **Coverage:** history from **2010-06-06 UTC**. Data prior to **2017-05-21** is reconstructed from CME FIX flat files (no nanosecond capture timestamps); later data is hardware-timestamped at Aurora DC3.
- **Fields:** preserves **per-contract identity** (raw venue symbols, e.g. NGF24), **volume** (in OHLCV), and **open interest + official settlement in the `statistics` schema** (these are NOT in OHLCV bars — a backtest must ingest `statistics` for settlement/OI, `definition` for expiry metadata, and `ohlcv-1d` for OHLC+volume).
- **Licensing:** **no CME exchange licence fee is required for historical-only (T+1) data for a single, non-redistributing researcher**; you pay only Databento's metered per-GB usage. New users receive **$125 in free data credits**, applicable to historical data or the first month of a subscription (Databento: "$125 in free data credits for new sign-ups"); a daily NG dataset is trivially small, so the effective cost is near zero.
- **Flat plan (optional, unnecessary here):** a CME "Standard" plan at **$179/month**, introduced when "usage-based pricing for CME **live** data has been discontinued as of… April 16, 2025." Metered per-GB pricing continues to apply to **historical** data, which is all this project needs.

**FACT — EIA RNGC1–4 (free cross-check only).** Free, public-domain via **EIA API v2** (IDs `NG.RNGC1.D`…`NG.RNGC4.D`; route `natural-gas/pri/fut`), daily, contracts 1–3 from **1994** and contract 4 from **1993**. But these are **constant-maturity continuous "Contract N" series** (not per-expiry; no OI) and EIA **stopped updating them after 2024-04-05** ("Futures prices after April 5, 2024, are not available"). Use for deep-history sanity checks on front-month settlement level, not as canonical.

**FACT — FRED DHHNGSP** is Henry Hub **spot** (physical), a fundamentals input, not a futures canonical.

**Why Yahoo NG=F is inadequate as canonical.** It is an opaque continuous stitch: no disclosed roll rule, no per-contract expiry identity, no open interest, subject to silent revision and survivorship in the stitch. It cannot support a reversible roll decision or backtest provenance. **Keep bootstrap-only (D2).**

**RECOMMENDATION (D1).** Set `market_canonical` to **Databento GLBX.MDP3**, ingesting `ohlcv-1d` + `statistics` + `definition` per contract. Primary = Databento; fallback cross-checks = EIA RNGC1–4 (pre-2024-04) and CME daily settlement bulletins. **A genuinely free option cannot support credible backtest evidence** (no OI, no expiry identity, or discontinued); Databento's metered historical tier makes the paid path effectively near-zero for daily data, so a paid tier is not a real obstacle. **This is the decision that unblocks backtest evidence.**

---

## 2. Roll & Continuous-Series Methodology

**FACT — NG contract (NYMEX Rulebook Ch. 220).** 10,000 MMBtu; tick $0.001/MMBtu = **$10/contract**; physically delivered at Henry Hub; **last trading day = third business day prior to the first calendar day of the delivery month**; if that day is a declared holiday, expiry moves to the immediately prior business day; listed for many consecutive months. E-mini **QG** = 2,500 MMBtu ($12.50/tick, cash). **MNG** = 1,000 MMBtu ($1/tick, financially settled, terminates one business day before NG).

**FACT — NG-specific back-adjustment hazards.** Strong seasonality (winter premium), deep contango/backwardation, and historically small/near-zero (occasionally crossing) calendar spreads make **ratio (proportional) back-adjustment hazardous**: dividing by a near-zero or sign-crossing spread produces exploding/garbage adjusted prices and corrupts computed returns. Difference (Panama) adjustment avoids blow-ups but distorts absolute levels and long-horizon return arithmetic.

**RECOMMENDATION (D3/D4).** Store **per-contract raw** OHLCV + OI + settlement in the **data layer**. Derive any continuous/adjusted series in the **feature layer**, never the data layer, so the decision stays reversible. Set `roll_method: "volume_oi_crossover"` (roll when the next contract's volume **and** open interest exceed the front, typically ~3–7 sessions pre-expiry — tracks liquidity migration, avoids delivery risk; aligns with GSCI/BCOM-style windowed practice). Set `adjustment_method: "none_stored_raw"`. Compute **within-contract returns** (never across the roll gap) to avoid roll-gap contamination, and build ranked-contract series **M1…M12** for term structure. Term-structure features: M1–M2 spread, calendar spreads, the **March/April "widow-maker" spread**, summer/winter spread, slope, curvature, seasonality-adjusted slope.

---

## 3. Point-in-Time Fundamentals

**FACT — WNGSR.** Released **Thursdays 10:30 a.m. ET**, data as-of the prior **Friday** (≈6-day lag). Holiday weeks shift per EIA's published exception calendar (e.g., to Friday after July 4, or **Wednesday 12:00 p.m.** around Thanksgiving/Christmas/New Year). **Unscheduled revisions ≥10 Bcf** (regional or national) are released in a special WNGSR between **2:00–2:10 p.m. ET** after 1:00 p.m. notification; working/base-gas **reclassifications** fold into the next regular release. Periodic **sample reselection** (e.g., Nov 2024) triggers blended revisions across ~8 weeks. **No native point-in-time vintage archive exists.**
**FACT — Production (EIA-914 / Natural Gas Monthly).** Monthly, ~2-month lag, and **materially revised** after initial publication; STEO provides forward estimates.
**FACT — Power burn.** EIA-930 hourly grid monitor (near real-time, revised); Electric Power Monthly / EIA-923 (lagged, revised).
**FACT — LNG feedgas / pipeline flows.** No free, reliable historical vintage feed; Genscape/Wood Mackenzie/Criterion/PointLogic are paid. Free public pipeline EBB scraping is legally/practically fragile and incomplete.

**RECOMMENDATION (D5).** Because no vintage archive exists: **build a vintage store going forward** (snapshot every release with a capture timestamp) and, for historical backtests, use **publication-date-lagged alignment** (align each datum to its actual publication timestamp, never its as-of date). This is explicitly second-best — quantify and disclose the residual look-ahead risk. As-of alignment rule table:

| Series | Knowable/usable on prediction date T when… |
|--------|--------------------------------------------|
| EIA storage (WNGSR) | ≥ Thu 10:30 ET of release week (holiday-shifted) |
| Dry gas production (914/NGM) | ≥ actual monthly publication date (~2-mo lag) |
| Power burn (EIA-930 hourly) | ≥ hourly publication (near real-time; treat as revised) |
| LNG feedgas | only if a timestamped feed is captured live |
| Henry Hub spot (DHHNGSP) | ≥ next-day publication |

---

## 4. Historical Weather Forecast Vintages (hardest item)

**FACT — the ERA5 trap.** ERA5 (Open-Meteo Historical Weather API, 1940→present) is **reanalysis, not forecast**. Using it as a "forecast" injects look-ahead bias because it assimilates observations unavailable at forecast issue time. **Must not be used as a forecast vintage.**
**FACT — Open-Meteo Historical Forecast API.** Archives **actually-issued** forecasts: GFS 2 m temperature from **March 2021**, most models from **Jan 2024**; JSON, no API key, **CC BY 4.0**, response times <10 ms. The Previous-Runs API returns fixed lead-time offsets (day 1–7) from Jan 2024; the Single-Runs API preserves original run structure. Strongest low-effort, vintage-correct candidate.
**FACT — NOAA GFS on AWS (`noaa-gfs-bdp-pds`) + NCAR RDA.** Continuously updated 0.25° GFS on AWS (free, no egress); NCAR RDA d084001 archive spans **2015-01-15 → present** (RDA stops updating early 2026 in favour of AWS). Cycles **00/06/12/18z**, forecasts to **16 days**, GRIB2. **GEFS reforecast v12** provides model-consistent history **2000–2019**. Heavier engineering (GRIB2, subsetting via NOMADS grib filter / THREDDS-NCSS).

**RECOMMENDATION (D6).** Primary = **Open-Meteo Historical Forecast API** for population-weighted HDD/CDD at daily cadence (fast, licensed, vintage-correct from 2021). Fallback / long history = **NOAA GFS on AWS + GEFS reforecast**. Needed vintages: **day 1–15**, plus **6–10** and **8–14 day** aggregates. **Issue-time alignment rule:** for a US session decision, the **00z cycle** (published ~05:00–05:30 ET) is reliably knowable; the **06z** (~11:00–11:30 ET) is knowable for an afternoon decision. Never use a cycle whose publication timestamp postdates your prediction timestamp. **Regions:** aggregate to **EIA's five storage regions** (East, Midwest, Mountain, Pacific, South Central incl. salt/nonsalt) using **population- or gas-consumption weights**; compute **gas-weighted degree days (GWDD, base 65°F)**. The predictive feature is the **forecast surprise** (vintage-over-vintage change in forecast HDD/CDD), not the level.

---

## 5. CFTC Positioning

**FACT.** Henry Hub NG appears in both the **Legacy** (Non-Commercial/Commercial/Non-Reportable) and **Disaggregated** (Producer/Merchant/Processor/User, Swap Dealers, **Managed Money**, Other Reportables) reports, in futures-only and futures-and-options-combined variants. Released **Fridays 3:30 p.m. ET**, as-of the prior **Tuesday** (3-day lag; firms report Wednesday, CFTC verifies for Friday). Federal holidays shift the release to the next business day (e.g., the Dec 2018 holidays used Monday data with Friday publication). The **2018–19 government shutdown** created a backlog/gap. Bulk historical files (annual; disaggregated back to 2006) and the Socrata `publicreporting` API are free.

**RECOMMENDATION (D7).** Use **Disaggregated, Managed Money net** for the NYMEX Henry Hub "NATURAL GAS" contract — **CFTC contract code 023651** (combined futures-and-options variant preferred, to capture options hedging). **Note:** do **not** use code 023391, which is the ICE "NAT GAS ICE LD1" 2,500-MMBtu contract, not NYMEX Henry Hub. Features (not raw levels): net position, net as % of open interest, 3-year rolling z-score/percentile, weekly change, positioning extremes (crowding/reversal hypotheses). Alignment: knowable only from **Friday 3:30 p.m. ET** (holiday-shifted). Honestly, this is a **weak, lagged, low-frequency secondary feature**.

---

## 6. Natural-Gas Domain / Feature Evidence Review

**FACT — storage surprise.** Peer-reviewed evidence documents an **inverse relation between the storage-change surprise (actual − expected) and futures price change on announcement day**, with a larger response post-2005 as production scaled (ScienceDirect: Ramaprasad et al.; Linn & Zhu). The canonical microstructure reference is **Gay, G.D., Simkins, B.J. & Turac, M. (2009), "Analyst forecasts and price discovery in futures markets: The case of natural gas storage," *Journal of Futures Markets* 29(5): 451–477, DOI 10.1002/fut.20368**. Corroborating: **Prokopczuk, Wese Simen & Wichmann (2021), "The Natural Gas Announcement Day Puzzle," *The Energy Journal* 42(2)** — "More than 50% of the annual return is earned on these [EIA storage announcement] days." The consensus/analyst survey (Bloomberg/Reuters/Dow Jones) is the surprise benchmark; its availability is itself a research problem, and a **model-implied expectation** is the practical substitute.
**FACT — volatility is far more forecastable than returns.** The GARCH/HAR/GARCH-MIDAS literature (Sadorsky; Lv & Shan; augmented-GARCH storage/maturity/weather studies; GARCH-MIDAS with extreme-weather indicators) shows NG **volatility** is strongly forecastable (persistence, clustering, storage-announcement and weather effects; volatility is elevated on Thursdays), while **daily NG returns are near-efficient** — very low out-of-sample R², sign accuracy barely above 50%.

**Evidence-graded driver table:**

| Driver | Mechanism | Horizon | Evidence | Feature construction |
|--------|-----------|---------|----------|----------------------|
| Weather forecast surprise | demand shock | 1–15 d | **Strong** | Δ forecast GWDD, vintage-over-vintage |
| Storage surprise vs consensus | supply/demand signal | event day | **Strong** | actual − expected Bcf |
| Storage vs 5-yr avg | inventory buffer | weeks–months | Medium | deviation z-score, days of supply |
| Dry gas production | supply | months | Medium | level + momentum, by basin (Appalachia/Permian/Haynesville) |
| LNG feedgas | structural demand | weeks–months | Medium-strong (post-2016 regime) | feedgas level, terminal outages/ramps |
| Power burn / coal-gas switch | demand | days–weeks | Medium | burn, gas-coal heat-rate spread |
| Term structure | storage/expectations | weeks | Medium | M1–M2, calendar, Mar/Apr spread |
| Seasonality | injection/withdrawal | intra-year | **Strong** | month/week dummies, expiry-week |
| Volatility persistence | clustering | days | **Strong** | realized vol, HAR/GARCH, implied vol |
| Positioning | crowding/reversal | weeks | Weak | Managed Money z-score |
| Cross-asset | substitution/macro | days–weeks | Weak-medium | WTI, TTF/JKM, USD, rates |
| Extreme-weather regime | Uri, polar vortex, freeze-offs, hurricanes | event | **Strong on vol** | regime flags |

**RECOMMENDATION.** Build features from an economic hypothesis, not a zoo. The literature's message drives target selection: **direct daily return prediction is a near-dead end; volatility and direction-of-volatility are tractable.**

---

## 7. Forecast-Target Design

**FACT/INFERENCE.** Next-session return (current bootstrap) has the worst signal-to-noise. Weekly and storage-report-conditional event returns carry marginally more structure. Realized volatility and curve/spread movements are the most learnable.

**RECOMMENDATION (D8).** Canonical **primary target = next-day (and weekly) realized volatility** (evaluated by **QLIKE**), plus **settlement-direction** as a secondary directional target (evaluated against a proper seasonal/AR baseline, not a coin flip). Secondary targets: 2–5-day and weekly returns; M1–M2 spread change; storage-event-conditional returns; quantile/distributional forecasts (**pinball loss**). Authoritative metrics: OOS R²/RMSE vs naive, **Diebold–Mariano**, directional accuracy vs seasonal baseline, pinball loss (quantiles), QLIKE (vol), and Sharpe **after realistic friction** (§8). **Anti-data-mining protocol:** walk-forward with **purged/embargoed CV** (overlapping horizons), **deflated Sharpe ratio**, and **pre-registration of hypotheses in the repo's decision records** before testing.

---

## 8. Execution Reality (Norwegian retail client)

**FACT — MNG specs & liquidity.** MNG = 1,000 MMBtu, **$1/tick**, financially settled, listed 24 consecutive months, terminates one business day before NG. Liquidity is **thin**: TradingView's MNG1! front-month page shows volume of **3.09 K** and open interest of **6.31 K** (point-in-time snapshot) — orders of magnitude below NG (~400k daily trades, ~1.7M OI). Thin books imply wide spreads and slippage at micro size.
**FACT — PRIIPs correction.** Contrary to a common assumption, **futures ARE PRIIPs-scoped**: CME produces KIDs for its futures for EU/UK retail ("members… are required to provide a KID prior to offering, selling or otherwise arranging a transaction"), as do OCC and ICE. A KID must be available before an EEA retail client trades — **not an exemption**. ESMA leverage caps apply to **CFDs**, not futures — so futures are the cleaner instrument regulatorily, but the KID requirement is real and must be satisfied by whoever offers the product.
**FACT — Saxo.** Lists CME/NYMEX futures; per-contract commissions with a minimum ticket; **OpenAPI (REST) + FIX** support futures and a SIM environment; account tiers (Classic/Platinum/VIP) affect commission. Exact MNG availability and instrument UICs must be confirmed in-platform.
**FACT — CME market data.** Non-professional CME/NYMEX Globex Level-1 is roughly **$2–$15/month per exchange** depending on vendor; professional ≈ **$140/exchange/month**.

**INFERENCE — friction is decisive.** For one MNG round turn: commission (~$0.50–$1.50/side typical retail micro) + exchange/NFA/regulatory fees + spread/slippage (≥1 tick = $1, likely more given the thin book) + rollover. On ~1,000-MMBtu notional (~$3,000 at $3/MMBtu), a few dollars of all-in friction is **~0.1–0.3% of notional per round turn** and a meaningful fraction of a typical daily ATR at micro size. A daily-horizon return edge almost certainly does **not** survive this.

**RECOMMENDATION (D9).** Keep **Saxo an unapproved candidate**; do execution research last. Prefer **IBKR (Ireland entity)** as the realistic primary for a Norwegian retail client (deeper CME futures access, transparent low commissions, clear market-data fees). If live trading proceeds, trade **low-frequency NG-relative signals (weekly/vol targets)**, not daily micro scalps, because friction kills daily edges. **Not tax advice:** Norwegian reporting obligations apply and should be reviewed separately.

---

## Revised Recommended Work Sequence (critical path)
1. Set `market_canonical` = Databento GLBX.MDP3; ingest raw per-contract (`ohlcv-1d`+`statistics`+`definition`) — **D1**. →
2. Implement roll/adjustment in the **feature** layer — **D3/D4**. →
3. EIA point-in-time alignment + start the forward vintage store — **D5**. ‖ (parallel) CFTC Managed-Money features (code **023651**) — **D7**. →
4. Weather forecast vintages via Open-Meteo (GWDD, forecast surprise) — **D6**. →
5. Feature library from §6 hypotheses. →
6. Baselines (naive/seasonal/Ridge) on **volatility + direction** targets — **D8**. →
7. Only then additional models (e.g., Kronos-mini). →
8. Saxo/MNG execution research + SIM — **D9**.

**Critical path** is 1→2→3/4→5→6. Execution (8) is **off** the research critical path and should not gate model work.

---

## Open Questions / Decisions Needed From Client
- **Governance access:** grant read access to `commodity`/`college` so the document-ID scheme, `config/data_sources.json`, decision-record format, and baseline configs can be verified and this report re-issued in-convention. (Currently unverifiable — §0.)
- **Budget:** confirm willingness to fund Databento metered historical usage (near-zero for daily; covered by $125 credit) vs the $179/mo flat plan (unnecessary for daily historical).
- **Consensus data:** is a paid storage-consensus feed (Bloomberg/Reuters/Dow Jones survey) available, or must a model-implied expectation be the surprise benchmark?
- **Live-trading intent:** is live execution actually in scope now, or research-only? (Determines whether §8 gates anything.)
- **Compute appetite:** GFS GRIB2 pipeline vs Open-Meteo-only for weather vintages.
- **CFTC variant:** confirm futures-only vs futures-and-options-combined for the Managed-Money feature.

---

## Evidence Appendix (selected; reliability grade)

| Source | Publisher | Type | Grade |
|--------|-----------|------|-------|
| NYMEX Rulebook Ch. 220; Henry Hub / Micro HH contract specs & fact card | CME Group | Primary | HIGH |
| GLBX.MDP3 catalog, metered-pricing docs, CME pricing blog (Apr 16 2025), licensing FAQ | Databento | Primary | HIGH |
| WNGSR schedule & holiday exceptions; IR site; RNGC1–4 pages; API v2; 2005 revision policy; 2024 sample reselection | EIA / govinfo | Primary | HIGH |
| COT reports (Disaggregated/Legacy), historical special announcements, contract-code listings | CFTC | Primary | HIGH |
| Historical Forecast API / Previous-Runs / features & licence (CC BY 4.0) | Open-Meteo | Primary | HIGH |
| `noaa-gfs-bdp-pds` registry; NCAR RDA d084001; NCEI GFS | AWS / NCAR / NOAA | Primary | HIGH |
| CHRIS deprecation notice | Nasdaq Data Link / GitHub issue | Secondary | MED |
| Gay/Simkins/Turac 2009 (DOI 10.1002/fut.20368); Prokopczuk et al. 2021 (Energy Journal 42(2)); Linn & Zhu; augmented-GARCH & GARCH-MIDAS vol studies | JFM / Energy Journal / ScienceDirect / MDPI | Primary literature | HIGH |
| PRIIPs/KID scope for futures | CME / Schwab / Eurex | Primary | HIGH |
| MNG liquidity snapshot (vol 3.09K / OI 6.31K) | TradingView | Secondary | MED (point-in-time) |
| CME non-pro market-data fees | Kinetick / Insignia / CME fee list | Secondary/Primary | MED-HIGH |

*Prepared as a controlled IP deliverable. All numeric/date claims are sourced above; where current status could not be independently re-verified within budget it is flagged in-line. Governance alignment with the client repo is explicitly unverified pending read access (§0).*