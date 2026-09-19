"""Local cache for known upstream template previews; never fetch arbitrary user URLs."""
import hashlib
import io
import json
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageOps
from .templates import HUB_REPO, HUB_REVISION


@lru_cache(maxsize=1)
def outfit_urls():
    return json.loads((Path(__file__).resolve().parents[1] / 'integrations/anima-outfit-previews.json').read_text())


def source_url(template):
    if template.get('source') != HUB_REPO or template.get('source_revision') != HUB_REVISION:
        return None
    key = template.get('source_key', '')
    if not key:
        return None
    if template['kind'] == 'character':
        parts = key.split('||')
        name = ', '.join(parts[:2]) if len(parts) > 1 and parts[1] else parts[0]
        return 'https://blobs.animadex.net/Outputs/thumbs/' + quote(name, safe="~!*'()-._") + '.webp'
    return outfit_urls().get(key)


def cache_path(store, template):
    url = source_url(template)
    if not url:
        return None
    return store.root / 'template-previews' / (hashlib.sha256(url.encode()).hexdigest() + '.webp')


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.preview-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def fetch_preview(store, template, client):
    path = cache_path(store, template)
    if path is None:
        return {'id': template['id'], 'status': 'unsupported'}
    if path.is_file():
        return {'id': template['id'], 'status': 'cached', 'bytes': path.stat().st_size}
    url = source_url(template)
    # Client redirects are disabled: the fixed upstream host is the fetch boundary.
    with client.stream('GET', url) as response:
        response.raise_for_status()
        if not response.headers.get('content-type', '').startswith('image/'):
            raise ValueError('Upstream returned non-image content')
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('Preview exceeds 8 MiB')
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 32_000_000:
            raise ValueError('Preview canvas too large')
        image = ImageOps.exif_transpose(image).convert('RGBA')
        image.thumbnail((384, 384), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='WEBP', quality=85)
    blob = output.getvalue()
    meta = {'source_url': url, 'source_revision': HUB_REVISION, 'fetched_at': time.time(),
            'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
    atomic_write(path.with_suffix('.json'), json.dumps(meta).encode())
    atomic_write(path, blob)
    return {'id': template['id'], 'status': 'downloaded', 'bytes': len(blob)}
