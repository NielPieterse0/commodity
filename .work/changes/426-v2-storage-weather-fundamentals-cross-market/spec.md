# Change Specification: V2 Storage Weather Fundamentals Cross Market

- **Change ID**: `426-v2-storage-weather-fundamentals-cross-market`
- **Status**: Active
- **Complexity**: large
- **Risk triggers**: money, persistent_state

## Outcome

Execute V2.29 strictly inside development evidence through 2022-12-31. Score only already-admissible point-in-time storage, issued-weather, power and positioning evidence; segregate screening/prospective cross-market sources; preserve the #425 market-only control; and record explicit HOLD/revisit dispositions when the required pre-2023 PIT evidence is unavailable.

## Scientific authority

- GitHub/Work item `#426` / `WORK-426` supplies the bounded research requirements and acceptance criteria.
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-search-plan-v1.json` freezes the executable source gate, ablations, interaction requirements and protected-evidence boundary before #426 scoring.
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-source-plan-v2.json` promotes the exact acquired historical storage, positioning and issued-weather evidence while preserving the same protected-evidence boundary.
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-optimization-plan-v3.json` supersedes the diagnostic v2 optimization plan before authoritative scoring and freezes identifiable role semantics plus zero-budget HOLD treatment for unidentifiable sizing/risk roles.
- `issue426-weather-feature-contract-v1.json` and `issue426-interaction-contract-v1.json` freeze weather and combined-interaction semantics before those searches consume evidence.
- `config/data_sources.json` owns global source/PIT admissibility.
- `config/v2_variable_registry.json` owns the registered V2 feature-family search space.
- `research/programmes/004-v2-maximum-reproducible-one-month-return/issue425-result-v1.json` owns the matched market-only development control.

## Requirements mapping

1. Source-gate every core family against configured PIT support and preserved snapshot coverage before loading/scoring it.
2. Enforce backward-only availability joins with bounded staleness and no post-2022 market rows.
3. When a family is scorable, transform it as an increment to the market control rather than as an isolated replacement.
4. Record storage × weather × season × volatility and all other registered interactions as scored or explicitly HOLD.
5. Preserve attempted-family history, monthly market-control return/risk evidence, and revisit triggers.
6. Never open reserved confirmation, prospective paper, Saxo SIM or LIVE evidence.

## Acceptance

- Core families are exactly storage, weather, power and positioning.
- A family whose configured or preserved PIT support begins after 2022-12-31 is HOLD before scoring and consumes no search budget.
- Screening-only/prospective-only fundamentals and cross-market sources remain segregated.
- #425 development evidence is content-bound as the matched market-only control.
- The result artifact explicitly reports source coverage, dispositions, interactions, zero/nonzero scoring trials, and protected-evidence flags.

## Risks and recovery

- **Risk:** silently using later corrected/history-only data would invalidate the research claim.
- **Recovery:** fail closed at the source gate; activation requires new admissible pre-2023 PIT evidence and a new immutable input identity.
- **Risk:** generated documentation or result hashes drift after implementation edits.
- **Recovery:** regenerate deterministic docs/results and rerun affected verification before promotion.

## Out of scope

Protected confirmation, paper/SIM/LIVE evaluation, sources not explicitly promoted by `issue426-source-plan-v2.json`, and downstream model/fusion/trading-policy optimization. Historical acquisition required to satisfy the registered #426 source families is in scope only when its exact source, availability semantics and evidence identity are frozen before scoring.
