"""Deterministic 2D guidance images. These are not Pose Studio 3D states."""
import hashlib
import io
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
from .workbench import Transaction

DATA = json.loads((Path(__file__).resolve().parents[1] / 'integrations/vnccs-poses.json').read_text())
EDGES = [('nose','neck'),('neck','r_shoulder'),('neck','l_shoulder'),('r_shoulder','r_elbow'),('r_elbow','r_wrist'),('l_shoulder','l_elbow'),('l_elbow','l_wrist'),('neck','r_hip'),('neck','l_hip'),('r_hip','l_hip'),('r_hip','r_knee'),('r_knee','r_ankle'),('l_hip','l_knee'),('l_knee','l_ankle'),('nose','r_eye'),('nose','l_eye'),('r_eye','r_ear'),('l_eye','l_ear')]


def preset(index):
    if not 1 <= index <= len(DATA['poses']): raise LookupError('Unknown pose preset')
    return DATA['poses'][index-1]


def render(index):
    points = preset(index)
    im = Image.new('RGB', (DATA['canvas']['width'], DATA['canvas']['height']), 'white')
    draw = ImageDraw.Draw(im)
    for a,b in EDGES:
        draw.line([tuple(points[a]),tuple(points[b])],fill=(28,151,138) if a.startswith('r_') else (44,44,44),width=10)
    for x,y in points.values(): draw.ellipse((x-6,y-6,x+6,y+6),fill=(223,101,85))
    output=io.BytesIO();im.save(output,format='PNG');return output.getvalue()


def catalog():
    return [dict(id=i,name=f'预设 {i:02}',source=DATA['source'],revision=DATA['revision'],format='vnccs_2d',preview_url=f'/production/pose-presets/{i}/image') for i in range(1,len(DATA['poses'])+1)]


def materialize(store,index):
    points=preset(index); blob=render(index)
    digest=hashlib.sha256(blob).hexdigest()
    asset_id=hashlib.sha256(('vnccs-render:'+digest).encode()).hexdigest()[:32]
    pose_id=hashlib.sha256((DATA['revision']+':'+str(index)+':'+digest).encode()).hexdigest()[:32]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');tx=Transaction(db)
        existing=tx.get('pose',pose_id,False)
        if existing:return existing
        asset=tx.get('asset',asset_id,False)
        if not asset:
            path=store.root/'files'/(asset_id+'.png')
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Preset output path contains different content')
            else:
                with path.open('xb') as f:f.write(blob)
            tx.put('asset',asset_id,dict(role='pose_render',path=path.name,width=DATA['canvas']['width'],height=DATA['canvas']['height'],mode='RGB',sha256=digest,created=time.time(),source=DATA['source']))
        value=dict(render_asset_id=asset_id,preset_id=index,lighting_prompt='Preserve lighting from the character reference.',state={'format':'vnccs_2d','source':DATA['source'],'revision':DATA['revision'],'canvas':DATA['canvas'],'points':points})
        tx.put('pose',pose_id,value)
        return dict(value,id=pose_id)
