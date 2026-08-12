# Harvest and Provenance Notes

## Adopted Source Evidence
- Repository: `openai/role-specific-plugins`
- Immutable commit: `fe5608d2512a7d6a7b9821ce8a88c48464ecd6e4`
- Quarantine case: `20260812-121057_openai-role-specific-plugins_3d1c07a7`
- Requested scope: `plugins/data-analytics/skills`

Concepts were harvested from markdown-only OpenAI skills:
- `analyze-data-quality/SKILL.md`: grain, completeness, integrity, temporal/distribution checks, ML leakage, remediation discipline.
- `jupyter-notebooks/SKILL.md`: inspectability, deterministic inputs, explicit assumptions, rerunnable analysis, source/artifact traceability.
- `validate-data/SKILL.md`: independent recomputation, methodology QA, join/denominator/time-window checks, statistical traps, confidence/disposition.
- `visualize-data/SKILL.md`: conceptual guidance for bounded, interpretable analytical outputs; no runtime assets copied.

The user-approved shared-core architecture supplied the requested skill boundaries and experiment lifecycle.

## Reconstruction Policy
No source file was copied verbatim. Skill bodies and the experiment schema are newly authored. Source-specific connector names, automation hooks, install commands, report runtimes, scripts, and encoded assets were deliberately excluded.

## Sources Not Adopted
- `mattpocock/skills` commit `84fdeffd12f2ee307994d1eb6feb48173b6e0502`: quarantine rejected the source archive for `archive-link`; policy was not relaxed.
- `huggingface/skills`: canonical acquisition received GitHub HTTP 403 rate limiting; no repository bytes or instructions are present here.

## Trust Statement
Repository reputation was not treated as authorization. The adopted OpenAI source was commit-pinned, Defender-scanned before and after materialization/import, statically inspected offline, and used only as read-only evidence for this Markdown/JSON reconstruction.

## Commodity Import Adaptation — 2026-08-12

Imported from reviewed quarantine export `20260812-123045_ml-research-core-reviewed_a24b69ea`.

Local changes are limited to shared-core contract quality and responsibility boundaries:
- experiment schema upgraded from v1 to v2 for reconstructible point-in-time experiments;
- v2 lineage records commit identity plus dirty-working-tree state/hash instead of treating `HEAD` alone as executed-code identity;
- experiment designer/tracker aligned to the v2 contract;
- model evaluator explicitly limited to forecast/model evaluation;
- lifecycle documentation corrected so statistical/robustness analysis feeds research promotion before reproducibility audit.

Commodity-specific skill bodies are materialized outside the generic core under `.agents/skills/`; research maturity remains owned by `config/research_stages.json`.
