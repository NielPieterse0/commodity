# Change Specification: V2 Variable Registry

- **Change ID**: `396-v2-variable-registry`
- **Status**: Draft
- **Complexity**: use live KIS schema-v4 classification

## Outcome

Register the authoritative V2 variable search space for Programme #393, restore deterministic generated documentation required by CI, and land issue #396 without starting optimization or opening any protected evidence boundary.

## Authority and scope

- Authoritative research/design requirement: GitHub issue `#396`, child of Programme `#393`; this change only maps that accepted registration design into repository authority.
- Existing implementation evidence: PR `#423` head `a2953e9ca18405e7c758c6c51c61fdc0f28fe032` contains the registered variable search space.
- Documentation authority: `config/documentation_authority.json`, `config/documentation.json`, and `scripts/docs/generate_docs.py`.
- Owned/shared/excluded paths and integration ownership: `scope.json`.

## Requirements mapping

- Preserve the PR #423 registry semantics without starting optimization or scoring.
- Generate `docs/reference/config/v2_variable_registry.md` from `config/v2_variable_registry.json`.
- Regenerate the shared `docs/reference/README.md` index deterministically.
- Keep `reserved_confirmation` and `true_forward` prohibited from search and keep V1 immutable.

## Acceptance

1. `config/v2_variable_registry.json` is valid JSON and retains issue #396's registered search boundaries.
2. `scripts/docs/generate_docs.py --check` passes on the current tree.
3. `scripts/checks/check_rule_verification.py --check-generated` passes on the current tree.
4. No optimization, scoring, sealed-confirmation access, SIM trading, or LIVE trading occurs in this change.

## Risks and recovery

- Risk: generated documentation drift or accidental expansion beyond the registration-only scope.
- Recovery: revert the bounded #396 commit; no data, model, trading, or external execution state is mutated by this change.

## Out of scope

- Running the V2 optimization campaign, selecting a champion, opening sealed confirmation, or changing trading permissions.
