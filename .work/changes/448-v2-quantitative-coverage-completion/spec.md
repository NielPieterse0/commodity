# Change Specification: V2 Quantitative Coverage Completion

- **Change ID**: `448-v2-quantitative-coverage-completion`
- **Status**: Ready for design review
- **Complexity**: large
- **Work**: `WORK-448` / GitHub issue #448
- **Programme**: #393 / `004-v2-maximum-reproducible-one-month-return`

## Scientific authority

This KIS specification is only the repository implementation mapping. It does not redefine the research design.

- L3/preregistered authority: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-prereg-v2.json`
- Preregistration SHA-256: `0695fe4944739be2728a70579096e60dab00e7a048232a988faca7adc13de64d`
- Source-feasibility authority: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-source-feasibility-v2.json`
- Source-feasibility SHA-256: `4e7f63f696097820ed3a6bc2c3b1aaf255744989132d0ac98f4bc7b5605bd7b5`
- Research boundary: development evidence through `2022-12-31` only; protected confirmation, prospective paper, SIM, LIVE, and V3 LLM/unstructured evidence remain unopened.

## Repository mapping

1. `src/commodity/v2_coverage.py`
   - Own deterministic #448 feature construction and validation for the preregistered technical-analysis, carry/basis, OI/liquidity, positioning and scheduled-event representations.
   - Expose explicit feature-family identities so downstream #427/#428 can consume them without redefining #448 semantics.
   - Fail closed on unavailable/ambiguous point-in-time inputs and on attempts to label non-consensus storage information as market surprise.

2. `src/commodity/providers/databento_futures.py`
   - Extend the existing Statistics decoder only as required for preregistered PIT open interest (`stat_type=9`) and zero-spend options feasibility metadata/statistics.
   - Preserve settlement/volume behavior and provenance.
   - Do not perform billable acquisition.

3. `tests/test_v2_coverage.py` and `tests/providers/test_databento_futures_provider.py`
   - Drive implementation test-first.
   - Verify exact preregistered grids/contracts, primitive-ablation identity, PIT availability, no silent storage-surprise substitution, event-time boundaries, and provider OI decoding.

4. Canonical configuration owners
   - Change `config/data_sources.json`, `config/research_dataset.json`, or `config/models.json` only where executable source/model/interface authority requires it.
   - Generated `docs/**` are not hand-edited; documentation projections are regenerated only when canonical owners change.

5. Programme evidence
   - `issue448-result-v1.json` and `issue448-trials-v1.jsonl` own empirical outcome/trial evidence after implementation is frozen.
   - `evidence-map.json`, `decisions.json`, and `revisit-triggers.json` are reconciled from #448 evidence after scoring.

## Acceptance mapping

- Traditional TA: every preregistered family is implemented as a bounded representation and compared against its matched primitive-feature control; algebraic aliases do not multiply search credit.
- Market structure: DTE-normalized basis/carry, basis momentum, curve dynamics, OI/liquidity and positioning/hedging-pressure representations are PIT-safe and auditable.
- Storage surprise: activation remains impossible unless the preregistered true pre-release consensus gate passes; current source disposition is HOLD.
- Event timing: WNGSR release-state features use the repository availability contract and never imply same-instant/HFT execution.
- Volatility/tail: interfaces/requirements for #427/#428/#430 are registered without fitting those downstream model families inside #448.
- Options: only zero-spend feasibility/inventory work is allowed until depth, timestamp, rights and cost gates pass; options cannot block V2.
- Research integrity: chronological development-only selection, complete trial accounting, search-budget controls, V1 immutability and protected-evidence boundaries remain enforced.

## Risks and recovery

- **PIT ambiguity**: fail closed and record HOLD/revisit evidence rather than infer publication times.
- **Duplicate information / indicator zoo**: require primitive-feature ablations and shared family identities for algebraically equivalent indicators.
- **Paid data**: no paid Databento/options or consensus acquisition without a separate governed cost decision.
- **Provider regression**: extend the existing decoder minimally and preserve current settlement/volume tests.
- **Scientific ambiguity discovered during implementation**: stop implementation and return to the preregistration/source-feasibility authority; do not silently redesign inside code.

## Out of scope

- Model-family fitting/selection owned by #427.
- Regime/fusion/confidence/decision-rule optimization owned by #428.
- Entry/exit/holding structure (#429), sizing/risk (#430), execution/roll/cost adaptation (#431).
- V3 LLM/RAG/news/document extraction.
- Calendar-spread trading as a new multi-leg target.
- Protected confirmation, prospective paper, Saxo SIM or LIVE evidence.
