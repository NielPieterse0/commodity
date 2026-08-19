# Execution Feasibility -- Independent Verification Against Commodity Issue #109

Status: DRAFT / PARTIAL VERIFICATION -- see limitations below
Prepared: 2026-08-16

## Verdict

**VIABLE WITH CONDITIONS.**

The instrument and exchange infrastructure required to trade a Henry Hub
research signal exist, are well-specified, and are publicly documented. The
blocking gap is **account-level and API-level entitlement verification**,
which cannot be completed through external desk/web research and requires an
authenticated Saxo SIM session (or IBKR paper account) -- exactly the work
issue #109 already scopes as required. This independent review confirms
there is no publicly-documented shortcut around that requirement; it does not
and cannot substitute for it.

---

## 1. Exact instrument verification

**Confirmed independently, from CME Group's own product documentation:**

- `NG` (Henry Hub Natural Gas futures, NYMEX): 10,000 MMBtu per contract,
  $0.001/MMBtu tick = $10/tick.
- `MNG` (Micro Henry Hub Natural Gas futures, NYMEX): 1,000 MMBtu per
  contract (1/10 of `NG`), $0.001/MMBtu minimum tick = $1/contract,
  financially settled (no physical delivery), trades nearly 24 hours on
  Globex, and is explicitly confirmed **fungible** with E-mini Henry Hub
  Natural Gas futures and the Henry Hub Natural Gas Penultimate Financial
  futures (per CME's own MNG FAQ).
- `MNG` uses the same FIFO matching algorithm and the same dynamic
  price-fluctuation-limit (circuit-breaker) structure as `NG`.

**NOT independently confirmed in this review:**

- The exact launch/history-start date of `MNG` (relevant to whether enough
  history exists for a walk-forward backtest of adequate length -- flagged
  as a constraint in `data/data-feasibility-map.csv`).
- Whether Saxo's specific Norway-resident retail offering lists `MNG` (as
  opposed to `NG` only) as a tradable `ContractFutures` instrument. Saxo's
  public futures-trading-conditions page confirms the existence of a
  downloadable "Futures Contract Specifications" document and a
  Norway-locale site (`home.saxo/nb-no`), but the specific instrument list
  and country/account-tier restrictions are not exposed on the public
  marketing page and require an authenticated session (or the linked PDF,
  which was not machine-readable in this pass) to confirm.
- The exact Saxo UIC / futures-space identity for `MNG` or `NG`.

**Structural finding relevant to the "no accidental physical delivery"
requirement in #109:** Saxo's own public trading-conditions text states
plainly: *"With Saxo you avoid physical delivery of the underlying asset on
expiry of a futures contract, which is not supported... If futures positions
are not closed before the relevant date, Saxo will close the position on
your behalf at the first available opportunity at the prevailing market
rate."* This is a structural, broker-level fail-closed protection against the
exact risk #109 flags (accidental physical-delivery exposure) and is a
meaningful positive finding independent of instrument-level entitlement.

**Research-target -> tradable-contract mapping risk (unresolved):** No
source reviewed in this pass provides a clean, general solution to the
gap between a continuous/front-month reference series (what a forecasting
model is typically trained and evaluated against) and the exact
contract-month order actually placed with a broker. The futures-curve /
calendar-spread literature reviewed (see `evidence/driver-evidence-matrix.csv`,
row "Futures curve state") documents that continuous-series construction
embeds systematic roll effects that do not exist in a single traded
contract-month. This mapping must be resolved explicitly (documented,
deterministic roll/entry rules) before any Commodity signal is connected to
a live or paper `MNG` order -- it is a design requirement, not a data-
acquisition task.

---

## 2. Broker/API execution path

**Confirmed independently:**

- Saxo publicly documents a "Futures" product line, order-type support
  (including synthetic stop orders where the exchange itself does not
  support native stop orders), partial-fill handling (volume-weighted
  average price for market orders), and an explicit expiry/first-notice-day
  (FND) closeout policy, including cases where Saxo's own FND cutoff is
  earlier than the exchange's.
- Saxo's developer portal exposes a documented `ContractFutures` /
  `futuresspaces` reference endpoint
  (`GET /ref/v1/instruments/futuresspaces/{ContinuousFuturesUic}`), consistent
  with #109's description of Saxo OpenAPI's futures-space contract-resolution
  model.

**NOT independently confirmed in this review (requires an authenticated
session):**

- Whether a Norway-resident retail/individual account is actually
  provisioned with the `ContractFutures` legal asset type and NYMEX
  market-data rights.
- SIM/live authentication flow, order validation, submit/amend/cancel,
  fill/position streaming, rejection handling, and reconnect/idempotency
  behaviour for the specific `MNG` (or `NG`) contract.
- IBKR's equivalent for a Norway-resident account: IBKR publicly advertises
  broad CME Group futures access and has public "Campus" educational
  material specifically covering `MNG`, which is a positive general
  signal, but account-level and jurisdiction-level entitlement was not
  independently verified.

