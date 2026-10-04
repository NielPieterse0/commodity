from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/research/run_issue465_block1_controller_v2.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("issue465_v2_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v2_prereg_is_frozen_before_scoring() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    assert prereg["status"] == "frozen_before_block1_controller_v2_scoring"
    assert prereg["block_contract"]["later_blocks_available"] is False
    assert prereg["freeze_rules"]["protected_2023_plus_remains_sealed"] is True


def test_v2_runner_keeps_v1_evidence_immutable() -> None:
    runner = _load_runner()
    prereg = runner.load_prereg()
    predecessor = prereg["predecessor_v1"]
    expected = {
        runner.V1_PREREG.name: predecessor["prereg_sha256"],
        runner.V1_STATE.name: predecessor["pit_state_sha256"],
        runner.V1_RESULT.name: predecessor["result_sha256"],
    }
    for name, expected_sha in expected.items():
        assert runner.sha256_file(runner.PROGRAMME / name) == expected_sha
