# Repository Authority Refresh Plan

**Documentation level:** Complex because the slice changes source-of-truth ownership, but it is bounded to documentation and provenance only.

## Outcome

- Make `AGENTS.md` the single repository authority map.
- Require one owner per mutable fact and references instead of copied authority.
- Refresh Databento acquisition documentation from verified local evidence without changing provider selection or licensing gates.
- Register GitHub API/MCP repositories as technical sources with explicit trust tiers.
- Make KIS Work Management the required operational projection for Commodity slices, tasks, defects, findings, decisions, risks, holds, approvals, and research follow-up while keeping all identifiers repository-scoped.
- Keep U.S. Henry Hub first, with Global/Interconnect and Norway/Europe as measured expansion layers.

## Scope

Edit `AGENTS.md`, `README.md`, `docs/THIRD_PARTY.md`, `docs/data-manifest.md`, and `docs/roadmap.md`; add a safe Databento acquisition evidence summary. Do not edit runtime code, schemas, configuration, policy, or raw licensed data.

## Verification

Review authority ownership and cross-references; validate Markdown paths; run repository tests required by `AGENTS.md` coupling, Ruff, `git diff --check`, JSON parse checks, and a credential-pattern scan of the diff.