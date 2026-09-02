$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $RepositoryRoot
try {
    & git rev-parse --is-inside-work-tree | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'REPOSITORY_GIT_UNAVAILABLE: repository root is not a Git worktree.'
    }

    & git config --local core.autocrlf false
    & git config --local core.eol lf
    & git config --local core.safecrlf true

    $Expected = [ordered]@{
        'core.autocrlf' = 'false'
        'core.eol' = 'lf'
        'core.safecrlf' = 'true'
    }
    foreach ($Entry in $Expected.GetEnumerator()) {
        $Actual = (& git config --local --get $Entry.Key).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $Actual -ne $Entry.Value) {
            throw "REPOSITORY_GIT_CONFIG_INVALID: $($Entry.Key) must be $($Entry.Value)."
        }
    }
}
finally {
    Pop-Location
}
