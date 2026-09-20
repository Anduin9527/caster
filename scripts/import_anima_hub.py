"""Fetch a pinned Hub catalog or read a local snapshot; never runs Hub code."""
from _config import API_URL, COMFY_URL, DATA_DIR
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from aigc.templates import HUB_REVISION, HUB_REPO, hub_bundle, parse_clothing_js, import_bundle
from aigc.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Directory containing js/ from the pinned Hub revision')
    parser.add_argument('--output', type=Path, default=DATA_DIR/'anima-hub.templates.json')
    parser.add_argument('--data-dir', type=Path, help='Optionally import into this local CASTER data directory')
    args = parser.parse_args()
    pinned = json.loads((Path(__file__).resolve().parents[1]/'integrations/anima-hub.json').read_text())
    files = {}
    for name in ('character_official_data.json', 'clothing_data.js'):
        if args.source_dir:
            raw = (args.source_dir/'js'/name).read_bytes()
        else:
            url = f'https://raw.githubusercontent.com/j955229/Comfyui-Anima-Tools-HUB/{HUB_REVISION}/js/{name}'
            with httpx.Client(timeout=60) as client:
                response = client.get(url)
                response.raise_for_status()
                raw = response.content
        if len(raw) > 16*1024*1024:
            raise ValueError('Source file exceeds 16 MiB')
        if hashlib.sha256(raw).hexdigest() != pinned['sha256'][name]:
            raise ValueError('Source SHA256 does not match the pinned Hub revision: '+name)
        files[name] = raw
    bundle = hub_bundle(json.loads(files['character_official_data.json']),
                        parse_clothing_js(files['clothing_data.js'].decode('utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(bundle.model_dump_json(indent=2), encoding='utf-8')
    manifest = {'repository': HUB_REPO, 'revision': HUB_REVISION,
                'source_mode': 'local-files' if args.source_dir else 'pinned-download',
                'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                'counts': {kind: sum(t.kind == kind for t in bundle.templates) for kind in ('character', 'outfit')}}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))
    if args.data_dir:
        print(json.dumps(import_bundle(Store(args.data_dir), bundle)))

if __name__ == '__main__':
    main()
