# Skill Boundary Contract

All repo-local runtime skills live under `.agents/skills/`; discovery and the authoritative inventory are owned by [`../../AGENTS.md`](../../AGENTS.md).

Core and domain skills are separated by responsibility, not by runtime directory.

A domain skill may add dataset semantics, point-in-time rules, target/label definitions, temporal validation constraints, domain leakage conditions, cost/evaluation assumptions, regimes, or task-specific rubrics.

A domain skill must not redefine generic experiment tracking, reproducibility, baseline discipline, final-test isolation, or execution authority. Domain logic must remain outside generic core skill bodies.
