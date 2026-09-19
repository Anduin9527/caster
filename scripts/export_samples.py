import json,shutil
from pathlib import Path
from PIL import Image,ImageDraw
import httpx
root=Path(__file__).resolve().parents[1];out=root/'samples';out.mkdir(exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30);jobs=c.get('/jobs').json();index=[]
for j in jobs:
 if j['state']!='succeeded':continue
 d=c.get('/jobs/'+j['id']).json();name=j['idempotency_key']
 for i,a in enumerate(d['output_assets']):
  p=out/(name+'-'+a['role']+'-'+str(i)+'.png');p.write_bytes(c.get(a['download_url']).content)
  index.append({'job_id':j['id'],'key':name,'asset_id':a['id'],'role':a['role'],'file':p.name,'seconds':j.get('progress',{}).get('elapsed_seconds')})
(out/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2))
poses=[x for x in index if x['key'] in {f'demo-b-pose-{i}-v1' for i in (1,2,3)} and x['role']=='original']
canvas=Image.new('RGB',(360*max(1,len(poses)),405),'#eeeeee');draw=ImageDraw.Draw(canvas)
for i,x in enumerate(poses):
 im=Image.open(out/x['file']).convert('RGB');im.thumbnail((350,360));canvas.paste(im,(i*360+(360-im.width)//2,25));draw.text((i*360+10,385),x['key'],fill='black')
canvas.save(out/'character-b-poses-review.png')
# Display alpha over a checkerboard; retain original RGBA separately.
p=root.parent/'ComfyUI/output/aigc/transparent_00001_.png'
if p.exists():
 im=Image.open(p).convert('RGBA');bg=Image.new('RGBA',im.size,'white');d=ImageDraw.Draw(bg)
 for y in range(0,im.height,24):
  for x in range(0,im.width,24):
   if (x//24+y//24)%2:d.rectangle((x,y,x+23,y+23),fill='#c6c6c6')
 Image.alpha_composite(bg,im).convert('RGB').save(out/'alpha-checker-preview.png')
print(json.dumps({'exported':len(index),'b_poses':len(poses)}))
