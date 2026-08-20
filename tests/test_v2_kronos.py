import hashlib
import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from commodity import kronos
from commodity import v2_kronos as v2_kronos_module
from commodity.v2_kronos import (
    CANDIDATE_ID,
    IMPLEMENTATION_SOURCE_PATHS,
    KRONOS_SOURCE_REVISION,
    EmpiricalReleaseBlocked,
    KronosContractError,
    adapter_frame,
    bind_activation_contract,
    build_input_manifest,
    build_longitudinal_handoff,
    build_pit_context,
    canonical_sha256,
    enforce_cost_caps,
    governed_return_prediction,
    require_empirical_release,
    seed_runtime,
    verify_replay,
)

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_BOUND_IMPLEMENTATION = "1" * 40
SYNTHETIC_RUNTIME_REVISION = "2" * 40


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def _source_manifest() -> dict:
    manifest = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "files": {path: hashlib.sha256(path.encode()).hexdigest() for path in IMPLEMENTATION_SOURCE_PATHS},
        "kronos_source_revision": KRONOS_SOURCE_REVISION,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def _candidate_registry() -> dict:
    candidates = _load("config/experiment_candidates.json")
    source_manifest = _source_manifest()
    candidates["candidates"]["v2-82-kronos-only"]["implementation_revision"] = {
        "pr": 100,
        "head": SYNTHETIC_BOUND_IMPLEMENTATION,
        "path": "src/commodity/v2_kronos.py",
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "source_manifest_paths": list(IMPLEMENTATION_SOURCE_PATHS),
        "kronos_source_revision": KRONOS_SOURCE_REVISION,
    }
    return candidates


def _activation_contract() -> dict:
    contract = _load("docs/development/v2-activation-preregistration/activation-contract.json")
    contract["frozen_execution_rules"]["kronos_target_interface"] = {
        "model_forecast_field": "close",
        "prediction_mapping": "log(predicted_close_next / observed_close_at_cutoff)",
        "prediction_role": "uncalibrated_close_return_proxy_for_target_ret_1",
        "actual_target": "selected_contract_settlement_log_return",
        "settlement_reconstruction_permitted": False,
        "calibration_permitted": False,
    }
    return contract


def _binding() -> dict:
    return bind_activation_contract(
        _activation_contract(),
        _candidate_registry(),
        _load("config/models.json")["models"]["kronos_mini"],
        _load("config/assumptions.json"),
    )


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-08-10T23:59:00Z", "2026-08-11T23:59:00Z"],
            "contract_id": ["NGU6", "NGU6"],
            "expiration": ["2026-08-27T00:00:00Z", "2026-08-27T00:00:00Z"],
            "available_at": ["2026-08-10T23:59:00Z", "2026-08-11T23:59:00Z"],
            "open": [3.0, 3.1],
            "high": [3.2, 3.3],
            "low": [2.9, 3.0],
            "close": [3.1, 3.2],
            "volume": [1000.0, 1100.0],
        }
    )


def test_source_hash_is_newline_invariant(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"first\nsecond\n")
    lf_digest = v2_kronos_module._sha256_file(source)
    source.write_bytes(b"first\r\nsecond\r\n")
    assert v2_kronos_module._sha256_file(source) == lf_digest


def test_binding_is_exact_but_blocked_during_independent_88_reaudit() -> None:
    binding = _binding()
    assert binding["candidate_id"] == "v2-82-kronos-only"
    assert binding["model_revision"] == "7fdcc628d87f325ccdbcae0a372622ca7e6813aa"
    assert binding["kronos_source_revision"] == KRONOS_SOURCE_REVISION
    assert binding["implementation_revision"]["head"] == SYNTHETIC_BOUND_IMPLEMENTATION
    assert binding["target_interface"]["prediction_role"] == "uncalibrated_close_return_proxy_for_target_ret_1"
    with pytest.raises(EmpiricalReleaseBlocked):
        require_empirical_release(binding)