---

## 3. Real-time trading data

**Confirmed independently:** CME Group sells real-time and historical market
data for Henry Hub/Micro Henry Hub Natural Gas products through multiple
channels (low-latency direct feed, cloud/on-demand, CME DataMine historical,
REST/streaming API, licensed distributors) -- i.e., the data exists and is
commercially available in principle.

**NOT independently confirmed in this review:** The exact real-time
NYMEX/CME subscription product, retail/non-professional cost tier, and
whether it is exposed end-to-end through Saxo OpenAPI (vs. requiring a
separate direct feed such as Databento, as #109 already flags as an open
question). This is squarely an account/subscription-level fact that this
desk review cannot resolve without an authenticated broker relationship.

---

## 4. Costs and feasibility

Directionally confirmed (from CME contract specifications, not from a live
fee schedule):

- `MNG`'s smaller notional (1,000 vs 10,000 MMBtu) mechanically reduces
  per-contract tick value ($1 vs $10) and, all else equal, margin
  requirement -- consistent with #109's framing of `MNG` as the preferred
  lower-capital retail instrument.
- Whether `MNG`'s liquidity/spread/depth is *actually* sufficient at the
  research target's intended trade size and horizon (the specific comparison
  #109 asks for) was **not independently verified** -- this requires either
  live/recent order-book data or a market-data subscription, neither of
  which this review had access to. CME confirms fungibility with the E-mini
  contract, which is a structural liquidity-support signal, but is not a
  substitute for an observed spread/depth comparison.
- Saxo's own commission schedule for CME-listed energy futures was not
  located in a machine-readable form in this pass (the linked PDF document
  was not parsed); a per-contract commission, exchange fee, and market-data
  subscription cost figure should be pulled directly from an authenticated
  account or the current published fee schedule before any cost-sensitivity
  conclusion is drawn.

---

## 5. Fallback (Interactive Brokers)

IBKR is confirmed to offer broad CME Group futures access in principle and
has product-specific educational material on `MNG`. As with Saxo, Norway
residency, exact market-data entitlements, paper-trading support, and API
order/fill behaviour for the specific instrument were **not independently
verified** and require the same authenticated-account verification path
that #109 already specifies. No evidence was found in this review to prefer
IBKR over Saxo or vice versa on the specific entitlement questions that
matter -- the review simply could not resolve either one from outside an
account.

---

## 6. End-to-end proof before paper execution

Not performed in this review and explicitly out of scope for external desk
research: an end-to-end SIM/paper order lifecycle test requires an
authenticated Saxo SIM (or IBKR paper) account, which this review does not
have and should not request credentials for. This remains squarely #109's
own required deliverable and is unaffected by anything in this independent
review.

---

## Decision-ready summary (per issue #109's requested format)

| Field | Status after this independent review |
|---|---|
| Primary broker | Saxo Bank (candidate confirmed as plausible; NOT entitlement-verified) |
| Primary API | Saxo OpenAPI (`ContractFutures` / futures-space model publicly documented; NOT entitlement-verified) |
| Primary tradable instrument | `MNG` (CME-confirmed: 1,000 MMBtu, $1/tick, fungible with E-mini HH; Saxo-side listing NOT independently confirmed) |
| Research-target -> tradable-contract mapping | **Unresolved** -- no general solution found in the literature; requires an explicit, documented, deterministic roll/entry rule before any live/paper connection |
| Required real-time data subscription/feed | Exists commercially (CME-confirmed); exact retail cost and Saxo OpenAPI entitlement NOT independently confirmed |
| Order types and execution semantics | Partially confirmed at the Saxo-platform level (stop/synthetic-stop, partial fills, FND closeout); NOT confirmed at the specific-contract/API level |
| Margin/cost/slippage assumptions | Directionally favourable for `MNG` (smaller notional); NOT quantitatively confirmed |
| Expiry/roll safeguards | Structurally strong (Saxo avoids physical delivery by design); contract-specific FND timing NOT independently confirmed |
| Paper/SIM verification evidence | Not performed in this review -- remains #109's own required next step |
| Fallback broker/API/instrument | IBKR (plausible; NOT entitlement-verified) |
| Remaining blockers requiring user action | Open a Saxo SIM (and/or IBKR paper) session and run the exact end-to-end verification #109 already specifies; obtain the Saxo futures contract-specifications PDF and current commission/market-data fee schedule in machine-readable form; confirm `MNG` history length is adequate for the intended backtest window |

This independent review's role is to confirm that nothing in the public
record contradicts #109's leading candidates, and to isolate precisely which
facts are structurally unverifiable from outside an authenticated account --
so that the account-opening/verification work in #109 is not duplicated, and
is not skipped on the mistaken assumption that public documentation already
settled it.
