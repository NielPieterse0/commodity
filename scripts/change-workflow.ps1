param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$KisRoot = 'C:\Projects\kis-mcp'
$GovernanceScript = Join-Path $KisRoot 'scripts\change-governance.py'
$GitWorkflowScript = Join-Path $KisRoot 'scripts\git-workflow.py'
$StateRoot = 'C:\Projects\.kis-mcp'

foreach ($Path in @($KisRoot, $GovernanceScript, $GitWorkflowScript)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "KIS_WORKFLOW_DEPENDENCY_MISSING: $Path"
    }
}

$env:KIS_STATE_ROOT = $StateRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $StateRoot 'python-env'
$env:UV_CACHE_DIR = Join-Path $StateRoot 'uv-cache'
$env:PYTHONPYCACHEPREFIX = Join-Path $StateRoot 'python-cache'
$env:TEMP = Join-Path $StateRoot 'temp'
$env:TMP = Join-Path $StateRoot 'temp'
$env:UV_OFFLINE = '1'
Push-Location $KisRoot
try {
    if ($CommandArguments.Count -ge 2 -and $CommandArguments[0] -eq 'cleanup') {
        & uv run --offline --no-sync python $GitWorkflowScript --repository $RepositoryRoot prepare-cleanup --change-id $CommandArguments[1]
        if ($LASTEXITCODE -ne 0) {
            throw "Change cleanup preparation failed with exit code $LASTEXITCODE"
        }
    }

    & uv run --offline --no-sync python $GovernanceScript --repository $RepositoryRoot @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Change governance failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
