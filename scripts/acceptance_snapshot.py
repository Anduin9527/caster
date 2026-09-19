"""Compact acceptance manifest and checkerboard contact sheets, no implied approval."""
import json,io,collections,hashlib
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1];c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30);jobs=c.get('/jobs').json();assets={a['id']:a for a in c.get('/assets').json()};report=[];alphas=[]
for j in jobs:
 item={k:j[k] for k in ['id','idempotency_key','state','body','prompt_id','error','progress','outputs']}
 if j['state']=='succeeded':
  r=c.get('/jobs/'+j['id']+'/record').json();item['validation']=r.get('validation');item['assets']=[{k:assets[a].get(k) for k in ['id','role','parent_asset_id','width','height','mode','sha256']} for a in j['outputs']]
  for a in item['assets']:
   if a['role']=='transparent':
    raw=c.get('/assets/'+a['id']+'/file').content;im=Image.open(io.BytesIO(raw)).convert('RGBA');a['alpha_extrema']=im.getchannel('A').getextrema();a['download_sha256_matches']=hashlib.sha256(raw).hexdigest()==a['sha256'];alphas.append((j['idempotency_key'],im))
 report.append(item)
summary={'states':dict(collections.Counter(j['state'] for j in jobs)),'jobs':report,'approvals':c.get('/approvals').json(),'llm':'deferred by user; no real endpoint tested','a_pose_expression_gate':'New A poses need separate approval; identity and B poses explicitly approved.'}
(root/'acceptance-manifest.json').write_text(json.dumps(summary,indent=2))
for ch in ['demo-a','demo-b']:
 group=[(k,im) for k,im in alphas if ch in k];n=len(group)
 if not n:continue
 sheet=Image.new('RGB',(1000,320*((n+3)//4)),'white');d=ImageDraw.Draw(sheet)
 for idx,(key,im) in enumerate(group):
  x=(idx%4)*250;y=(idx//4)*320;im.thumbnail((244,280));bg=Image.new('RGBA',(250,285),'#f5f5f5');bd=ImageDraw.Draw(bg)
  for cy in range(0,285,16):
   for cx in range(0,250,16):
    if (cx//16+cy//16)%2:bd.rectangle((cx,cy,cx+15,cy+15),fill='#bbbbbb')
  bg.alpha_composite(im,((250-im.width)//2,(285-im.height)//2));sheet.paste(bg.convert('RGB'),(x,y));d.text((x+3,y+290),key.replace('acceptance-'+ch+'-','')[-33:],fill='black')
 sheet.save(root/'samples'/(ch+'-transparent-review.png'))
print(json.dumps({'states':summary['states'],'rgba_outputs':len(alphas),'all_alpha_hashes_verified':all(a.get('download_sha256_matches',True) for j in report for a in j.get('assets',[]))}))
