"""Fail-closed operational contract tests; no Docker daemon or real market data."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/environment/docker_data_runtime.py"
spec = importlib.util.spec_from_file_location("commodity_docker_data_runtime", SCRIPT)
assert spec and spec.loader
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)
TEST_IMAGE_ID = "sha256:" + "f" * 64


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch):
    root = tmp_path / "commodity" / ".work" / "worktrees" / "test"
    for folder in ("scripts/data", "src", "config", "docker/data-platform"):
        (root / folder).mkdir(parents=True)
    (root / "scripts/data/benchmark_data_platform.py").write_text("pass\n", encoding="utf-8")
    (root / "docker/data-platform/Dockerfile").write_text(
        "FROM python:3.11.17-slim-bookworm@" + runtime.BASE_DIGEST + "\n", encoding="utf-8"
    )
    (root / "docker/data-platform/requirements.txt").write_text(
        "duckdb==1.5.6\n", encoding="utf-8"
    )
    monkeypatch.setattr(runtime, "ROOT", root)
    monkeypatch.setattr(runtime, "CONTEXT", root / "docker/data-platform")
    monkeypatch.setattr(runtime, "DOCKERFILE", root / "docker/data-platform/Dockerfile")
    monkeypatch.setattr(runtime, "LOCKFILE", root / "docker/data-platform/requirements.txt")
    monkeypatch.setattr(runtime, "RUNTIME", root / ".work/runtime/docker-data-platform")
    monkeypatch.setattr(runtime, "IMAGE_RECORD", runtime.RUNTIME / "image-lock.json")
    return root


def completed(code=0, out="", err=""):
    return subprocess.CompletedProcess(["fake"], code, stdout=out, stderr=err)


def directory_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise


def test_docker_invocation_is_isolated_and_never_mounts_checkout_root(isolated):
    script = runtime._script_path(runtime.SCRIPT)
    command = runtime.docker_command(script, ["--rows", "1500000"], image_id=TEST_IMAGE_ID)
    rendered = " ".join(command)
    for arg in ("--network none", "--cpus 2", "--memory 2g", "--pids-limit 128",
                "--read-only", "--cap-drop ALL", "--user " + runtime._container_user(),
                "no-new-privileges:true", "--pull never", "--rm"):
        assert arg in rendered
    assert "target=/workspace/scripts/data,readonly" in rendered
    assert "target=/workspace/src,readonly" in rendered
    assert "target=/workspace/config,readonly" in rendered
    assert "target=/outputs" in rendered
    assert "target=/worktmp" in rendered
    assert "target=/workspace,readonly" not in rendered
    assert ".env" not in rendered
    assert "--privileged" not in command
    assert "/var/run/docker.sock" not in rendered


def test_script_path_rejects_traversal_and_other_modules(isolated):
    with pytest.raises(runtime.RuntimeFailure, match="RUNNER_SCRIPT_NOT_APPROVED"):
        runtime._script_path("../../.env")
    with pytest.raises(runtime.RuntimeFailure, match="RUNNER_SCRIPT_NOT_APPROVED"):
        runtime._script_path("src/commodity/data_platform.py")


def test_native_blocked_error_triggers_fallback_only_for_policy(monkeypatch):
    monkeypatch.setattr(runtime, "_run", lambda *a, **kw: completed(1, err="WinError 577"))
    assert runtime.native_probe(Path("python.exe")) is False
    monkeypatch.setattr(runtime, "_run", lambda *a, **kw: completed(1, err="ModuleNotFoundError: foo"))
    with pytest.raises(runtime.RuntimeFailure, match="NONBLOCKED"):
        runtime.native_probe(Path("python.exe"))


def test_host_preferred_when_native_probe_succeeds(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "host_python", lambda: Path("python.exe"))
    monkeypatch.setattr(runtime, "native_probe", lambda _p: True)
    monkeypatch.setattr(runtime, "_host_run", lambda *_args: 0)
    monkeypatch.setattr(runtime, "verify_image", lambda: pytest.fail("Docker must not run"))
    assert runtime.execute("auto", runtime.SCRIPT, 100000) == 0


def test_blocked_native_falls_back_to_docker(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "host_python", lambda: Path("python.exe"))
    monkeypatch.setattr(runtime, "native_probe", lambda _p: False)
    monkeypatch.setattr(runtime, "verify_image", lambda: {"image_id": TEST_IMAGE_ID})
    called = []
    monkeypatch.setattr(runtime, "_run", lambda argv, **kwargs: called.append(argv) or completed())
    assert runtime.execute("auto", runtime.SCRIPT, 100000) == 0
    assert called and called[0][:2] == ["docker", "run"]


def test_forced_docker_skips_native_probe(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "native_probe", lambda _p: pytest.fail("probe unexpected"))
    monkeypatch.setattr(runtime, "verify_image", lambda: {"image_id": TEST_IMAGE_ID})
    monkeypatch.setattr(runtime, "_run", lambda *args, **kwargs: completed())
    assert runtime.execute("docker", runtime.SCRIPT, 100000) == 0


def test_docker_absent_is_explicit(monkeypatch):
    monkeypatch.setattr(runtime, "_run", lambda *a, **kw: completed(1, err="daemon unavailable"))
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_DAEMON_UNAVAILABLE"):
        runtime.docker_info()


def test_image_identity_and_lock_must_match(isolated):
    evidence = runtime.image_evidence()
    correct = {**evidence, "image_id": "sha256:expected"}
    image = {
        "Os": "linux", "Architecture": "amd64", "Id": "sha256:changed",
        "Config": {"Labels": {
            "org.commodity.lock-sha256": evidence["lock_sha256"],
            "org.commodity.dockerfile-sha256": evidence["dockerfile_sha256"],
        }},
    }
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_IMAGE_DIGEST_MISMATCH"):
        runtime._validate_image(correct, image)
    image["Id"] = "sha256:expected"
    runtime._validate_image(correct, image)
    correct["lock_sha256"] = "0" * 64
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_BUILD_INPUT_CHANGED"):
        runtime._validate_image(correct, image)


def test_image_bad_architecture_rejected(isolated):
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_IMAGE_ARCH_UNSUPPORTED"):
        runtime._validate_image({"image_id": "x"}, {
            "Os": "linux", "Architecture": "arm64", "Id": "x"
        })


def test_missing_input_and_external_input_fail_closed(isolated, tmp_path):
    script = runtime._script_path(runtime.SCRIPT)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_INPUT_MISSING"):
        runtime.docker_command(script, [], image_id=TEST_IMAGE_ID, input_dir=tmp_path / "missing")
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_INPUT_NOT_APPROVED"):
        runtime.docker_command(script, [], image_id=TEST_IMAGE_ID, input_dir=tmp_path)


def test_approved_staging_only_maps_readonly(isolated):
    approved = runtime.RUNTIME / "inputs" / "synthetic"
    approved.mkdir(parents=True)
    script = runtime._script_path(runtime.SCRIPT)
    command = runtime.docker_command(script, [], image_id=TEST_IMAGE_ID, input_dir=approved)
    assert "target=/input,readonly" in " ".join(command)


def test_non_native_host_failure_never_falls_back(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "host_python", lambda: Path("python.exe"))
    monkeypatch.setattr(runtime, "native_probe", lambda _p: True)
    monkeypatch.setattr(runtime, "_host_run",
                        lambda *args: (_ for _ in ()).throw(runtime.RuntimeFailure("BAD_DATA")))
    monkeypatch.setattr(runtime, "verify_image", lambda: pytest.fail("Docker not permitted"))
    with pytest.raises(runtime.RuntimeFailure, match="BAD_DATA"):
        runtime.execute("auto", runtime.SCRIPT, 100000)


def test_missing_host_venv_is_not_silent_docker_fallback(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "verify_image", lambda: pytest.fail("Docker not permitted"))
    with pytest.raises(runtime.RuntimeFailure, match="RUNNER_WORKTREE_VENV_MISSING"):
        runtime.execute("auto", runtime.SCRIPT, 100000)


def test_missing_outputs_reported(isolated, monkeypatch):
    original = Path.write_text

    def deny_probe(path, *args, **kwargs):
        if path.name == ".write-probe":
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", deny_probe)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_OUTPUT_NOT_WRITABLE"):
        runtime._workspace_dirs()


def test_no_small_nonrepresentative_benchmark(isolated):
    with pytest.raises(runtime.RuntimeFailure, match="ROWS_TOO_SMALL"):
        runtime.execute("docker", runtime.SCRIPT, 99_999)


def test_docker_resource_failure_is_not_retried_on_host(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "native_probe", lambda _p: pytest.fail("host probe forbidden"))
    monkeypatch.setattr(runtime, "verify_image", lambda: {"image_id": TEST_IMAGE_ID})
    monkeypatch.setattr(runtime, "_run", lambda *args, **kwargs: completed(137, err="killed"))
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_EXECUTION_FAILED:exit=137"):
        runtime.execute("docker", runtime.SCRIPT, 100000)


def test_docker_image_missing_actionable(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "_run", lambda *a, **kw: completed(1, err="no such image"))
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_IMAGE_MISSING_BUILD_FIRST"):
        runtime.image_info()


def test_image_lock_label_conflict_fail_closed(isolated):
    evidence = runtime.image_evidence()
    record = {**evidence, "image_id": "sha256:pinned"}
    image = {
        "Os": "linux", "Architecture": "amd64", "Id": "sha256:pinned",
        "Config": {"Labels": {"org.commodity.lock-sha256": "tampered",
                              "org.commodity.dockerfile-sha256": evidence["dockerfile_sha256"]}},
    }
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_LOCK_LABEL_MISMATCH"):
        runtime._validate_image(record, image)


def test_generic_data_route_preserves_exact_argument_vector(isolated, monkeypatch):
    job = isolated / "scripts/data/dbn_to_parquet.py"
    job.write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "verify_image", lambda: {"image_id": TEST_IMAGE_ID})
    seen = []
    monkeypatch.setattr(runtime, "_run",
                        lambda argv, **kwargs: seen.append(argv) or completed())
    args = ["--input=/input/source.dbn", "--output=/outputs/table.parquet", "a b"]
    assert runtime.execute("docker", "scripts/data/dbn_to_parquet.py", 1000,
                           script_args=args) == 0
    assert seen[0][-len(args):] == args
    assert "/workspace/scripts/data/dbn_to_parquet.py" in seen[0]


def test_runtime_rejects_external_writable_mount_symlink(isolated, tmp_path):
    external = tmp_path / "unrelated"
    external.mkdir()
    runtime.RUNTIME.mkdir(parents=True)
    directory_symlink(runtime.RUNTIME / "outputs", external)
    script = runtime._script_path(runtime.SCRIPT)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_RUNTIME_PATH_UNSAFE"):
        runtime.docker_command(script, [], image_id=TEST_IMAGE_ID)
    assert list(external.iterdir()) == []


def test_runtime_rejects_symlinked_runtime_parent(isolated, tmp_path):
    external = tmp_path / "outside"
    external.mkdir()
    (isolated / ".work").mkdir(exist_ok=True)
    directory_symlink(isolated / ".work/runtime", external)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_RUNTIME_PATH_UNSAFE"):
        runtime._workspace_dirs()


def test_mount_rejects_output_swapped_after_initial_validation(isolated, tmp_path):
    output, _ = runtime._workspace_dirs()
    output.rename(runtime.RUNTIME / "former-outputs")
    external = tmp_path / "external-output"
    external.mkdir()
    directory_symlink(output, external)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_RUNTIME_PATH_UNSAFE"):
        runtime._mount(output, "/outputs", readonly=False)
    assert list(external.iterdir()) == []


def test_runtime_rejects_symlinked_approved_input(isolated, tmp_path):
    outside = tmp_path / "external-input"
    outside.mkdir()
    (runtime.RUNTIME / "inputs").mkdir(parents=True)
    directory_symlink(runtime.RUNTIME / "inputs/escape", outside)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_RUNTIME_PATH_UNSAFE"):
        runtime.docker_command(runtime._script_path(runtime.SCRIPT), [], image_id=TEST_IMAGE_ID,
                               input_dir=runtime.RUNTIME / "inputs/escape")


def test_base_digest_must_be_effective_single_from(isolated, monkeypatch):
    dockerfile = runtime.DOCKERFILE
    dockerfile.write_text(
        "# python:3.11.17-slim-bookworm@" + runtime.BASE_DIGEST + "\n"
        "FROM python:3.11.17-slim-bookworm\n", encoding="utf-8"
    )
    monkeypatch.setattr(runtime, "docker_info", dict)
    monkeypatch.setattr(runtime, "_run",
                        lambda *a, **k: pytest.fail("Must reject before Docker build"))
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_BASE_DIGEST_MISMATCH"):
        runtime.build_image()
    dockerfile.write_text(
        "FROM python:3.11.17-slim-bookworm@" + runtime.BASE_DIGEST + "\n"
        "FROM alpine:latest\n", encoding="utf-8"
    )
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_BASE_DIGEST_MISMATCH"):
        runtime.build_image()


def test_nested_script_must_not_resolve_to_different_container_file(isolated):
    nested = isolated / "scripts/data/nested"
    nested.mkdir()
    (nested / "benchmark_data_platform.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(runtime.RuntimeFailure, match="RUNNER_SCRIPT_NOT_APPROVED"):
        runtime._script_path("scripts/data/nested/benchmark_data_platform.py")
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_SCRIPT_NOT_APPROVED"):
        runtime.docker_command((nested / "benchmark_data_platform.py").resolve(), [],
                               image_id=TEST_IMAGE_ID)


def test_benchmark_alias_cannot_bypass_minimum_rows(isolated):
    with pytest.raises(runtime.RuntimeFailure, match="RUNNER_BENCHMARK_ROWS_TOO_SMALL"):
        runtime.execute("docker", "scripts/data/./benchmark_data_platform.py", 99_999)


def test_docker_executes_verified_immutable_image_id(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "verify_image", lambda: {"image_id": TEST_IMAGE_ID})
    executed = []
    monkeypatch.setattr(runtime, "_run",
                        lambda argv, **kwargs: executed.append(argv) or completed())
    assert runtime.execute("docker", runtime.SCRIPT, 100_000) == 0
    assert TEST_IMAGE_ID in executed[0]
    assert runtime.IMAGE not in executed[0]


def test_docker_rejects_mutable_image_tag_argument(isolated):
    script = runtime._script_path(runtime.SCRIPT)
    with pytest.raises(runtime.RuntimeFailure, match="DOCKER_IMAGE_DIGEST_MISMATCH"):
        runtime.docker_command(script, [], image_id=runtime.IMAGE)
