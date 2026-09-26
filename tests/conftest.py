"""Offline tests never inherit a developer's data directory or model settings."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    for key in os.environ:
        if key.startswith("AIGC_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("AIGC_CONFIG_FILE", str(tmp_path / "config.env"))
    monkeypatch.setenv("AIGC_DATA_DIR", str(tmp_path / "runtime"))
