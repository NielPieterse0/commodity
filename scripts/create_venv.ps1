param(
    [string]$PythonPath = $env:COMMODITY_PYTHON,
    [string]$VenvPath = ".venv",
    [switch]$InstallLockedDependencies
)

$ErrorActionPreference = "Stop"
$projectsRoot = (Resolve-Path -LiteralPath "C:\Projects").Path.TrimEnd('\')
$repoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path.TrimEnd('\')

if (-not $PythonPath) {
    throw "No Python selected. Set COMMODITY_PYTHON or pass -PythonPath to the canonical Projects-local python.exe."
}

$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
if (-not $resolvedPython.StartsWith($projectsRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing Python outside Projects root: $resolvedPython"
}
if ([IO.Path]::GetFileName($resolvedPython) -ne 'python.exe') {
    throw "Selected interpreter is not python.exe: $resolvedPython"
}

$pythonBase = (Split-Path -Parent $resolvedPython)
& $resolvedPython -c "import sys; assert sys.base_prefix.lower() == r'$pythonBase'.lower(), sys.base_prefix"
if ($LASTEXITCODE -ne 0) {
    throw "Selected Python is not a base interpreter at its declared Projects-local installation: $resolvedPython"
}
$candidateVenv = if ([IO.Path]::IsPathRooted($VenvPath)) {
    [IO.Path]::GetFullPath($VenvPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $VenvPath))
}
if (-not $candidateVenv.StartsWith($repoRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing virtual environment outside repository root: $candidateVenv"
}
if ($candidateVenv -eq $repoRoot) {
    throw "Refusing to replace the repository root."
}

if (Test-Path -LiteralPath $candidateVenv) {
    $existingConfig = Join-Path $candidateVenv 'pyvenv.cfg'
    if (-not (Test-Path -LiteralPath $existingConfig -PathType Leaf)) {
        throw "Refusing to replace a non-venv directory: $candidateVenv"
    }
    Remove-Item -LiteralPath $candidateVenv -Recurse -Force
}
& $resolvedPython -m venv $candidateVenv
if ($LASTEXITCODE -ne 0) { throw "Virtual-environment creation failed." }

$venvPython = Join-Path $candidateVenv 'Scripts\python.exe'
& $venvPython -c "import sys; assert sys.base_prefix.lower() == r'$pythonBase'.lower(); print(sys.executable); print(sys.base_prefix)"
if ($LASTEXITCODE -ne 0) { throw "Virtual-environment verification failed." }
if ($InstallLockedDependencies) {
    $lockFile = Join-Path $repoRoot 'requirements.lock.txt'
    if (-not (Test-Path -LiteralPath $lockFile -PathType Leaf)) {
        throw "Locked requirements not found: $lockFile"
    }
    & $venvPython -m pip install --no-deps -r $lockFile
    if ($LASTEXITCODE -ne 0) { throw "Locked dependency installation failed." }
    & $venvPython -m pip install -e $repoRoot --no-deps
    if ($LASTEXITCODE -ne 0) { throw "Editable project installation failed." }
}