def test_binding_requires_explicit_close_proxy_target_interface() -> None:
    contract = _activation_contract()
    contract["frozen_execution_rules"].pop("kronos_target_interface")
    with pytest.raises(KronosContractError, match="target interface"):
        bind_activation_contract(
            contract,
            _candidate_registry(),
            _load("config/models.json")["models"]["kronos_mini"],
            _load("config/assumptions.json"),
        )


def test_binding_still_fails_closed_without_88_release() -> None:
    binding = _binding()
    binding["activation_execution_authorized"] = False
    gate = binding["empirical_release_gate"]
    gate["88"]["satisfied"] = False
    gate["88"]["current_state"] = "not_executed"
    gate["release_state"]["82"] = False
    binding["binding_sha256"] = canonical_sha256(
        {key: value for key, value in binding.items() if key != "binding_sha256"}
    )
    with pytest.raises(EmpiricalReleaseBlocked):
        require_empirical_release(binding)


def test_binding_requires_separate_exact_implementation_revision() -> None:
    candidates = _load("config/experiment_candidates.json")
    candidates["candidates"]["v2-82-kronos-only"].pop("implementation_revision", None)
    with pytest.raises(KronosContractError, match="implementation revision"):
        bind_activation_contract(
            _load("docs/development/v2-activation-preregistration/activation-contract.json"),
            candidates,
            _load("config/models.json")["models"]["kronos_mini"],
            _load("config/assumptions.json"),
        )


def test_longitudinal_handoff_allows_integrated_revision_only_with_identical_sources() -> None:
    binding = _binding()
    source_manifest = _source_manifest()
    handoff = build_longitudinal_handoff(
        binding,
        runtime_code_revision=SYNTHETIC_RUNTIME_REVISION,
        runtime_source_manifest=source_manifest,
        config_sha256="a" * 64,
        artifact_sha256s=["b" * 64],
    )
    assert handoff["bound_implementation_revision"] == SYNTHETIC_BOUND_IMPLEMENTATION
    assert handoff["runtime_code_revision"] == SYNTHETIC_RUNTIME_REVISION
    assert handoff["implementation_source_manifest_sha256"] == source_manifest["manifest_sha256"]
    assert handoff["activation_binding_sha256"] == binding["binding_sha256"]

    mutated = json.loads(json.dumps(source_manifest))
    mutated["files"][IMPLEMENTATION_SOURCE_PATHS[0]] = "f" * 64
    mutated["manifest_sha256"] = canonical_sha256({
        key: value for key, value in mutated.items() if key != "manifest_sha256"
    })
    with pytest.raises(KronosContractError, match="sources differ"):
        build_longitudinal_handoff(
            binding,
            runtime_code_revision=SYNTHETIC_RUNTIME_REVISION,
            runtime_source_manifest=mutated,
            config_sha256="a" * 64,
            artifact_sha256s=["b" * 64],
        )


def test_pit_context_preserves_trace_and_adapter_boundary() -> None:
    context = build_pit_context(_market(), "2026-08-11T23:59:00Z")
    assert list(context["contract_id"]) == ["NGU6", "NGU6"]
    adapted = adapter_frame(context)
    assert list(adapted.columns) == ["open", "high", "low", "close", "volume"]
    assert adapted.index.is_monotonic_increasing
    manifest = build_input_manifest(context, "2026-08-11T23:59:00Z")
    assert manifest["row_count"] == 2
    assert len(manifest["context_sha256"]) == 64


def test_pit_context_rejects_missing_or_invalid_selected_data() -> None:
    frame = _market()
    frame.loc[1, "high"] = 2.0
    with pytest.raises(KronosContractError, match="OHLC ordering"):
        build_pit_context(frame, "2026-08-11T23:59:00Z")

    frame = _market()
    frame.loc[1, "close"] = float("nan")
    with pytest.raises(KronosContractError, match="non-finite"):
        build_pit_context(frame, "2026-08-11T23:59:00Z")


