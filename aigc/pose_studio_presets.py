"""Pinned Pose Studio presets with locally cached official WebGL renders."""
import hashlib
import io
import json
import time
from pathlib import Path
from PIL import Image
from .workbench import Transaction

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / 'integrations/pose-studio-library.json').read_text())
ITEMS = {p['id']: p for p in MANIFEST['poses']}

def preset(index):
    try: return ITEMS[index]
    except KeyError: raise LookupError('Unknown Pose Studio preset')

def verified_file(store, relative, expected):
    file = store.root / 'pose-studio-library' / relative
    if not file.is_file(): raise LookupError('Pose Studio cache is not ready')
    blob = file.read_bytes()
    if hashlib.sha256(blob).hexdigest() != expected:
        raise LookupError('Pose Studio cache checksum mismatch')
    return blob

def render_info(item, width=None, height=None):
    if width is None and height is None:
        return f"renders/{item['id']}.png", item['render_sha256']
    if width is None or height is None or not (64<=width<=4096 and 64<=height<=4096):
        raise ValueError('Invalid pose canvas')
    from .canvas import SIZES
    key=f'{width}x{height}'
    if key not in SIZES:
        # Historical source canvases retain their own dimensions in the encoder.
        key=min(SIZES,key=lambda k:abs(SIZES[k][0]/SIZES[k][1]-width/height))
    digest=item.get('native_renders',{}).get(key)
    if not digest:raise LookupError('Native pose render cache is not ready')
    return f"renders/{item['id']}-{key}.png",digest

def render(store, index, width=None, height=None):
    relative,digest=render_info(preset(index),width,height)
    return verified_file(store, relative, digest)

def catalog():
    return [dict(id=p['id'],name=p['display_name'],original_name=p['name'],
                 source=MANIFEST['source'],revision=MANIFEST['revision'],format='pose_studio_3d',
                 preview_url=f"/production/pose-presets/{p['id']}/image?width=1024&height=1536&v={p.get('native_renders',{}).get('1024x1536',p['render_sha256'])}")
            for p in MANIFEST['poses']]

def materialize(store,index,width=None,height=None):
    item=preset(index)
    state=json.loads(verified_file(store,item['json_path'],item['json_sha256']))
    blob=render(store,index,width,height)
    image=Image.open(io.BytesIO(blob)); image.load()
    digest=hashlib.sha256(blob).hexdigest()
    asset_id=hashlib.sha256(('pose-studio-render:'+digest).encode()).hexdigest()[:32]
    pose_id=hashlib.sha256((MANIFEST['revision']+':'+str(index)+':'+digest).encode()).hexdigest()[:32]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');tx=Transaction(db)
        existing=tx.get('pose',pose_id,False)
        if existing:return existing
        if not tx.get('asset',asset_id,False):
            path=store.root/'files'/(asset_id+'.png')
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Pose render path contains different content')
            else:
                with path.open('xb') as f:f.write(blob)
            tx.put('asset',asset_id,dict(role='pose_render',path=path.name,width=image.width,height=image.height,
                mode=image.mode,sha256=digest,created=time.time(),source=MANIFEST['source']))
        value=dict(render_asset_id=asset_id,preset_id=index,name=item['display_name'],
            lighting_prompt='Preserve lighting from the character reference.',
            state={'format':'pose_studio_3d','source':MANIFEST['source'],'revision':MANIFEST['revision'],
                   'pose':state,'render_sha256':digest,'renderer':MANIFEST['renderer'],'canvas':[image.width,image.height],'native_render':width is not None})
        tx.put('pose',pose_id,value)
        return dict(value,id=pose_id)
