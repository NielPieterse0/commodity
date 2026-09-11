# Spec: Phase 4 Foundation Specialists

## Scientific authority

- GitHub issue #358, L3 implementation freeze comment `5628520758`, role-specific clarification `5632161050`, and closed-budget second-line amendment `5634786235`.
- The clarification preserves the original #358 rule that failure in one tested role is not evidence against all possible specialist value. The amendment admits exactly one additional deployment-compatible family (Chronos-2), one same-family Kronos capacity control, and one Moirai research-only/non-commercial comparator; policy optimization remains in #359.
- Dependency #357 landed at `fa1841ac7877b25b868639abdcb4ec9928ecf8f6`.
- Protected confirmation remains unopened.

## Science-to-repository mapping

- `config/models.json` pins the eligible deployment-compatible specialist identities and checkpoint hashes.
- `src/commodity/foundation_specialists.py` enforces specialist provenance, PIT generation cutoff, exact contract/time join grain, target-leakage exclusion and remove-one component sets.
- `tests/test_foundation_specialists.py` supplies failing-boundary evidence for those controls.
- Later Phase-4 runtime work must consume the L3 freeze directly; this spec does not extend its scientific design.

## Scope boundary

No target/estimand, fill, cost, sizing, risk, protected-evidence, or policy-selection change is authorized here. The model-family budget is exactly the amended closed set in comment `5634786235`; no fourth family or post-hoc representation search is permitted. Runtime/checkpoint availability defects that preserve this L3 contract remain engineering work inside this change.
