from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "environment" / "run_python.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("commodity_run_python", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

def _layout(tmp_path: Path):
    commodity_root = tmp_path / "commodity"
    worktree = commodity_root / ".work" / "worktrees" / "change"
    script = worktree / "scripts" / "environment" / "run_python.py"
    python = worktree / ".venv" / "Scripts" / "python.exe"
    script.parent.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    script.write_text("# runner\n", encoding="utf-8")
    python.write_bytes(b"")
    return commodity_root, worktree, script, python


def test_resolve_context_accepts_active_worktree_venv(tmp_path: Path):
    commodity_root, worktree, script, python = _layout(tmp_path)

    context = runner.resolve_context(script, python, commodity_root)

    assert context.repo_root == worktree.resolve()
    assert context.python == python.resolve()
    assert context.runtime_root.is_relative_to(commodity_root.resolve())

@pytest.mark.parametrize(
    "wrong_python_factory",
    [
        lambda root: root / ".venv" / "Scripts" / "python.exe",
        lambda root: root / ".work" / "worktrees" / "sibling" / ".venv" / "Scripts" / "python.exe",
        lambda root: root.parent / "external" / ".venv" / "Scripts" / "python.exe",
    ],
)
def test_resolve_context_rejects_interpreters_outside_active_worktree(
    tmp_path: Path, wrong_python_factory
):
    commodity_root, worktree, script, _python = _layout(tmp_path)
    wrong_python = wrong_python_factory(commodity_root)
    wrong_python.parent.mkdir(parents=True)
    wrong_python.write_bytes(b"")
    assert not wrong_python.resolve().is_relative_to(worktree.resolve())

    with pytest.raises(runner.RunnerError, match="RUNNER_PYTHON_MISMATCH"):
        runner.resolve_context(script, wrong_python, commodity_root)


def test_resolve_context_rejects_repo_outside_commodity_root(tmp_path: Path):
    commodity_root = tmp_path / "commodity"
    worktree = tmp_path / "other" / "change"
    script = worktree / "scripts" / "environment" / "run_python.py"
    python = worktree / ".venv" / "Scripts" / "python.exe"
    script.parent.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    script.write_text("# runner\n", encoding="utf-8")
    python.write_bytes(b"")

    with pytest.raises(runner.RunnerError, match="RUNNER_ROOT_OUTSIDE_COMMODITY"):
        runner.resolve_context(script, python, commodity_root)

def test_build_environment_keeps_managed_paths_inside_commodity(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)

    env = runner.build_environment(context, {"PATH": "existing"})

    for key in (
        "TMP",
        "TEMP",
        "TMPDIR",
        "PYTHONPYCACHEPREFIX",
        "RUFF_CACHE_DIR",
        "PIP_CACHE_DIR",
        "XDG_CACHE_HOME",
        "COMMODITY_RUNNER_ROOT",
    ):
        assert Path(env[key]).resolve().is_relative_to(commodity_root.resolve())
    assert env["PATH"] == "existing"

@pytest.mark.parametrize(
    ("argv", "expected_prefix"),
    [
        (["pytest", "tests/test_x.py", "-q"], ["-m", "pytest"]),
        (["ruff", "check", "."], ["-m", "ruff"]),
        (["module", "commodity.cli", "--help"], ["-m", "commodity.cli"]),
        (["python", "-c", "print(1)"], ["-c", "print(1)"]),
    ],
)
def test_build_command_uses_active_venv_python(
    tmp_path: Path, argv: list[str], expected_prefix: list[str]
):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)

    command = runner.build_command(context, argv)

    assert command[0] == str(python.resolve())
    joined = command[1:]
    for token in expected_prefix:
        assert token in joined


def test_python_command_preserves_argument_vector_exactly(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)
    arguments = ["-c", "import sys; print(sys.argv[1:])", "a b", 'quote"value', "", "Δ"]

    command = runner.build_command(context, ["python", *arguments])

    assert command == [str(python.resolve()), *arguments]


def test_pytest_command_forces_repository_local_cache(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)

    command = runner.build_command(context, ["pytest", "-q"])

    cache_option = next(item for item in command if item.startswith("cache_dir="))
    cache_path = Path(cache_option.split("=", 1)[1])
    assert cache_path.resolve().is_relative_to(commodity_root.resolve())


def test_script_command_rejects_path_outside_worktree(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")

    with pytest.raises(runner.RunnerError, match="RUNNER_SCRIPT_OUTSIDE_WORKTREE"):
        runner.build_command(context, ["script", str(outside)])

def test_run_record_tracks_child_pid_and_terminal_exit(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)
    command = runner.build_command(context, ["python", "-c", "print(1)"])

    record_path = runner.write_running_record(
        context, "python", command, child_pid=4242, launcher_pid=3131
    )
    running = json.loads(record_path.read_text(encoding="utf-8"))
    assert running["state"] == "running"
    assert running["pid"] == 4242
    assert "argv_sha256" in running
    assert "argv" not in running

    runner.finish_run_record(record_path, exit_code=7)
    completed = json.loads(record_path.read_text(encoding="utf-8"))
    assert completed["state"] == "completed"
    assert completed["exit_code"] == 7

def test_reconcile_marks_missing_running_pid_interrupted(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)
    command = runner.build_command(context, ["python", "-c", "print(1)"])
    record_path = runner.write_running_record(
        context, "python", command, child_pid=9999, launcher_pid=3131
    )

    record = runner.reconcile_run_record(record_path, pid_exists=lambda _pid: False)

    assert record["state"] == "interrupted"
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "interrupted"


def test_pid_probe_does_not_signal_live_child(tmp_path: Path):
    commodity_root, _worktree, script, python = _layout(tmp_path)
    context = runner.resolve_context(script, python, commodity_root)
    command = runner.build_command(context, ["python", "-c", "print(1)"])
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=creationflags,
    )
    try:
        record_path = runner.write_running_record(
            context, "python", command, child_pid=child.pid, launcher_pid=3131
        )
        running = runner.reconcile_run_record(record_path)
        assert running["state"] == "running"
        assert child.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)

    interrupted = runner.reconcile_run_record(record_path)
    assert interrupted["state"] == "interrupted"


def test_cmd_shim_launches_venv_python_without_powershell():
    shim = (REPO_ROOT / "scripts" / "run.cmd").read_text(encoding="utf-8").lower()

    assert "powershell" not in shim
    assert ".venv\\scripts\\python.exe" in shim
    assert "scripts\\environment\\run_python.py" in shim
