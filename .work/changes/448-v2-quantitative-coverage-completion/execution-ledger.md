# SDD ledger â€” plan: .work/changes/448-v2-quantitative-coverage-completion/plan.md
Pre-flight: Task 1 contract feeds Tasks 3-6; Task 2 provider OI feeds Task 4. Interfaces match the plan.
Execution: inline; no implementer subagent available.
Environment: worktree-local `.venv` bootstrapped from the repository-approved Python 3.11.9 runtime.
Task 1: complete (tests: `python -m pytest tests/test_v2_coverage.py -k "contract or registry or disposition" -q` â†’ 5 passed).
Task 2: complete (tests: `python -m pytest tests/providers/test_databento_futures_provider.py -q` â†’ 42 passed).
Task 2 Ruling: normalize `ts_event`, `ts_recv`, and `ts_ref` to explicit UTC timestamps only on the new OI-specific interface; legacy DBN decoder output stays unchanged.
Task 3: complete (tests: `python -m pytest tests/test_v2_coverage.py -q` â†’ 9 passed).
Task 3 Ruling: Bollinger is represented as band position and stochastic/Williams-style states share the preregistered normalized-range family, so aliases cannot multiply trial credit.
Task 4: complete (tests: `python -m pytest tests/test_v2_coverage.py -q` â†’ 13 passed).
Task 4 Ruling: producer/merchant hedging pressure is `-producer_merchant_net / open_interest`, so positive values mean net short commercial hedging pressure; report changes are computed before daily PIT joining.
Task 5: complete (tests: `python -m pytest tests/test_v2_coverage.py -q` â†’ 19 passed).
Task 5 Ruling: exact release time is not flagged as executable; `first_executable_session_after_release` is the first strategy decision strictly after public availability. Options can score only from local/zero-dollar evidence with every activation gate satisfied and never authorize billable acquisition.
Ruling: store the execution ledger in the owned KIS change record instead of `.superpowers` scratch â€” repository scope/trackability rules take precedence â€” cost if wrong: extra tracked operational history only.