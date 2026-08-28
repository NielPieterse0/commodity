# Issue 215 review

WNGSR workbook parsing now fails closed when more than one candidate table is structurally admissible. The parser evaluates all history candidates and all revision candidates, preserves the existing direct-revision then legacy-revision fallback for each physical table, and accepts only a unique normalized result.

Regression coverage proves ambiguity failure for both history and revision workbooks. Existing WNGSR capture/current-ledger tests remain green.

Focused verification: 11 tests passed; Ruff and `git diff --check` passed. A local full-suite run reached 529 passing tests; the six remaining failures were unrelated Databento decoder tests blocked by Windows Application Control loading `databento_dbn._lib`. Provider CI remains the authoritative full-suite gate.

No source values, SHA lineage, revision timing, frozen feature meaning, tuning, empirical execution, or trading authority are changed by this slice.