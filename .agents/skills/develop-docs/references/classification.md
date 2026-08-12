# Documentation Classification

Classify by the highest applicable signal. Word count and changed-line count are supporting evidence, never the deciding factor.

| `Signal` | Small | Medium | Complex |
|---|---|---|---|
| `Scope` | One bounded correction or short addition | Multiple sections/files or dependent edits | Cross-document system or publication boundary |
| `Authority` | Informational, local, non-governing | Shared guidance with bounded authority | Governing, controlled, contractual, public, or safety-critical |
| `Sources` | One clear current source | Several compatible sources requiring synthesis | Conflicting, incomplete, volatile, or approval-dependent sources |
| `Structure` | Existing structure remains valid | Meaningful outline, terminology, or cross-reference choices | Metadata, schemas, indexes, generated docs, migrations, or class changes |
| `Impact` | Low-risk and readily reversible | Moderate reader or workflow impact | Security, legal, compliance, operational, release, or broad downstream impact |
| `Evidence` | Targeted review/checks are sufficient | Several checks and section/task evidence | Approval, source, structural, safety, publication, and rollback evidence |

## Automatic Escalation

Classify as Complex when a material change affects security or privacy guidance; authentication, authorization, recovery, incident response, deployment, release, migration, legal, compliance, policy, contractual terms, public API or customer documentation, controlled/governing documents, source-of-truth ownership, machine indexes or schemas, generated-document pipelines, sensitive data, difficult rollback, or conflicting authority with high-impact consequences.

Classify at least Medium when work spans multiple documents or major sections, synthesizes several sources, changes shared terminology or navigation, requires a new information architecture, alters many links/examples, or has unresolved audience/content decisions that are not themselves Complex.

Small requires all Small signals. A one-line edit to an authoritative control is not Small. If uncertain between levels, select the higher level and record what evidence could reduce uncertainty.

## Reclassification Triggers

Reclassify when discovery reveals a governing owner, hidden consumers, public exposure, source conflicts, stale facts, structural/index coupling, broader publication, sensitive content, executable behavior, or repeated verification failures. Update the plan and gates before continuing.
