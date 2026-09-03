import json
from pathlib import Path


def test_config_resolution_falls_back_to_installed_data(monkeypatch, tmp_path) -> None:
    from commodity import config

    installed = tmp_path / "share" / "commodity-research" / "config"
    installed.mkdir(parents=True)
    (installed / "models.json").write_text(
        json.dumps({"models": {"installed": {"enabled": True}}}), encoding="utf-8"
    )
    monkeypatch.delenv("COMMODITY_CONFIG_DIR", raising=False)
    monkeypatch.setattr(config, "SOURCE_CONFIG_DIR", tmp_path / "missing")
    monkeypatch.setattr(config, "INSTALLED_CONFIG_DIR", installed)
    loaded = config.load_json("models.json")
    assert loaded["models"]["installed"]["enabled"] is True


def test_config_resolution_honors_explicit_override(monkeypatch, tmp_path) -> None:
    from commodity import config

    override = tmp_path / "config"
    override.mkdir()
    (override / "models.json").write_text(
        json.dumps({"models": {"override": {"enabled": True}}}), encoding="utf-8"
    )
    monkeypatch.setenv("COMMODITY_CONFIG_DIR", str(override))
    loaded = config.load_json("models.json")
    assert loaded["models"]["override"]["enabled"] is True
    assert config.config_path("models.json") == override / "models.json"


def test_kronos_base_checkpoint_is_pinned_but_empirically_disabled() -> None:
    root = Path(__file__).resolve().parents[2]
    models = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    cfg = models["models"]["kronos_base"]

    assert cfg["enabled"] is False
    assert cfg["checkpoint_preflight_enabled"] is True
    assert cfg["model_id"] == "NeoQuasar/Kronos-base"
    assert cfg["model_revision"] == "2b554741eca47781b64468546e77fef3e85130e6"
    assert cfg["tokenizer_id"] == "NeoQuasar/Kronos-Tokenizer-base"
    assert cfg["tokenizer_revision"] == "0e0117387f39004a9016484a186a908917e22426"
    assert cfg["checkpoint_artifacts"]["model"]["sha256"] == (
        "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83"
    )
    assert cfg["checkpoint_artifacts"]["tokenizer"]["sha256"] == (
        "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee"
    )


def test_kronos_small_checkpoint_is_pinned_but_empirically_disabled() -> None:
    root = Path(__file__).resolve().parents[2]
    models = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    cfg = models["models"]["kronos_small"]

    assert cfg["enabled"] is False
    assert cfg["checkpoint_preflight_enabled"] is True
    assert cfg["model_id"] == "NeoQuasar/Kronos-small"
    assert cfg["model_revision"] == "901c26c1332695a2a8f243eb2f37243a37bea320"
    assert cfg["tokenizer_id"] == "NeoQuasar/Kronos-Tokenizer-base"
    assert cfg["checkpoint_artifacts"]["model"]["sha256"] == (
        "b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020"
    )


def test_kronos_confirmation_profile_freezes_paper_and_repository_roles() -> None:
    root = Path(__file__).resolve().parents[2]
    models = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    profile = models["kronos_confirmation_profile"]

    assert profile["paper_backtest_inference"] == {
        "T": 0.6,
        "top_p": 0.9,
        "sample_count": 5,
        "source": "vendor/Kronos/finetune/config.py",
    }
    assert profile["repository_diagnostic"]["horizon_trading_sessions"] == 1
    assert profile["empirical_execution_authorized"] is False
