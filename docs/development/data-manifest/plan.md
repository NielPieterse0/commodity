# Data Manifest Documentation Plan

**Outcome:** Create one concise reader-facing manifest for the ideal natural-gas research dataset, split into U.S./Henry Hub, global/interconnect, and Norway/Europe layers.

**Audience:** Repository maintainers and research agents deciding what to acquire, ingest, and promote into model features.

**Authority:** `config/data_sources.json` remains the machine-readable authority for implemented provider/source state. The new manifest owns the intended dataset roadmap and source candidates only.

**Output:** `docs/data-manifest.md`

**Boundaries:** Documentation-only. Do not change provider status, canonical-evidence gates, roll policy, model policy, or execution policy.

## Acceptance

- Every desired data family is assigned `V1` or `Later`.
- Each row identifies the desired datapoints, cadence/grain, preferred source, access class, and point-in-time concern.
- Sources prefer primary/public authorities; commercial sources are explicit where no equivalent public source is adequate.
- U.S., global/interconnect, and Norway/Europe layers remain distinct.
- Existing implemented state is linked to `config/data_sources.json`, not duplicated as a competing status registry.
- The final document stays concise enough to scan as a manifest rather than becoming another research report.
## Source Traceability

| ID | Evidence family | Intended section |
|---|---|---|
| S-US-MKT | CME/Massive contract, settlement, OHLCV, expiry | U.S. market structure |
| S-US-FUND | EIA natural gas, storage, production, imports/exports, power | U.S. physical balance |
| S-US-WX | NOAA/Open-Meteo issued forecast archives | U.S. weather |
| S-US-POS | CFTC COT | U.S. positioning |
| S-GL-FLOW | ENTSOG gas transmission transparency | Global/interconnect |
| S-GL-STOR | GIE AGSI/ALSI storage and LNG transparency | Global/interconnect |
| S-GL-PWR | ENTSO-E load/generation/wind/solar/outage transparency | Global/interconnect |
| S-GL-TRADE | Eurostat/ACER gas and LNG trade/market transparency | Global/interconnect |
| S-NO-PROD | Norwegian Offshore Directorate field/NCS production | Norway/Europe |
| S-NO-TRADE | SSB Statbank exports and economic data | Norway/Europe |
| S-NO-HYDRO | NVE hydrology/reservoir data | Norway/Europe |
| S-NO-WXFX | MET Norway weather; Norges Bank FX | Norway/Europe |

## Tasks

1. Verify current repo source authority and avoid duplicating runtime status.
2. Research primary sources, access method, history/cadence, licensing/key requirements, and vintage/revision constraints.
3. Write the three-layer manifest with V1/Later prioritization and derived-feature intent.
4. Review for source support, leakage risk, duplication, and scope creep.
5. Run Markdown/link/repository checks available in the repo; inspect the final diff.
6. Commit, push, open/review/merge the PR, synchronize local `main`, and remove the linked worktree/feature branch.