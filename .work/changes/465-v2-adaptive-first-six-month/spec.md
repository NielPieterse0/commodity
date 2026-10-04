# Change Specification: V2 Adaptive First Six Month

- **Change ID**: `465-v2-adaptive-first-six-month`
- **Status**: Active; frozen v1/controller-v2 predecessor evidence preserved, controller-v3 scope-completion implementation and Block-1 verification in progress
- **Complexity**: `large` per `scope.json`; risk trigger `money`

## Outcome

Preserve the already-scored block-1 v1 and controller-v2 iterations as immutable predecessor evidence, then use the live Issue #465 authority to preregister and implement a separate controller-v3 scope-completion iteration on the same 2010-07-06 through 2011-01-06 block. Controller v3 must complete the eight-stage controller with independent long/short profiles; independent strict-prior memory-scale selection per specialist×horizon×direction across all 5/10/20/40/60/126/252/expanding memories; genuine WAIT/ENTER_NOW/ABSTAIN timing; complete position lifecycle; trading-session age; decision-time MTM/MFE/MAE; remaining-edge lifecycle actions; dynamic sizing/leverage/margin controls; execution stress and missed fills; roll turnover costs; prior-only scoring; stress-gated structural competition; actual-state ensemble lifecycle controls; full consequence storage; native 20-session TimesFM/Kronos trajectories with horizon-specific expert use and explicit path-shape/interval/disagreement context; forecast-error/hit/calibration history; a primitive hindsight-winner oracle plus a dedicated strict-prior predictor of its policy_id/specialist/horizon/direction identity; the full 53-attribute hindsight oracle plus strict-prior oracle-weight predictor; oracle-first diagnostics; and future-mutation invariance proof. Block 2 and protected 2023+ data remain sealed.

## Authority and scope

- Scientific authority: live GitHub Issue #465 plus `research/programmes/004-v2-maximum-reproducible-one-month-return/lines/001-v2-optimization-execution/line.json`. The scored v1 and controller-v2 artifacts remain frozen predecessor evidence, not controller-v3 authority.
- Controller-v3 scientific freeze: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue465-block1-controller-v3-prereg.json`, written before controller-v3 empirical scoring, with the corrected scoring-code identity bound by the regenerated no-scoring preflight.
- Executable controller-v3 authority: `src/commodity/v2_adaptive_controller_v3.py`, `scripts/research/run_issue465_block1_controller_v3.py`, v3 tests/evidence, and unchanged admissible predecessor PIT/source identities used as inputs.
- Owned/shared/excluded paths and Work identity: `scope.json`.

## Requirements mapping

- `src/commodity/v2_adaptive_controller.py`: enforce PIT/protected-boundary contracts, prior-only consequence maturation, deterministic policy selection, adaptive ledger, and oracle diagnostic primitives required by the frozen preregistration.
- `scripts/research/run_issue465_adaptive_block.py`: construct/freeze only block 1, validate source identities and executable decisions, materialize required artifacts, and fail closed on later/protected access.
- `tests/test_issue465_adaptive_controller.py` and `tests/test_issue465_adaptive_runner.py`: preserve causal invariants, deterministic freeze behavior, duplicate-fill canonicalization, punctuation-safe policy IDs, and protected/later-block seals.
- Existing v1 source/runner/tests and `issue465-block1-*-v1` artifacts remain immutable predecessor evidence.
- Controller-v2 source, runner, tests, and scored artifacts remain immutable predecessor evidence for the v3 scope-completion pass.
- `src/commodity/v2_adaptive_controller_v3.py`: implement independent side profiles; independently select the useful strict-prior memory scale for each specialist×horizon×direction from the full eight-memory bank while treating side-profile memory sets only as deterministic tie-break preferences; expose the selected memory and one-hot memory weights in opportunity/brain state; implement tri-state entry timing, complete add/reduce/exit/reverse lifecycle, trading-session age, decision-time path accounting, dynamic causal sizing, leverage/margin controls, execution/roll stress, prior-only candidate scoring, stress-gated competition, and actual-ensemble-state lifecycle control. REDUCE must require either configured edge deterioration or a binding hard risk cap; a soft desired-size decrease alone must not force reduction.
- `scripts/research/run_issue465_block1_controller_v3.py`: freeze and replay all 96 v3 structural candidates across three execution scenarios; use native TimesFM/Kronos 1/3/5/10/20 opinions plus path-shape/interval/disagreement comparable-state context; maintain strict-prior economic, hit-rate, forecast-error, and calibration histories; materialize the primitive hindsight winner and a dedicated strict-prior, development-only predictor of policy_id/specialist/horizon/direction; materialize the 53-attribute hindsight oracle and causal oracle-weight predictor; run the causal meta-controller; materialize oracle-first/trial/decision-brain/consequence/ledger/result evidence; and execute deterministic future-state/outcome/expert/predictor mutation replay without opening later blocks. Candidate scoring must checkpoint each completed candidate's three scenario replays atomically, maintain a durable progress manifest, resume only identity-matching checkpoints, and emit progress after every candidate as `n/96` rather than batching updates.
- The attribute oracle must solve the exact after-cost 0.25-contract exposure lattice over 1/3/5/10/20-session horizons, retain the canonical minimum-L2 dense 53-attribute solution and globally minimum-norm sparse 1/2/4/8/16-attribute solutions, and evaluate strict-prior prediction of side, exposure, sparse attribute identity, and weight vector. Oracle outputs remain development-only and excluded from selection.
- Controller-v3 tests: prove causal outcome isolation, independent full-bank memory selection per specialist×horizon×direction, strict-prior primitive winner identity prediction, sparse weight support, comparable-state prior-only use, complete lifecycle/path accounting including REDUCE deterioration semantics, side asymmetry, execution degradation, ensemble-state controls, deterministic replay, atomic checkpoint round-trips, streaming output behavior, artifact identity, and future-invariance behavior.

## Acceptance

1. Focused issue-465 tests, the full repository test suite, lint, documentation, methodology, and whitespace gates pass from the isolated worktree.
2. Required controller-v3 block-1 artifacts are deterministic and hash-bound to the frozen preregistration, corrected no-scoring preflight, executable identity, and source identities.
3. Result and ledger evidence record `protected_confirmation_accessed=false`, `later_blocks_accessed=false`, exactly 96 structural candidates / 288 candidate-scenario replays, and complete 123-row decision/consequence archives.
4. Full future-state/outcome/expert mutation replay records `PASS` with invariant causal decision prefixes and unchanged specialist/effectiveness/comparable-state/meta-controller state plus invariant strict-prior attribute-oracle and primitive-winner predictor prefixes across all 288 replays.
5. The literal V3 Block-1 completeness audit passes every recorded agreed-feature check, including independent per-quantity memory-scale selection, primitive winner identity predictability, live expert-path context, native-target forecast diagnostics, the attribute-weight oracle/predictor, complete brain/consequence storage, and protected/later-block seals.
6. KIS exact-source verification and implementation review close without unresolved findings before publication.

## Risks and recovery

- Risk: money-sensitive research code can create misleading performance through leakage, duplicate fills, non-causal selection, or accidental protected/later-block access.
- Recovery: fail closed, preserve the frozen evidence identity, correct implementation-only defects before scoring where possible, and return to scientific authority rather than altering the frozen design after observing block-1 outcomes.

## Out of scope

- Block 2 or any later six-month block.
- Protected 2023+ confirmation, prospective paper, Saxo SIM, or LIVE evidence.
- Mutating or rescoring the already-scored v1 or controller-v2 procedures. Controller v3 is a separately preregistered scope-completion iteration with separate artifacts and identity.
