from aigc.config import load, ROOT


def test_config_literal_values_and_explicit_override(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    marker = tmp_path / 'should-not-exist'
    config.write_text(
        'AIGC_API_URL="http://127.0.0.1:9000" # local API\n'
        'AIGC_DATA_DIR="data/config test"\n'
        f'AIGC_LLM_API_KEY="$(touch {marker})"\n'
    )
    for key in ('AIGC_API_URL', 'AIGC_DATA_DIR', 'AIGC_LLM_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    values = load(config)
    assert values['AIGC_API_URL'] == 'http://127.0.0.1:9000'
    assert values['AIGC_DATA_DIR'] == str(ROOT / 'data/config test')
    assert not marker.exists()
    monkeypatch.setenv('AIGC_API_URL', 'http://127.0.0.1:9001')
    assert load(config)['AIGC_API_URL'] == 'http://127.0.0.1:9001'
