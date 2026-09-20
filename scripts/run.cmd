@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
set "RUNNER=%REPO_ROOT%\scripts\environment\run_python.py"
if not exist "%PYTHON%" (
  echo RUNNER_VENV_MISSING: %PYTHON% 1>&2
  exit /b 3
)
if not exist "%RUNNER%" (
  echo RUNNER_IMPLEMENTATION_MISSING: %RUNNER% 1>&2
  exit /b 4
)
"%PYTHON%" "%RUNNER%" %*
exit /b %ERRORLEVEL%
