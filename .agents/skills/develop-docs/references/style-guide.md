# Machine-Friendly Markdown Style Guide

Project style, schemas, controlled vocabularies, and document-owner rules override this guide.

## Format And Structure

- Output `.md` unless another format is explicitly requested or project-mandated.
- Use one H1 title. Use logical heading levels without skipping levels.
- Start each section with new information. Do not restate the heading.
- Use numbered lists only for ordered steps. Keep one action per step.
- Use bullets for non-sequential items. Use tables for uniform or comparative data.
- Use fenced YAML or JSON for machine-consumed structures when the repository accepts that representation. Add language tags to every code fence.
- Keep links explicit and resolvable. Prefer repository-relative links for repository documents.
- Preserve stable anchors, IDs, metadata fields, and established frontmatter keys.

## Sentence And Claim Discipline

- Put one claim in each sentence or structured block.
- Use active voice and name the responsible role, component, document, or team.
- State conditions, thresholds, units, defaults, exceptions, and time boundaries explicitly.
- Use direct subject-verb-object construction when practical.
- Keep terminology exact and consistent. Define a term once; reference the definition thereafter.
- Separate instructions from rationale. Do not hide requirements inside explanatory prose.
- Apply the deletion test: remove any sentence whose absence changes neither machine extraction nor a reader's decision.

## Normative Content

- Physically separate binding requirements from informative rationale or examples.
- Use `MUST`, `MUST NOT`, `SHOULD`, and `MAY` only when the document defines their normative meaning or follows an established convention.
- Make each requirement atomic and independently referenceable when stable identifiers are available.
- Enumerate value sets completely. Mark an incomplete set explicitly and state that it is not enforcement-ready.
- Make conditions machine-evaluable. Replace "when appropriate" with the exact predicate.
- State every default. Avoid "unless otherwise specified" unless the controlling source and lookup boundary are explicit.

## Machine-Friendly Good Practice

1. Structure before prose for specifications, registers, comparisons, procedures, and finite sets.
2. Stable identifiers before positional references such as "the section above."
3. Named actors before ambiguous "it," "they," or "the system."
4. Complete sets or an explicit incomplete status; never "and so on."
5. One source of truth; link to authority instead of duplicating governed rules.
6. Source-backed claims; label adaptations, inferences, and repository decisions.
7. Synchronized metadata, headings, indexes, references, and body content.
8. Exact commands and examples verified against the current repository state.
9. Informative context labeled so machines do not interpret it as an obligation.
10. Minimum sufficient content; completeness is not word count.

## Rewrite Or Remove

Rewrite filler and ambiguity such as:

- "This section defines/covers/describes/outlines ..."
- "It is important/worth noting ..."
- "It should be noted ..."
- "In order to ..."
- "As mentioned above/previously discussed ..."
- "Where appropriate/applicable," "as needed," or "when necessary" without an explicit condition
- "Generally," "typically," "usually," or "often" without evidence or a defined scope
- "Various," "a number of," "and/or," "etc.," or "and so on"
- "This ensures that ..." when it introduces unsupported rationale

Do not ban a phrase mechanically when quoted source text, legal language, or an established project convention requires it. Preserve controlled wording and record the exception.

## Controlled-Document Boundary

Some systems require RULE blocks, section-ID comments, frontmatter indexes, canonical cross-reference tokens, change logs, or modal vocabularies. Apply those structures only when project authority requires them. Do not import SVX-specific fields, IDs, enums, or compliance verdicts into an unrelated repository.

## Final Style Check

- First sentences are operative.
- Claims are atomic, direct, source-supported, and scoped.
- Binding and informative content are structurally distinguishable.
- Headings, links, anchors, metadata, examples, and indexes agree.
- No filler, hidden defaults, vague conditions, duplicate authority, or stale commands remain.
- Markdown renders correctly and remains easy to parse as plain text.
