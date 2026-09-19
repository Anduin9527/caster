"""Explicit operator mask correction for the reviewed B pose 3 hand occlusion.
Coordinates are sample-specific, not an automatic hand segmentation claim.
"""
import io,json
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFilter,ImageChops
root=Path(__file__).resolve().parents[1];out=root/'reference-validation';out.mkdir(exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30)
key='demo-b-pose-3-happy-hand-protected-v2'
existing=next((j for j in c.get('/jobs').json() if j['idempotency_key']==key),None)
if existing:print(json.dumps(existing));raise SystemExit
j=c.get('/jobs/6a018b96cc404b72a1f3c2a4f82fc0f1').json();a=next(a for a in j['output_assets'] if a['role']=='mask')
m=Image.open(io.BytesIO(c.get(a['download_url']).content)).convert('L')
protect=Image.new('L',m.size);points=[(440,183),(474,175),(493,177),(522,162),(527,163),(530,170),(510,187),(529,182),(534,186),(533,192),(506,204),(513,210),(513,216),(484,228),(448,229)]
ImageDraw.Draw(protect).polygon(points,fill=255)
protect=protect.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(2))
m=ImageChops.multiply(m,ImageChops.invert(protect));path=out/'b-pose3-hand-protected-mask.png';m.save(path)
r=c.post('/assets',files={'file':(path.name,path.read_bytes(),'image/png')},data={'role':'mask'});r.raise_for_status();mask=r.json()
r=c.post('/jobs',json={**{k:v for k,v in j['body'].items() if k!='idempotency_key'},'mask_asset_id':mask['id'],'idempotency_key':key});r.raise_for_status();record={'job':r.json(),'mask_asset':mask,'protected_polygon':points,'note':'Human-reviewed sample-specific protection, based on original image; original failed sample retained.'}
(out/'occlusion-correction.json').write_text(json.dumps(record,indent=2));print(json.dumps(record['job']))
