# Closeout: V2 Sizing Exposure Leverage Risk Control

## Implemented scope

- Research-only sizing from reduced exposure through bounded multi-contract exposure, including long/short asymmetry and prior-only regime/tail/confidence modifiers.
- Explicit contract-count, margin-utilization, and notional-leverage accounting while preserving the operational one-contract paper cap.
- Causal drawdown scaling, uncertainty stop/take-profit, time stop, and additional-loss cooldown research controls.
- Frozen two-stage 318-trial development study with deterministic parent selection and full trial ledger.

## Scientific result

- Disposition: `FREEZE_ISSUE430_SIZING_DEVELOPMENT_CANDIDATE_NO_RISK_INCREMENT`.
- Single Stage-1 gate passer: `regime_favored1_50_other0_75`.
- Incremental mean monthly net-return delta vs fixed parent: `0.001276375` (+0.1276375%/month).
- Mean absolute monthly net return across development outers: `0.005214875` (0.5214875%/month).
- Maximum research position: 1.5 contracts; maximum margin utilization: 7.5%; maximum observed notional/account leverage: ~0.7971x.
- No Stage-2 risk-control variant passed the incremental robustness gate.
- Protected 2023+ confirmation, prospective paper, SIM, and LIVE evidence remained untouched.

## Implementation evidence

- Preregistration SHA: `d1009575138536bd7a960ba0ac3cd993d8b33b1095cd3736bdd47bfade6ab016`.
- No-scoring preflight SHA: `13553182f3cd7c3f4ff2b0ac64971f189e54b8b54398b473c4fdaa59dd34a2be` (PASS).
- Trial ledger SHA: `f180434937b86795abfd98a844b3297ae920f5f4612a8ce19d2808fa52b493e7`; 318/318 trials.
- Result SHA: `98d65a94ffff93aea93c95f5e52c7de0a34500e1efb21d41b396e13aef5ef50c`.
- Focused verification: 29/29 passed; Ruff clean.
- Inherited execution regression: 94/94 passed.
- `scripts/change-workflow.ps1 check`: PASS after quarantining a temporary probe outside the claimed worktree.
- Canonical full verification: pending.
- Review closure: pending.

## Provider and landing evidence

- Pull request exact head: pending.
- Provider-native GitHub Actions: pending.
- Merge / landed revision: pending.
- Documentation / Work reconciliation: pending.
- Cleanup: pending.

## Research return

- The surviving result is development-only and does not authorize >1 contract in paper, SIM, or LIVE.
- Fixed-scale gains are classified as exposure amplification, not new directional edge.
- Four asymmetric sizing variants showed positive allocation value versus nearest fixed-exposure controls, but failed the main promotion gate because of hard-safety and/or concentration behavior.

## Residual items

- Complete canonical verification, independent implementation review, PR/CI/merge, and Work closeout.
