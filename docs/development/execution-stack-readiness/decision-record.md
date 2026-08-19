# Henry Hub execution-stack decision record

**Evidence snapshot:** `evidence.json` owns the exact point-in-time probe/status facts for this record.
**Execution authority:** none; `config/policy.json` remains authoritative and live trading remains prohibited.

## Decision

Use **Saxo OpenAPI/SIM as the primary verification path** and **Micro Henry Hub Natural Gas futures (`MNG`) as the preferred tradable instrument candidate**, but do not promote either to an approved execution stack yet. Keep **Interactive Brokers (IBKR)** as the fallback verification path.

This is the strongest decision support currently available without a valid authenticated brokerage session. Public documentation establishes product and API feasibility, but it does **not** satisfy #109's account-specific acceptance criteria. The exact local authentication result is owned by `evidence.json#local_probe`; exact Norway-account entitlements, UIC identity, real-time OpenAPI feed rights, account margin, supported order types, and an end-to-end SIM order lifecycle remain unverified.

## Decision-ready stack

| Element | Current decision | Gate before promotion |
|---|---|---|
| Primary broker | Saxo Bank | Norway-resident account/SIM must expose exact MNG contract(s) and futures trading permission. |
| Primary API | Saxo OpenAPI SIM | Authenticated account, `ContractFutures` legal asset type, price-feed entitlement, and paper order lifecycle required. |
| Primary instrument | CME/NYMEX `MNG` | Exact Saxo UIC/futures-space identity and tradability must be observed in the intended account. |
| Fallback | Interactive Brokers paper/API + MNG | Open/funded eligible live account, futures permission, MNG contract resolution, data subscription, paper API lifecycle required. |
| Execution-time data | Broker-native NYMEX real-time feed | Entitlement must be proven through the API, not only in the broker UI. |
| Research data | Repository-configured research providers | Must remain separate from execution-time quote/order-state authority. |

## Instrument facts and mapping

CME defines MNG as 1,000 MMBtu, one tenth of standard NG, with a $0.001/MMBtu minimum tick worth $1 per contract. MNG is financially settled and trading terminates one business day before the corresponding standard NG contract; standard NG is 10,000 MMBtu and physically settled. MNG's final settlement is tied to the corresponding NG contract.

The applicable research-series and roll authority is `config/assumptions.json#assumptions.continuous_series_policy`. Translation to execution must therefore be **contract-month preserving**:

1. Resolve the exact NG contract month selected by the research/roll engine.
2. Resolve the MNG contract for that same delivery month through the broker's futures-space/contract identifier.
3. Reject the order unless exchange/product/month/expiry identity all match the expected mapping.
4. Never translate a continuous symbol directly into an order.
5. Apply an execution-specific earlier-expiry guard because MNG stops trading before its corresponding NG contract. The execution layer must roll/close before the MNG broker deadline even if the research series has not yet rolled.
6. Fail closed if the same-month MNG contract is unavailable; switching to standard NG is an explicit exposure-size decision, not an automatic fallback.

The 10:1 contract-size ratio means a one-contract MNG position is not economically interchangeable with one NG contract. Any sizing layer must convert forecast exposure into MMBtu/notional risk and then quantize to the selected instrument.

## Saxo findings

Saxo Norway publicly lists Henry Hub Natural Gas futures and micro futures generally, but its public page explicitly says actual product availability depends on account setup and country of residence. That is insufficient to prove MNG for this account.

OpenAPI supports account-scoped instrument search, `ContractFutures` futures-space resolution, instrument details and trading schedules. Its price endpoints expose trading prices, bid/ask, delay state and market depth subject to feed rights. User entitlements distinguish real-time top-of-book and full-book rights by asset type.

Critically, Saxo documents that exchange-product price feeds are paid subscriptions and that using price feeds through an API/third-party application can require **additional licences, agreements and cost beyond platform display access**. Therefore a NYMEX platform subscription alone must not be treated as proof of real-time OpenAPI entitlement.

Saxo's Norway market-data page currently lists NYMEX futures data at **USD 7/month Level 1** and **USD 15/month Level 2** for private/non-professional clients; professional pricing is materially higher. These are public platform prices and remain provisional until the account and OpenAPI usage rights are checked. Level 1 is sufficient for a basic bid/ask/last execution gate; Level 2 is required only if the strategy explicitly depends on depth.

Saxo Norway currently advertises Henry Hub Natural Gas futures at an indicative **USD 3 commission per contract per trade**, excluding exchange fees, with residency/account-tier variation and additional overnight carrying costs. Exact MNG commission, exchange fees, margin and currency effects must come from the authenticated trade ticket/contract specification.

Saxo also warns clients to close futures before expiry/FND and may impose a broker deadline earlier than the exchange. MNG is financially settled, but the adapter still must use the broker's exact expiry/closeout deadline rather than infer safety from settlement type.

## IBKR fallback findings

IBKR lists Norway among supported account-opening countries. Its current US futures margin table explicitly includes Micro Henry Hub Natural Gas (`MNG`; displayed in the table as `MHNG`) and standard `NG`, which is materially stronger public evidence of MNG product support than the Saxo public catalogue.

IBKR's published direct-client commission schedule groups `MHNG` with E-micro futures at **USD 0.25/contract** for the first 1,000 monthly contracts, plus exchange/regulatory and potentially overnight fees. Current margin values are dynamic and must be captured from the intended account at verification time rather than frozen here.

