$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$RepositoryPython = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $RepositoryPython)) {
    throw 'VERIFY_VENV_MISSING: create the repository .venv before verification.'
}
& (Join-Path $PSScriptRoot 'configure-repository.ps1')

Push-Location $RepositoryRoot
try {
    & $RepositoryPython scripts/check_public_hygiene.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_PUBLIC_HYGIENE_FAILED' }
    & $RepositoryPython scripts/check_documentation_authority.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_DOCUMENTATION_AUTHORITY_FAILED' }
    & $RepositoryPython scripts/check_research_methodology.py --check experiment-schema
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_SCHEMA_FAILED' }
    & $RepositoryPython scripts/check_research_methodology.py --check experiment-freeze-integrity
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_FREEZE_FAILED' }
    & $RepositoryPython scripts/check_research_methodology.py --check experiment-verification
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_EXPERIMENT_VERIFICATION_FAILED' }
    & $RepositoryPython scripts/check_research_methodology.py --check programme-inference-integrity
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_PROGRAMME_INFERENCE_FAILED' }
    & $RepositoryPython scripts/check_research_memory.py
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_RESEARCH_MEMORY_FAILED' }
    & $RepositoryPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_TESTS_FAILED' }
    & $RepositoryPython -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_LINT_FAILED' }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'VERIFY_WHITESPACE_FAILED' }
}
finally {
    Pop-Location
}
