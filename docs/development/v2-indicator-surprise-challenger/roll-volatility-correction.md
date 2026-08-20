# #136 Roll-Safe Volatility Correction

**Issue:** `NielPieterse0/commodity#136`

**Parent programme:** `#132`

**Shared semantic dependency:** `#133`

**Affected candidate:** `#83` / `v2-83-indicators-only`

**Status:** correction implemented before #83 empirical execution; refreeze and independent release audit still required

## Defect lineage

The frozen #83 definition inherited V1 `vol_5` and `vol_20` as controls and derived `vol_ratio_5_20` from those columns. The V1 selected-series construction could leave a missing return at a contract switch and downstream processing could turn that missing value into an artificial zero. That makes roll-adjacent volatility smaller than the same-contract market history supports.

The original #83 preparation and implementation identities remain historical evidence. They are **superseded-before-execution**, not rewritten as though this correction had been preregistered originally.

## Corrected semantics

For each selected session, volatility now starts from `same_contract_selected_returns` owned by `src/commodity/roll_safe_market.py` and introduced by #133. Each return compares the selected contract settlement with that same contract's latest eligible prior-session settlement.

No cross-contract return is created. A roll day is not replaced with zero when the newly selected contract has eligible own-contract history. A 20-session volatility window fails closed if any required same-contract return is missing or non-finite.

## Governance consequence

The frozen candidate registry is intentionally not rewritten inside this correction because #81 binds its exact digest and the corrected #136 implementation does not yet have an immutable landed revision. Instead, the corrected implementation source contract now includes `src/commodity/roll_safe_market.py`; the old #83 implementation binding cannot satisfy that source-manifest contract and therefore fails closed until a later refreeze binds the corrected revision.

The runtime release check also requires candidate-level execution authority. The final corrected implementation revision, manifest digest, candidate-registry digest, and release state can only be frozen after this change has an immutable commit/PR identity and has passed the required independent audit.

## Verification boundary

Verification includes a synthetic large-level roll where the selected contract changes from a roughly 3-price contract to a roughly 10-price contract. The corrected volatility uses the new contract's own prior-session return, not the cross-contract level jump and not zero.

No #83 model fitting, prediction generation, metric inspection, feature-family expansion, threshold search, estimator tuning, Kronos fusion, or live-trading authority change is authorized by this correction.

## Required handoff before #83 execution

1. Land the #136 correction with exact source and test identities.
2. Refreeze #83 against the landed implementation and corrected result-affecting manifest.
3. Re-run the independent empirical-release audit against the corrected authority.
4. Generate no #83 empirical prediction until both refreeze and audit explicitly release the new exact implementation.
