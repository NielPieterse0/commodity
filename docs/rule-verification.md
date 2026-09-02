<!-- GENERATED FILE. DO NOT EDIT. Source: config/rule_verification.json -->

# Rule Verification

## Deterministically enforced rules

| Rule | Authority | Verifier | Enforcement |
| --- | --- | --- | --- |
| `public-repository-hygiene` | repository/publication hygiene (`scripts/checks/check_public_hygiene.py`) | `scripts/checks/check_public_hygiene.py` | pre-ci+ci |
| `documentation-authority` | maintained-document ownership and boundaries (`config/documentation_authority.json`) | `scripts/checks/check_documentation_authority.py` | pre-ci+ci |
| `python-environment-boundary` | active checkout/worktree Python environment boundary (`AGENTS.md`) | `scripts/checks/check_python_environment.py` | pre-ci+ci |
| `durable-evidence-references` | durable research evidence reference resolvability (`artifacts/research-metrics/longitudinal-ledger.json`) | `scripts/checks/check_durable_evidence_refs.py` | pre-ci+ci |
| `market-source-authority` | canonical market source selection, retained integrity, and evaluation/promotion boundary (`config/data_sources.json`) | `scripts/checks/check_market_source_authority.py` | pre-ci+ci |
| `dataset-assurance-contract` | deterministic dataset reconstruction and explicit semantic-verification boundary (`config/research_methodology.json`) | `scripts/checks/check_data_assurance_contract.py` | pre-ci+ci |
| `work-layout` | governed change and retained worktree lifecycle layout (`AGENTS.md`) | `scripts/checks/check_work_layout.py` | pre-ci+ci |
| `experiment-schema` | confirmatory experiment schema (`config/research_methodology.json`) | `scripts/checks/check_research_methodology.py --check experiment-schema` | pre-ci+ci |
| `experiment-freeze-integrity` | immutable preregistration and freeze evidence (`config/research_methodology.json`) | `scripts/checks/check_research_methodology.py --check experiment-freeze-integrity` | pre-ci+ci |
| `experiment-verification` | confirmatory execution/result verification (`config/research_methodology.json`) | `scripts/checks/check_research_methodology.py --check experiment-verification` | pre-ci+ci |
| `programme-inference-integrity` | programme inference registration (`research/programme/programme_inference_ledger.json`) | `scripts/checks/check_research_methodology.py --check programme-inference-integrity` | pre-ci+ci |
| `research-memory` | research decision/backlog projections (`research/experiments`) | `scripts/checks/check_research_memory.py` | pre-ci+ci |
| `tests` | repository executable contracts (`tests`) | `-m pytest -q` | pre-ci+ci |
| `lint` | Python static-quality rules (`pyproject.toml`) | `-m ruff check .` | pre-ci+ci |
| `whitespace` | Git whitespace policy (`.gitattributes`) | `git diff --check` | pre-ci+ci |

## Rules requiring external lifecycle state

These rules cannot be decided from repository bytes alone and remain under live lifecycle authority.

- `kis-runtime-governance` (`AGENTS.md`): requires live external KIS runtime state and workflow evidence; not decidable from repository bytes alone
- `work-management-state` (`AGENTS.md`): requires external Work/GitHub lifecycle state; enforced by KIS rather than repository pre-CI
- `exact-head-merge-policy` (`CONTRIBUTING.md`): requires provider-native pull-request and Actions state; enforced by KIS closeout workflow
- `secret-history-review` (`SECURITY.md`): publication-wide history/ref review is provider/lifecycle scoped; current-tree hygiene remains pre-CI verified
