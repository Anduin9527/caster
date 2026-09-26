import pytest

from aigc.config import ROOT, flag, load


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE"])
def test_explicit_false_overrides_true_default(value):
    assert flag({"AIGC_FLAG": value}, "AIGC_FLAG", default=True) is False


def test_missing_flag_uses_default_and_invalid_flag_is_rejected():
    assert flag({}, "AIGC_FLAG", default=True) is True
    assert flag({}, "AIGC_FLAG") is False
    with pytest.raises(ValueError, match="AIGC_FLAG"):
        flag({"AIGC_FLAG": "perhaps"}, "AIGC_FLAG")


def test_config_file_can_be_selected_without_loading_developer_settings(tmp_path, monkeypatch):
    config = tmp_path / "isolated.env"
    config.write_text("AIGC_UI_URL=http://127.0.0.1:4999\n")
    monkeypatch.setenv("AIGC_CONFIG_FILE", str(config))
    assert load()["AIGC_UI_URL"] == "http://127.0.0.1:4999"
    assert load()["AIGC_RAG_DEVICE"] == "cpu"


def test_config_literal_values_and_explicit_override(tmp_path, monkeypatch):
    config = tmp_path / "config.env"
    marker = tmp_path / "should-not-exist"
    config.write_text(
        'AIGC_API_URL="http://127.0.0.1:9000" # local API\n'
        'AIGC_DATA_DIR="data/config test"\n'
        f'AIGC_LLM_API_KEY="$(touch {marker})"\n'
    )
    for key in ("AIGC_API_URL", "AIGC_DATA_DIR", "AIGC_LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    values = load(config)
    assert values["AIGC_API_URL"] == "http://127.0.0.1:9000"
    assert values["AIGC_DATA_DIR"] == str(ROOT / "data/config test")
    assert not marker.exists()
    monkeypatch.setenv("AIGC_API_URL", "http://127.0.0.1:9001")
    assert load(config)["AIGC_API_URL"] == "http://127.0.0.1:9001"
