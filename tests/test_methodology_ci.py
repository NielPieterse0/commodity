import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_research_methodology.py"


def test_methodology_ci_script_has_all_four_gates() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for gate in ("experiment-schema", "experiment-freeze-integrity", "experiment-verification", "programme-inference-integrity"):
        assert gate in text


def test_legacy_authority_hash_is_line_ending_stable(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("check_research_methodology", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert module.sha256_file(lf) == module.sha256_file(crlf)


def test_methodology_schema_gate_passes_repository_authority() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "experiment-schema"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_runs_all_methodology_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for gate in ("experiment-schema", "experiment-freeze-integrity", "experiment-verification", "programme-inference-integrity"):
        assert gate in workflow
