"""App-wide config (theme persistence) round-trip."""

from __future__ import annotations

import importlib


def test_app_config_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    app_config = importlib.import_module("owa_tui.app_config")

    assert app_config.load() == {}  # nothing saved yet
    app_config.save({"theme": "gruvbox"})
    assert app_config.load()["theme"] == "gruvbox"
    assert (tmp_path / "owa-tui" / "tui.json").exists()


def test_app_config_bad_file_returns_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    app_config = importlib.import_module("owa_tui.app_config")
    p = tmp_path / "owa-tui" / "tui.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json")
    assert app_config.load() == {}
