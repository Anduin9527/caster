"""Shared runtime defaults and local config.env loading (no shell execution)."""
import json
import os
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]


def load(path=None):
    values = {
        'AIGC_API_URL': 'http://127.0.0.1:8189',
        'AIGC_COMFY_URL': 'http://127.0.0.1:8188',
        'AIGC_UI_URL': 'http://127.0.0.1:4173',
        'AIGC_DATA_DIR': str(ROOT / 'data'),
    }
    source = Path(path) if path is not None else ROOT / 'config.env'
    if source.exists():
        for line in source.read_text().splitlines():
            tokens = shlex.split(line, comments=True)
            if not tokens:
                continue
            if tokens[0] == 'export':
                tokens = tokens[1:]
            key, sep, value = ' '.join(tokens).partition('=')
            if not sep or not key.startswith('AIGC_'):
                raise ValueError('config.env expects AIGC_NAME=value assignments')
            values[key] = value
    # Explicit process overrides support isolated tests and deployed services.
    values.update({k: v for k, v in os.environ.items() if k.startswith('AIGC_')})
    data = Path(values['AIGC_DATA_DIR']).expanduser()
    values['AIGC_DATA_DIR'] = str(data if data.is_absolute() else ROOT / data)
    return values


if __name__ == '__main__':
    config = load()
    print(json.dumps({k: config[k] for k in ('AIGC_API_URL', 'AIGC_UI_URL')}))
