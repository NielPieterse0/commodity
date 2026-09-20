from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunnerContext:
    repo_root: Path
    commodity_root: Path
    python: Path
    runtime_root: Path


def _resolve(path: Path) -> Path:
    return path.resolve(strict=False)


def _find_repo_root(script_path: Path) -> Path:
    return _resolve(script_path).parents[2]

def _find_commodity_root(repo_root: Path) -> Path:
    repo_root = _resolve(repo_root)
    parts = repo_root.parts
    try:
        index = next(i for i, part in enumerate(parts) if part.lower() == "commodity")
    except StopIteration as exc:
        raise RunnerError("RUNNER_ROOT_OUTSIDE_COMMODITY") from exc
    return Path(*parts[: index + 1])


def resolve_context(
    script_path: Path | None = None,
    python_path: Path | None = None,
    commodity_root: Path | None = None,
) -> RunnerContext:
    script = _resolve(script_path or Path(__file__))
    repo_root = _find_repo_root(script)
    root = _resolve(commodity_root or _find_commodity_root(repo_root))
    if not repo_root.is_relative_to(root):
        raise RunnerError("RUNNER_ROOT_OUTSIDE_COMMODITY")
    python = _resolve(python_path or repo_root / ".venv" / "Scripts" / "python.exe")
    expected = _resolve(repo_root / ".venv" / "Scripts" / "python.exe")
    if python != expected:
        raise RunnerError("RUNNER_PYTHON_MISMATCH")
    if not python.exists():
        raise RunnerError("RUNNER_VENV_MISSING")
    runtime_root = root / ".work" / "runtime" / "python-runner"
    return RunnerContext(repo_root=repo_root, commodity_root=root, python=python, runtime_root=runtime_root)

def build_environment(context: RunnerContext, base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    cache_root = context.runtime_root / "cache"
    temp_root = context.runtime_root / "tmp"
    for path in (cache_root, temp_root):
        path.mkdir(parents=True, exist_ok=True)
    managed = {
        "TMP": temp_root,
        "TEMP": temp_root,
        "TMPDIR": temp_root,
        "PYTHONPYCACHEPREFIX": cache_root / "pycache",
        "RUFF_CACHE_DIR": cache_root / "ruff",
        "PIP_CACHE_DIR": cache_root / "pip",
        "XDG_CACHE_HOME": cache_root / "xdg",
        "COMMODITY_RUNNER_ROOT": context.runtime_root,
    }
    for key, value in managed.items():
        value.mkdir(parents=True, exist_ok=True)
        env[key] = str(value)

    venv_root = context.repo_root / ".venv"
    venv_scripts = venv_root / "Scripts"
    env["VIRTUAL_ENV"] = str(venv_root)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = str(context.repo_root / "src")
    env.pop("PYTHONHOME", None)
    inherited_path = env.get("PATH", "")
    env["PATH"] = str(venv_scripts) + (os.pathsep + inherited_path if inherited_path else "")
    return env


def build_command(context: RunnerContext, argv: list[str]) -> list[str]:
    if not argv:
        raise RunnerError("RUNNER_COMMAND_REQUIRED")
    mode, *rest = argv
    if mode == "pytest":
        return [str(context.python), "-m", "pytest", "-o", f"cache_dir={context.runtime_root / 'cache' / 'pytest'}", *rest]
    if mode == "ruff":
        return [str(context.python), "-m", "ruff", *rest]
    if mode == "module":
        if not rest:
            raise RunnerError("RUNNER_MODULE_REQUIRED")
        return [str(context.python), "-m", *rest]

    if mode == "script":
        if not rest:
            raise RunnerError("RUNNER_SCRIPT_REQUIRED")
        requested = Path(rest[0])
        script = _resolve(requested if requested.is_absolute() else context.repo_root / requested)
        if not script.is_relative_to(context.repo_root):
            raise RunnerError("RUNNER_SCRIPT_OUTSIDE_WORKTREE")
        return [str(context.python), str(script), *rest[1:]]
    if mode == "python":
        return [str(context.python), *rest]
    raise RunnerError(f"RUNNER_UNKNOWN_MODE:{mode}")


def _record_dir(context: RunnerContext) -> Path:
    path = context.runtime_root / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(path)


def write_running_record(
    context: RunnerContext,
    mode: str,
    command: list[str],
    *,
    child_pid: int,
    launcher_pid: int,
) -> Path:
    digest = hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{child_pid}"

    path = _record_dir(context) / f"{run_id}.json"
    _write_json(
        path,
        {
            "schema_version": 1,
            "state": "running",
            "mode": mode,
            "pid": child_pid,
            "launcher_pid": launcher_pid,
            "started_at": datetime.now(UTC).isoformat(),
            "argv_sha256": digest,
            "worktree": str(context.repo_root),
            "python": str(context.python),
        },
    )
    return path


def finish_run_record(path: Path, *, exit_code: int) -> dict[str, object]:
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(
        {
            "state": "completed",
            "exit_code": int(exit_code),
            "finished_at": datetime.now(UTC).isoformat(),
        }
    )
    _write_json(path, record)
    return record


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        handle = open_process(synchronize, False, pid)
        if not handle:
            return False
        try:
            return wait_for_single_object(handle, 0) == wait_timeout
        finally:
            close_handle(handle)

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def reconcile_run_record(path: Path, *, pid_exists=_pid_exists) -> dict[str, object]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("state") == "running" and not pid_exists(int(record["pid"])):
        record["state"] = "interrupted"
        record["finished_at"] = datetime.now(UTC).isoformat()
        _write_json(path, record)
    return record

def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    context = resolve_context()
    if args[:1] == ["status"]:
        records = sorted(_record_dir(context).glob("*.json"))
        for path in records:
            record = reconcile_run_record(path)
            print(json.dumps(record, sort_keys=True))
        return 0
    command = build_command(context, args)
    env = build_environment(context)
    proc = subprocess.Popen(command, cwd=context.repo_root, env=env)
    record_path = write_running_record(
        context,
        args[0],
        command,
        child_pid=proc.pid,
        launcher_pid=os.getpid(),
    )
    exit_code = proc.wait()
    finish_run_record(record_path, exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
