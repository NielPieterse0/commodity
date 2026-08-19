# External review 2.2 disposition

**Source:** `docs/references/commodity-external-review-2.2.md` and immutable package `docs/references/commodity-external-review-2.2.zip`.

**Role:** provenance and adoption routing only. This record does not make the external review authoritative. Mutable Commodity facts remain owned by the authority map in `AGENTS.md`.

## Material findings

| External finding | Disposition | Commodity owner / action |
|---|---|---|
| H-GLOBAL-LNG-1 has a plausible conditional mechanism but lacks demonstrated next-session Henry Hub OOS evidence; crisis congestion can weaken transmission. | Future hypothesis; revise and re-horizon before any test. | #116. Keep the current frozen daily V2 target unchanged. |
| Weekly US storage surprise is the strongest horizon-matched candidate located, but modern-regime replication and a PIT-safe historical consensus source are still required. | Future hypothesis. | #113, explicitly post-core-V2. |
| Issued weather-forecast revisions are a high-priority short-horizon candidate, but academic evidence is incomplete and archive/PIT/licensing feasibility needs dedicated work. | Research gap / future hypothesis. | #114. |
| Norway-specific NOD/Gassco/SSB/ENTSOG evidence was not independently researched in review 2.2. | Unresolved research gap. | #115 under #86. |
| TTF, GIE AGSI/ALSI and ENTSOG require further PIT/publication/licensing verification; JKM has material licensing risk. | Existing data-readiness work; no acquisition authority granted. | #86; Databento-specific adoption remains #51. |
| MNG/exchange infrastructure appears viable, but Norway-resident account/API entitlement and exact research-series-to-tradable-contract mapping remain unresolved. | Execution-readiness requirement. | #109. `config/policy.json` remains the sole execution-permission owner. |
| Parsimonious/shrunk specifications and explicit treatment of inactive HH-WTI relationships are supported as design cautions, not automatic model changes. | Future design review. | #89 before any next-wave model redesign. |
| Curve/spread features require a frozen continuous-series or exact contract-month construction rule. | Existing/future design constraint. | #89 for research design; #109 for signal-to-order contract mapping. |

## Rejected or bounded recommendations

- Do not treat CFTC positioning as presumptively leading at short horizons without a separately preregistered lead/lag test. This is retained as negative external evidence, not promoted to a new experiment here.
- Do not promote raw TTF/JKM levels as a standalone forecasting hypothesis; retain them only as comparators unless a separately reviewed hypothesis establishes a mechanism and PIT-ready data.
- Do not assume crisis or stress mechanically strengthens global-to-US gas-price transmission; any future test must allow congestion-driven decoupling.
- H4 futures-spread and H6 regime-overlay ideas are not activated by this intake. They may be considered by #89 and require fresh preregistration before empirical use.

## Evidence handling

- Version 2.2 is the current external evidence package; version 2.1 is retained unchanged as superseded provenance.
- The ZIP is retained unchanged and its internal `output/` layout is preserved in the searchable extraction.
- `docs/references/commodity-external-review-2.2/SHA256SUMS.txt` records received-file and extracted-artifact identities.
- No finding in this intake changes `config/policy.json`, `config/data_sources.json`, model configuration, experiment activation, or empirical release flags.

## Follow-up boundary

Issue #112 is complete when this evidence package, checksum record, reference index, and disposition are landed. The follow-on issues remain independently governed work; this intake does not mark their conclusions as adopted or authorize execution.
