"""Export enlarged face comparisons and persisted pixel-validation evidence."""
import json,io
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1];out=root/'samples';out.mkdir(exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30)
jobs=c.get('/jobs').json();report=[]
def im(asset):
 r=c.get('/assets/'+asset+'/file');r.raise_for_status();return Image.open(io.BytesIO(r.content)).convert('RGB')
for ch in ['demo-a','demo-b']:
 rows=[]
 for j in jobs:
  if not j['idempotency_key'].startswith('acceptance-'+ch) or j['idempotency_key'].endswith('-alpha') or j['state']!='succeeded':continue
  record=c.get('/jobs/'+j['id']+'/record').json();detail=c.get('/jobs/'+j['id']).json();roles={a['role']:a['id'] for a in detail['output_assets']}
  # Mask bounds define a consistent comparison viewport, including modest context.
  mask=im(roles['mask']).convert('L');box=mask.getbbox();pad=25
  box=(max(0,box[0]-pad),max(0,box[1]-pad),min(mask.width,box[2]+pad),min(mask.height,box[3]+pad))
  images=[im(j['body']['reference_asset_id']).crop(box),im(roles['original']).crop(box),mask.crop(box).convert('RGB')]
  rows.append((j,images));report.append({'job_id':j['id'],'key':j['idempotency_key'],'state':j['state'],'seconds':j['progress']['elapsed_seconds'],'record':record})
 if not rows:continue
 canvas=Image.new('RGB',(760,280*len(rows)), '#eeeeee');d=ImageDraw.Draw(canvas)
 for y,(j,images) in enumerate(rows):
  for x,p in enumerate(images):
   p.thumbnail((245,245));canvas.paste(p,(x*250+(250-p.width)//2,y*280+25))
  d.text((5,y*280+5),j['idempotency_key'].replace('acceptance-'+ch+'-','')[:55],fill='black')
 canvas.save(out/(ch+'-expression-faces-review.png'))
(root/'expression-acceptance.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'reviewed_jobs':len(report)}))