IBKR paper trading supports Web API and TWS API with most live-account capabilities, but requires a fully open and funded live account for individual Web API access. Trading permissions and market-data subscriptions propagate from the live setup. Paper fills are simulated and have documented differences from production execution.

IBKR therefore remains a credible fallback, not a verified fallback. No authenticated IBKR account/API evidence exists in this repository yet.

## Costs and slippage policy for paper evaluation

Do not encode current broker prices as timeless simulation constants from this record. Before paper promotion, capture account-specific commission, exchange/regulatory fees, carrying fees, margin, data subscriptions and NOK/USD conversion/funding costs into the applicable simulation/execution authority.

Until empirical MNG spread/depth observations are captured, paper evaluation must not assume zero slippage. Use observed executable bid/ask at decision time and record spread, order type, fill price and latency. Any additional slippage model must be conservative and separately justified.

## Required authenticated proof

#109 remains open until one path completes this sequence with retained safe evidence:

1. Authenticate to Saxo SIM for the intended Norway-resident account.
2. Record account/client identifiers only in redacted or hashed form; never commit credentials or secrets.
3. Prove `ContractFutures` legal asset type and account/user futures permissions.
4. Search Henry Hub futures and record the continuous parent plus exact MNG UIC(s), symbols, expiry dates, contract size, trading status and trading schedule.
5. Prove NYMEX real-time top-of-book through OpenAPI (`DelayedByMinutes == 0`) and record whether full-book is entitled/needed.
6. Capture exact supported order types/durations, margin impact, commission and broker expiry/closeout fields for the chosen MNG month.
7. Under paper-only authority and explicit manual confirmation: validate -> submit one minimal MNG SIM order -> observe acknowledgement -> amend/cancel if applicable -> observe fill/position -> close -> reconcile orders, fills and positions.
8. Repeat the necessary discovery/data/order checks on IBKR paper, or explicitly disposition IBKR as unavailable with evidence.
9. Only after that evidence exists may `config/assumptions.json`, `config/data_sources.json`, third-party boundaries, simulation assumptions, or broker approval state be changed by their respective owners.

## Current blockers requiring user action

- Obtain/refresh a Saxo OpenAPI SIM access token and make it available locally as `SAXO_SIM_ACCESS_TOKEN` without committing it.
- Confirm the intended Saxo Norway account has futures permission and can see MNG specifically, not merely standard Henry Hub NG.
- Accept/subscribe to the required NYMEX real-time market-data agreement and confirm that the entitlement applies to OpenAPI/third-party use; platform-only display rights are insufficient.
- Provide or create the intended Saxo SIM account context needed for the paper order proof.
- For fallback verification, open/fund an eligible IBKR Pro live account if none exists, enable futures permissions, create/enable paper trading, and subscribe/share the required CME/NYMEX market data.

## Repository probe available now

The existing read-only command can be used once a Saxo SIM token is present:

`python -m commodity.cli probe-saxo-market --max-contracts 24 --output .work/issue-109-saxo-probe.json`

That command is evidence collection only. It does not prove order permissions or satisfy the paper lifecycle acceptance criterion.

## Primary evidence sources

Checked 2026-08-20:

- CME Group, Micro Henry Hub Natural Gas futures FAQ: https://www.cmegroup.com/articles/faqs/micro-henry-hub-natural-gas-futures-and-options-frequently-asked-questions.html
- CME Group, Micro Henry Hub product overview: https://www.cmegroup.com/education/courses/understanding-micro-futures-contracts-at-cme-group/micro-crude-futures/micro-henry-hub-natural-gas-futures-product-overview
- Saxo OpenAPI, Reference Data / Futures Spaces: https://www.developer.saxo/openapi/learn/reference-data
- Saxo OpenAPI, Pricing and price-feed rights: https://www.developer.saxo/openapi/learn/pricing
- Saxo OpenAPI, Core Business Concepts / market-data licensing: https://www.developer.saxo/openapi/learn/core-business-concepts
- Saxo OpenAPI, Order Placement: https://www.developer.saxo/openapi/learn/order-placement
- Saxo Norway, futures product page: https://www.home.saxo/nb-no/products/futures
- Saxo Norway, market-data subscriptions: https://www.home.saxo/nb-no/products/market-data-subscriptions
- Saxo Norway, futures commissions: https://www.home.saxo/nb-no/rates-and-conditions/futures/commissions
- IBKR, supported countries: https://www.interactivebrokers.com/en/accounts/open-account-country-list.php
- IBKR, futures margin requirements: https://www.interactivebrokers.com/en/trading/margin-futures-fops.php
- IBKR, futures commissions: https://www.interactivebrokers.com/en/pricing/commissions-futures.php
- IBKR, Trading Web API: https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/
- IBKR, paper trading: https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/

Public sources support feasibility only. Account-specific broker responses are the required evidence for promotion.

## Authenticated probe attempt

The exact local authentication result and token-expiry evidence are recorded only in `evidence.json#local_probe`. That evidence establishes that a fresh SIM token is required before account-specific checks can continue. Saxo documents that developer-portal quick SIM tokens have limited one-day validity.

This does not change execution authority or satisfy any account/API acceptance criterion.
