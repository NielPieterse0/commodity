# Change Specification: Quantitative Research Knowledge Router

- **Change ID:** `354-quantitative-research-knowledge-router`
- **Status:** Implementing
- **Complexity:** `medium`
- **Risk triggers:** `architecture_boundary`, `public_contract`

## Outcome

Establish Programme 003 Phase 0 as a cited, repository-native knowledge router that converts authoritative quantitative-research sources into Commodity-specific executable rules without creating a competing local skill catalogue.

## Authority and design

- Work authority: GitHub #354 under programme #353.
- Repository authority: `AGENTS.md`.
- Canonical router: `config/quantitative_research_knowledge.json` under a dedicated schema.
- Human projection: generated documentation only.
- Existing methodology remains owned by `config/research_methodology.json`; the router references and gap-maps it.

## Requirements mapping

1. Record four core sources plus tier-2 DDIA with stable URLs and access/license notes.
2. Route each approved research/engineering question to primary and secondary source authorities.
3. Provide executable playbooks for temporal integrity, targets, features, validation/CV, tuning, forecast evaluation and backtesting.
4. Produce `current Commodity rule -> source authority -> legacy evidence -> missing control` mappings.
5. Integrate agent usage into normal repo guidance while keeping reusable skills in live KIS.
6. Preserve protected confirmation boundaries and avoid empirical outcome access.
## Acceptance

- Router/schema validation is deterministic and part of canonical verification.
- Every playbook rule cites source IDs and Commodity canonical-owner references.
- Methodology coverage and genuinely missing/partial controls are explicit rather than implied.
- Generated guidance tells later phases what authority and playbook to consult.
- No copyrighted prose is harvested wholesale and no third-party code is imported in Phase 0.
- No protected confirmation outcome is opened or scored.

## Risks and recovery

- **Competing authority:** a local `SKILL.md` would conflict with `AGENTS.md`. Control: config + generated projection only.
- **Generic summaries:** source notes could become non-executable prose. Control: schema/tests require ordered Commodity rules and owner references.
- **False gap claims:** source-inspired wishes could be mislabeled as current defects. Control: mark controls `covered`, `partial`, or `missing` against current canonical owners and assign later phases only where appropriate.
- **Copyright:** books are copyrighted. Control: metadata, short distilled principles and citations only.
- **Recovery:** revert the bounded Phase-0 commit; prior methodology and programme science remain unchanged.

## Out of scope

- New forecasting, fitting, backtesting or empirical scoring.
- Protected confirmation access.
- Importing third-party source code or book text.
- Implementing later Phase 1-8 controls merely because the router identifies them.
- Closing or changing #348/#351 or other distinct scientific branches.
