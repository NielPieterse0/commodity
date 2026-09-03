$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$RepositoryPython = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $RepositoryPython)) {
    throw 'VERIFY_VENV_MISSING: create the repository .venv before verification.'
}
& (Join-Path $PSScriptRoot 'environment\configure-repository.ps1')

Push-Location $RepositoryRoot
try {
    & $RepositoryPython scripts/checks/check_rule_verification.py --check-generated
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_RULE_REGISTRY_FAILED' }
    & $RepositoryPython scripts/checks/check_python_environment.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_PYTHON_ENVIRONMENT_FAILED' }
    & $RepositoryPython scripts/checks/check_durable_evidence_refs.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_DURABLE_EVIDENCE_REFS_FAILED' }
    & $RepositoryPython scripts/checks/check_market_source_authority.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_MARKET_SOURCE_AUTHORITY_FAILED' }
    & $RepositoryPython scripts/checks/check_data_assurance_contract.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_DATA_ASSURANCE_CONTRACT_FAILED' }
    & $RepositoryPython scripts/checks/check_work_layout.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_WORK_LAYOUT_FAILED' }
    & $RepositoryPython scripts/checks/check_public_hygiene.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_PUBLIC_HYGIENE_FAILED' }
    & $RepositoryPython scripts/checks/check_documentation_authority.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_DOCUMENTATION_AUTHORITY_FAILED' }
    & $RepositoryPython scripts/checks/check_research_methodology.py --check experiment-schema
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_SCHEMA_FAILED' }
    & $RepositoryPython scripts/checks/check_research_methodology.py --check experiment-freeze-integrity
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_FREEZE_FAILED' }
    & $RepositoryPython scripts/checks/check_research_methodology.py --check experiment-verification
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_VERIFICATION_FAILED' }
    & $RepositoryPython scripts/checks/check_research_methodology.py --check programme-inference-integrity
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_PROGRAMME_INFERENCE_FAILED' }
    & $RepositoryPython scripts/checks/check_research_metrics.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_RESEARCH_METRICS_FAILED' }
    & $RepositoryPython scripts/checks/check_research_memory.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_RESEARCH_MEMORY_FAILED' }
    & $RepositoryPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_TESTS_FAILED' }
    & $RepositoryPython -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_LINT_FAILED' }
    & $RepositoryPython scripts/checks/check_git_whitespace.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_WHITESPACE_FAILED' }
}
finally {
    Pop-Location
}
