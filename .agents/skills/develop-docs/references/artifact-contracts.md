# Documentation Artifact Contracts

Project-owned paths, templates, metadata, and publication systems take precedence.

## Output Format

- Create Markdown (`.md`) by default.
- Use another format only when the user explicitly requests it or authoritative project conventions require it.
- Do not silently generate duplicate formats or treat a rendered projection as a new source of truth.
- Preserve existing encoding, line-ending, heading, frontmatter, and wrapping conventions unless the task changes them.

## Default Locations

- Existing document: edit it in place.
- New document with no project convention: `docs/<slug>.md`.
- Small plan: keep the compact brief and plan in the durable task record or response.
- Medium or Complex plan with no project convention: `docs/development/<slug>/documentation-plan.md`.

Use [small template](../assets/small.md), [medium template](../assets/medium.md), [complex template](../assets/complex.md), and [document template](../assets/document.md) only when the repository lacks a more authoritative structure.

## Traceability

- Give Medium and Complex claims or requirements stable working IDs when the repository does not already provide them.
- Each plan task lists target documents, source evidence, expected reader outcome, and verification.
- Review reconciles source -> planned section/change -> final text -> check or review evidence.
- Record source conflicts, adaptations, decisions, and exclusions in the plan, not only in chat.

## Canonical Ownership

- Source owners govern imported facts, rules, and controlled wording.
- The documentation plan governs the authorized transformation and acceptance evidence.
- The final document owns its intended reader-facing content only within its declared authority.
- Generated views do not silently supersede canonical Markdown or another established source of truth.
