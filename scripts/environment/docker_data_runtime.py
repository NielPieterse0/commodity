"""Bounded Windows-native/Docker execution of the commodity data benchmark."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "docker" / "data-platform"
DOCKERFILE = CONTEXT / "Dockerfile"
LOCKFILE = CONTEXT / "requirements.txt"
IMAGE = "commodity-data-platform:issue487-v1"
RUNTIME = ROOT / ".work" / "runtime" / "docker-data-platform"
IMAGE_RECORD = RUNTIME / "image-lock.json"
BASE_DIGEST = "sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89"
SCRIPT = "scripts/data/benchmark_data_platform.py"
BLOCKED = re.compile(
    r"(?i)(blocked by (?:group|application) policy|"
    r"windows defender application control|app control|"
    r"winerror (?:577|1260)|0x800704ec|0xc0000428)"
)


class RuntimeFailure(RuntimeError):
    """Fail-closed, actionable runtime failure."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise RuntimeFailure(f"RUNTIME_PROCESS_UNAVAILABLE:{argv[0]}:{type(exc).__name__}") from exc


def _check(result: subprocess.CompletedProcess[str], code: str) -> str:
    if result.returncode:
        raise RuntimeFailure(f"{code}:exit={result.returncode}:{result.stderr.strip()[:600]}")
    return result.stdout.strip()


def docker_info() -> dict[str, object]:
    result = _run(["docker", "info", "--format", "{{json .}}"])
    raw = _check(result, "DOCKER_DAEMON_UNAVAILABLE")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeFailure("DOCKER_INFO_INVALID") from exc
    if info.get("OSType") != "linux":
        raise RuntimeFailure("DOCKER_LINUX_BACKEND_REQUIRED")
    return info


def image_info() -> dict[str, object]:
    result = _run(["docker", "image", "inspect", IMAGE, "--format", "{{json .}}"])
    raw = _check(result, "DOCKER_IMAGE_MISSING_BUILD_FIRST")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeFailure("DOCKER_IMAGE_METADATA_INVALID") from exc


def image_evidence() -> dict[str, str]:
    return {
        "base_digest": BASE_DIGEST,
        "dockerfile_sha256": file_sha256(DOCKERFILE),
        "lock_sha256": file_sha256(LOCKFILE),
    }


def _validate_image(record: dict[str, object], image: dict[str, object]) -> None:
    if image.get("Os") != "linux" or image.get("Architecture") != "amd64":
        raise RuntimeFailure("DOCKER_IMAGE_ARCH_UNSUPPORTED")
    if record.get("image_id") != image.get("Id"):
        raise RuntimeFailure("DOCKER_IMAGE_DIGEST_MISMATCH")
    labels = image.get("Config", {}).get("Labels", {})
    evidence = image_evidence()
    for key, value in evidence.items():
        if record.get(key) != value:
            raise RuntimeFailure(f"DOCKER_BUILD_INPUT_CHANGED:{key}")
    if labels.get("org.commodity.lock-sha256") != evidence["lock_sha256"]:
        raise RuntimeFailure("DOCKER_LOCK_LABEL_MISMATCH")
    if labels.get("org.commodity.dockerfile-sha256") != evidence["dockerfile_sha256"]:
        raise RuntimeFailure("DOCKER_DOCKERFILE_LABEL_MISMATCH")


def build_image() -> dict[str, str]:
    docker_info()
    from_lines = [line.strip() for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
                  if re.match(r"(?i)^\s*FROM\s+", line)]
    base_line = f"python:3.11.17-slim-bookworm@{BASE_DIGEST}"
    if len(from_lines) != 1 or from_lines[0] not in {
        f"FROM {base_line}", f"FROM --platform=linux/amd64 {base_line}",
    }:
        raise RuntimeFailure("DOCKER_BASE_DIGEST_MISMATCH")
    evidence = image_evidence()
    command = [
        "docker", "build", "--platform", "linux/amd64",
        "--file", str(DOCKERFILE), "--tag", IMAGE,
        "--build-arg", f"LOCK_SHA256={evidence['lock_sha256']}",
        "--build-arg", f"DOCKERFILE_SHA256={evidence['dockerfile_sha256']}",
        str(CONTEXT),
    ]
    _check(_run(command), "DOCKER_BUILD_FAILED")
    image = image_info()
    record = {**evidence, "image_id": str(image.get("Id", ""))}
    _validate_image(record, image)
    _runtime_path(IMAGE_RECORD)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    safe_directory = _runtime_path(RUNTIME)
    # Atomic replacement changes the destination entry, never follows its symlink.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=safe_directory, prefix=".image-lock-",
                                     suffix=".tmp", delete=False) as stream:
        stream.write(json.dumps(record, sort_keys=True, indent=2) + "\n")
        temporary_record = Path(stream.name)
    _runtime_path(IMAGE_RECORD)
    os.replace(temporary_record, IMAGE_RECORD)
    return record


