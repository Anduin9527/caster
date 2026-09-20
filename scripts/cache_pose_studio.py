"""Download pinned Pose Studio states/previews under the project data directory.

Run through the existing proxychains configuration on the deployment host.
"""
from _config import API_URL, COMFY_URL, DATA_DIR
import concurrent.futures
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'integrations/pose-studio-library.json').read_text())

def fetch(item):
    for kind in ('json', 'preview'):
        relative = item[kind + '_path']
        path = DATA_DIR / 'pose-studio-library' / relative
        expected = item[kind + '_sha256']
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            continue
        url = MANIFEST['source'] + '/resolve/' + MANIFEST['revision'] + '/' + quote(relative)
        with urlopen(url, timeout=45) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Invalid downloaded asset: ' + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.part')
        temporary.write_bytes(data)
        temporary.replace(path)
    return item['name']

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(fetch, MANIFEST['poses']):
            print(name, flush=True)
