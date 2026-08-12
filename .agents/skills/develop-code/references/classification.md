# Development Classification

Classify by the highest applicable signal. File count and line count are supporting evidence, never the deciding factor.

| `Signal` | Small | Medium | Complex |
|---|---|---|---|
| `Scope` | One clear bounded outcome | Multiple files or dependent steps | Cross-component or architectural boundary |
| `Decisions` | No meaningful design choice | Meaningful but bounded choices | Material trade-offs or open decisions |
| `Risk` | Low and readily reversible | Moderate or non-trivial regression surface | High-risk, security-sensitive, difficult to reverse |
| `State` | No persistent-data change | Existing state used without risky transition | Persistent data, schema, migration, destructive or irreversible transition |
| `Operations` | No provider/deployment/release coupling | Bounded integration | Provider, deployment, release, infrastructure, or operational recovery |
| `Evidence` | Targeted checks are sufficient | Several checks and task evidence | Acceptance, rollback, operational, security, and cross-component evidence |

## Automatic Escalation

Classify as Complex when any material part is security- or privacy-sensitive; changes authentication or authorization; handles secrets, money, regulated data, persistent data, schemas, migrations, providers, deployment, infrastructure, public compatibility, or release controls; crosses trust or architectural boundaries; is hard to reverse; or has uncertainty whose wrong resolution could cause high impact.

Classify at least Medium when the outcome spans multiple files, has several dependent steps, requires a meaningful design choice, changes a shared interface, lacks a clear test strategy, or has unresolved behavior that is not itself Complex.

Small requires all Small signals. If uncertain between levels, select the higher level and record what evidence could reduce uncertainty. Complexity may decrease during understanding, but never solely because the eventual code diff is short.

## Reclassification Triggers

Reclassify when discovery reveals hidden consumers, shared contracts, new data/state, broader permissions, migration or rollback needs, additional systems, unclear acceptance criteria, failed assumptions, or repeated verification failures. Update artifacts and gates before continuing.