def test_pit_context_rejects_ambiguous_time_and_order() -> None:
    with pytest.raises(KronosContractError, match="timezone-aware"):
        build_pit_context(_market(), "2026-08-11 23:59:00")
    reversed_frame = _market().iloc[::-1].reset_index(drop=True)
    with pytest.raises(KronosContractError, match="strictly chronological"):
        build_pit_context(reversed_frame, "2026-08-11T23:59:00Z")


def test_pit_context_rejects_future_trade_date_even_if_marked_available() -> None:
    frame = _market()
    frame.loc[1, "trade_date"] = "2026-08-12T23:59:00Z"
    frame.loc[1, "available_at"] = "2026-08-11T22:00:00Z"

    with pytest.raises(KronosContractError, match="trade_date after the prediction cutoff"):
        build_pit_context(frame, "2026-08-11T23:59:00Z")


def test_target_mapping_fails_closed_on_roll_transition() -> None:
    value = governed_return_prediction(
        predicted_close_next=3.3,
        observed_close_at_cutoff=3.2,
        current_contract_id="NGU6",
        target_contract_id="NGU6",
    )
    assert value > 0
    with pytest.raises(KronosContractError, match="cross-contract"):
        governed_return_prediction(
            predicted_close_next=3.3,
            observed_close_at_cutoff=3.2,
            current_contract_id="NGU6",
            target_contract_id="NGV6",
        )


def test_replay_and_cost_caps_fail_closed() -> None:
    verify_replay("a" * 64, "a" * 64)
    with pytest.raises(KronosContractError, match="replay"):
        verify_replay("a" * 64, "b" * 64)
    enforce_cost_caps(
        elapsed_hours=1.0,
        paid_compute_usd=0.0,
        new_data_acquisition_usd=0.0,
        max_wall_clock_hours=12.0,
    )
    with pytest.raises(KronosContractError, match="paid compute"):
        enforce_cost_caps(
            elapsed_hours=1.0,
            paid_compute_usd=0.01,
            new_data_acquisition_usd=0.0,
            max_wall_clock_hours=12.0,
        )


def test_seed_runtime_sets_cpu_seed_and_rejects_cuda() -> None:
    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _Torch:
        cuda = _Cuda()
        seed = None

        @classmethod
        def manual_seed(cls, value: int) -> None:
            cls.seed = value

    seed_runtime(_Torch)
    assert _Torch.seed == 0

    class _CudaAvailable:
        @staticmethod
        def is_available() -> bool:
            return True

    _Torch.cuda = _CudaAvailable()
    with pytest.raises(KronosContractError, match="CUDA"):
        seed_runtime(_Torch)


def test_checkpoint_preflight_is_local_only_and_hash_verified(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    snapshot = tmp_path / "snapshot"
    cache.mkdir()
    snapshot.mkdir()
    artifact = snapshot / "model.safetensors"
    artifact.write_bytes(b"frozen-checkpoint")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    fake_hf = types.ModuleType("huggingface_hub")

    def snapshot_download(**kwargs):
        assert kwargs["local_files_only"] is True
        assert kwargs["revision"] == "model-revision"
        assert Path(kwargs["cache_dir"]) == cache
        return str(snapshot)

    fake_hf.snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)
    monkeypatch.setenv("TEST_KRONOS_CACHE", str(cache))
    cfg = {
        "local_files_only": True,
        "checkpoint_cache_env": "TEST_KRONOS_CACHE",
        "model_id": "model-id",
        "model_revision": "model-revision",
        "tokenizer_id": "tokenizer-id",
        "tokenizer_revision": "tokenizer-revision",
        "checkpoint_artifacts": {
            "model": {"filename": "model.safetensors", "sha256": digest},
            "tokenizer": {"filename": "model.safetensors", "sha256": digest},
        },
    }
    resolved = kronos._resolve_pinned_snapshot(cfg, "model")
    assert resolved["artifact_sha256"] == digest

    cfg["checkpoint_artifacts"]["model"]["sha256"] = "0" * 64
    with pytest.raises(kronos.KronosArtifactError, match="hash mismatch"):
        kronos._resolve_pinned_snapshot(cfg, "model")