def verify_image() -> dict[str, str]:
    docker_info()
    _runtime_path(IMAGE_RECORD)
    if not IMAGE_RECORD.is_file():
        raise RuntimeFailure("DOCKER_IMAGE_LOCK_MISSING_RUN_BUILD_FIRST")
    try:
        record = json.loads(IMAGE_RECORD.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise RuntimeFailure("DOCKER_IMAGE_LOCK_INVALID") from exc
    if not isinstance(record, dict):
        raise RuntimeFailure("DOCKER_IMAGE_LOCK_INVALID")
    _validate_image(record, image_info())
    return record


def host_python() -> Path:
    candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    if not candidate.is_file():
        candidate = ROOT / ".venv" / "bin" / "python"
    if not candidate.is_file():
        raise RuntimeFailure("RUNNER_WORKTREE_VENV_MISSING")
    if not candidate.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeFailure("RUNNER_WORKTREE_VENV_INVALID")
    return candidate


def native_probe(python: Path) -> bool:
    probe = _run([str(python), "-c", "import duckdb, numpy, polars, pyarrow"])
    if probe.returncode == 0:
        return True
    if BLOCKED.search(probe.stderr):
        return False
    raise RuntimeFailure("RUNNER_NATIVE_PROBE_NONBLOCKED_ERROR:" + probe.stderr.strip()[:600])


def _script_path(relative: str) -> Path:
    # Only direct-child files are executable; Docker mounts precisely this directory.
    path = (ROOT / relative).resolve()
    allowed = (ROOT / "scripts" / "data").resolve()
    if path.parent != allowed or path.suffix != ".py" or not path.is_file():
        raise RuntimeFailure("RUNNER_SCRIPT_NOT_APPROVED")
    return path


def _mount(directory: Path, target: str, *, readonly: bool) -> str:
    if not readonly:
        resolved = _runtime_path(directory)
        if target not in {"/outputs", "/worktmp"}:
            raise RuntimeFailure("DOCKER_MOUNT_TARGET_NOT_APPROVED")
    else:
        resolved = directory.resolve(strict=True)
    path = str(resolved)
    if "," in path or "\n" in path:
        raise RuntimeFailure("DOCKER_MOUNT_PATH_INVALID")
    suffix = ",readonly" if readonly else ""
    return f"type=bind,source={path},target={target}{suffix}"


def _runtime_path(path: Path) -> Path:
    """Reject links/reparse points in the approved runtime tree before any host IO."""
    try:
        relative = path.relative_to(ROOT)
        if relative.parts[:3] != (".work", "runtime", "docker-data-platform"):
            raise ValueError("outside runtime")
    except ValueError as exc:
        raise RuntimeFailure("DOCKER_RUNTIME_PATH_UNSAFE") from exc
    current = ROOT
    for part in relative.parts:
        current = current / part
        try:
            attrs = current.lstat()
        except FileNotFoundError:
            continue
        if current.is_symlink() or (
            getattr(attrs, "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise RuntimeFailure("DOCKER_RUNTIME_PATH_UNSAFE")
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeFailure("DOCKER_RUNTIME_PATH_UNSAFE")
    return resolved


def _workspace_dirs() -> tuple[Path, Path]:
    output = RUNTIME / "outputs"
    temporary = RUNTIME / "tmp"
    for directory in (output, temporary):
        _runtime_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        _runtime_path(directory)
        check = directory / ".write-probe"
        try:
            check.write_text("ok", encoding="utf-8", newline="\n")
            check.unlink()
        except OSError as exc:
            raise RuntimeFailure(f"DOCKER_OUTPUT_NOT_WRITABLE:{directory.name}") from exc
    return output, temporary


def _host_run(script: Path, args: list[str]) -> int:
    command = [str(host_python()), str(script), *args]
    result = _run(command, cwd=ROOT)
    if result.returncode:
        if BLOCKED.search(result.stderr):
            raise RuntimeFailure("RUNNER_NATIVE_BINARY_BLOCKED")
        raise RuntimeFailure("RUNNER_HOST_SCRIPT_FAILED:" + result.stderr.strip()[:600])
    print(result.stdout.strip())
    return 0


def _container_user() -> str:
    # Match the invoking Linux user's ownership for writable bind mounts.
    # Docker Desktop on Windows has no POSIX uid/gid; use unprivileged fallback.
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        uid, gid = os.getuid(), os.getgid()
        if uid > 0 and gid > 0:
            return f"{uid}:{gid}"
    return "65532:65532"


def docker_command(script: Path, args: list[str], *, image_id: str,
                   input_dir: Path | None = None) -> list[str]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeFailure("DOCKER_IMAGE_DIGEST_MISMATCH")
    output, temporary = _workspace_dirs()
    if script.parent != (ROOT / "scripts" / "data").resolve() or script.suffix != ".py" or not script.is_file():
        raise RuntimeFailure("DOCKER_SCRIPT_NOT_APPROVED")
    commands = [
        "docker", "run", "--rm", "--pull", "never",
        "--platform", "linux/amd64", "--network", "none",
        "--cpus", "2", "--memory", "2g", "--memory-swap", "2g",
        "--pids-limit", "128", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--user", _container_user(),
        "--env", "PYTHONPATH=/workspace/src",
        "--env", "COMMODITY_RUNTIME_TMP=/worktmp",
        "--env", "TMPDIR=/worktmp", "--env", "TMP=/worktmp",
        "--env", "HOME=/worktmp", "--env", "XDG_CACHE_HOME=/worktmp",
        "--env", "PYTHONNOUSERSITE=1",
        "--mount", _mount(ROOT / "scripts" / "data", "/workspace/scripts/data", readonly=True),
        "--mount", _mount(ROOT / "src", "/workspace/src", readonly=True),
        "--mount", _mount(ROOT / "config", "/workspace/config", readonly=True),
        "--mount", _mount(output, "/outputs", readonly=False),
        "--mount", _mount(temporary, "/worktmp", readonly=False),
    ]
    if input_dir is not None:
        approved = _runtime_path(RUNTIME / "inputs")
        try:
            resolved = input_dir.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeFailure("DOCKER_INPUT_MISSING") from exc
        if not input_dir.is_relative_to(RUNTIME / "inputs"):
            raise RuntimeFailure("DOCKER_INPUT_NOT_APPROVED")
        _runtime_path(input_dir)
        if not resolved.is_relative_to(approved) or not resolved.is_dir():
            raise RuntimeFailure("DOCKER_INPUT_NOT_APPROVED")
        commands += ["--mount", _mount(resolved, "/input", readonly=True)]
    commands += [image_id, "python", f"/workspace/scripts/data/{script.name}", *args]
    return commands


def execute(mode: str, script_name: str, rows: int, *, input_dir: Path | None = None, script_args: list[str] | None = None) -> int:
    script = _script_path(script_name)
    benchmark_script = script == _script_path(SCRIPT)
    if benchmark_script and rows < 100_000:
        raise RuntimeFailure("RUNNER_BENCHMARK_ROWS_TOO_SMALL")
    output, _ = _workspace_dirs()
    if benchmark_script:
        if mode == "docker":
            args = ["--rows", str(rows), "--output", "/outputs/benchmark.json"]
        else:
            args = ["--rows", str(rows), "--output", str(output / "benchmark.json")]
    else:
        args = list(script_args or [])
    if mode == "auto":
        available = native_probe(host_python())
        if available:
            try:
                return _host_run(script, args)
            except RuntimeFailure as exc:
                if str(exc) != "RUNNER_NATIVE_BINARY_BLOCKED":
                    raise
        mode = "docker"
    elif mode == "host":
        if not native_probe(host_python()):
            raise RuntimeFailure("RUNNER_NATIVE_BINARY_BLOCKED")
        return _host_run(script, args)
    elif mode != "docker":
        raise RuntimeFailure("RUNNER_MODE_UNKNOWN")
    image_id = str(verify_image().get("image_id", ""))
    docker_args = (["--rows", str(rows), "--output", "/outputs/benchmark.json"]
                   if benchmark_script else list(script_args or []))
    result = _run(docker_command(script, docker_args, image_id=image_id, input_dir=input_dir))
    if result.returncode:
        raise RuntimeFailure(
            f"DOCKER_EXECUTION_FAILED:exit={result.returncode}:{result.stderr.strip()[:600]}"
        )
    print(result.stdout.strip())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["auto", "host", "docker"], default="auto")
    parser.add_argument("--build-image", action="store_true")
    parser.add_argument("--script", default=SCRIPT)
    parser.add_argument("--rows", type=int, default=1_500_000)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--arg", dest="script_args", action="append", default=[])
    options = parser.parse_args(argv)
    try:
        if options.build_image:
            print(json.dumps(build_image(), sort_keys=True))
            return 0
        return execute(options.mode, options.script, options.rows, input_dir=options.input_dir,
                       script_args=options.script_args)
    except RuntimeFailure as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
