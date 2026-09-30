# Spec: 427-v2-model-family-optimization

## Scientific authority

- L3 preregistration: `research/programmes/004-v2-maximum-reproducible-one-month-return/issue427-prereg-v1.json`
- Frozen prereg SHA256: `3ff25238408e701f344c7aacb0c60205a037eb4f97d0a7511e46d31c564dc551`
- Human-facing slice: GitHub issue #427.

## Repository mapping

Implement only the execution machinery required by the frozen preregistration:
- parameterized Ridge/HistGB baseline construction with legacy defaults preserved;
- bounded nested model selection and matched feature-ablation execution;
- inherited #448 PIT feature reconstruction and row-identity checks;
- specialist-role evaluation using already-pinned local artifacts only;
- deterministic result and trial-ledger persistence under programme 004.

Do not change target, execution, cost, paper risk, protected-evidence, or source-acquisition policy outside the L3 authority.
