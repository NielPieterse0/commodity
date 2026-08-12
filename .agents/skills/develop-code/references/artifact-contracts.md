# Artifact Contracts

Project-owned locations and templates take precedence. If none exist, use:

```text
docs/development/<slug>/spec.md
docs/development/<slug>/plan.md
```

For Small work, keep the compact specification and inline plan in the task record, issue, or response when that is durable enough. If a repository file is needed, use `docs/development/<slug>/spec.md` and include the plan section in it. Do not create an empty plan file.

Use [small template](../assets/small.md), [medium template](../assets/medium.md), or [complex template](../assets/complex.md). Adapt headings to repository conventions without dropping required content.

## Traceability

- Give Medium and Complex requirements stable IDs such as `R1`, `R2`.
- Each plan task lists the requirements it satisfies and the evidence it will produce.
- Review reconciles requirement -> task/change -> test or other evidence.
- Record deviations and exclusions in the specification, not only in chat.

## Canonical Ownership

- Specification owns outcome, behavior, boundaries, acceptance, exclusions, risk expectations, and open decisions.
- Plan owns implementation approach, affected surfaces, ordered tasks, verification, review checkpoints, rollout, and recovery steps.
- Code and tests implement the approved artifacts; they do not silently redefine them.
- Verification output proves a particular current state; it does not replace requirements or review.
