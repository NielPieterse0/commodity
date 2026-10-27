$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$primary = (Resolve-Path -LiteralPath (Join-Path $repo '..\..\..')).Path
$legacy = (Resolve-Path -LiteralPath (Join-Path $primary '.work\worktrees\356-market-only-nested-walk-forward\.work\checkpoints\356-market-only-nested-walk-forward\inputs')).Path
foreach ($script in @('audit_calendar_parity.py', 'audit_technical_parity.py')) {
    Write-Host "START_AUDIT: $script"
    & docker run --rm --network none --cpus 2 --memory 2g --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,size=536870912 --mount "type=bind,source=$repo,target=/repo,readonly" --mount "type=bind,source=$legacy,target=/legacy,readonly" commodity-data-platform:issue487-v1 python "/repo/.work/changes/482-data-phase2-market-truth/$script"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
