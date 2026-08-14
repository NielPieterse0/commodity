import json


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
