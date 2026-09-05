# Change Specification: Pre-outcome Dataset Assurance

- **Change ID**: `320-preoutcome-dataset-assurance`
- **Status**: Active
- **Complexity**: medium

## Outcome

Split confirmatory dataset assurance into a pre-outcome structural/identity gate and a post-unblinding value-level empirical gate without weakening either.

## Authority and scope

- Scientific lifecycle authority: `config/research_methodology.json` Step 9 freeze boundary and Step 11 verification requirements.
- Defect/acceptance authority: GitHub issue #320.
- Owned/shared/excluded paths: `scope.json`.

## Requirements mapping

- Freeze must validate only outcome-blind source/version/schema/time/PIT/pipeline/coverage/invariant bindings.
- Opening confirmatory outcomes must require a valid remotely bound freeze plus the pre-outcome assurance identity.
- Result construction must reject missing or mismatched post-unblinding exact reconstruction + semantic assurance.
- Existing exploratory/research-ready assurance remains value-level and unchanged in meaning.

## Acceptance

1. A confirmatory freeze can be constructed without a dataframe or protected value hash.
2. Post-unblinding results cannot be accepted without value-level research-ready assurance bound to the frozen pre-outcome identity.
3. Existing exact reconstruction and semantic verification remain fail-closed.

## Out of scope

- Signed-tag infrastructure and KIS implementation.
- WORK-316 protected outcome access or experiment-specific result execution.
