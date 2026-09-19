import json,io
from pathlib import Path
import httpx
from PIL import Image,ImageChops,ImageDraw
root=Path(__file__).resolve().parents[1];out=root/'reference-validation';c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30)
def asset(id):return Image.open(io.BytesIO(c.get('/assets/'+id+'/file').content)).convert('RGB')
j=c.get('/jobs/e49ff7224c51461686d4bafa161a49b1').json();roles={a['role']:a['id'] for a in j['output_assets']};original=asset(j['body']['reference_asset_id']);mask=asset(roles['mask']).convert('L');outside=mask.point(lambda x:255 if x==0 else 0);n=outside.histogram()[255]
images={'original':original,'local masked':asset(roles['original']),'VNCCS Detailer':Image.open(out/'reference-detailer-0.png').convert('RGB'),'whole image':Image.open(out/'whole-image-control-0.png').convert('RGB')};report={}
for name,im in images.items():
 if name=='original':continue
 if im.size!=original.size:report[name]={'canvas_unchanged':False};continue
 diff=ImageChops.difference(original,im);chs=diff.split();mx=ImageChops.lighter(ImageChops.lighter(chs[0],chs[1]),chs[2]);hist=ImageChops.multiply(mx,outside).histogram();changed=sum(hist[1:]);tot=sum(sum(i*v for i,v in enumerate(ImageChops.multiply(ch,outside).histogram())) for ch in chs)
 report[name]={'canvas_unchanged':True,'outside_pixels':n,'outside_changed_pixels':changed,'outside_changed_fraction':changed/n,'outside_mean_absolute_rgb_error_0_255':tot/(3*n)}
report['scope']='One approved B pose, happy edit, fixed seed. Methods differ in crop scale, prompt wording and blending; this is an operational comparison, not an isolated causal benchmark.'
(out/'drift-comparison.json').write_text(json.dumps(report,indent=2))
canvas=Image.new('RGB',(1600,660),'#eeeeee');d=ImageDraw.Draw(canvas)
for i,(name,im) in enumerate(images.items()):
 small=im.copy();small.thumbnail((390,390));canvas.paste(small,(400*i,25));face=im.crop((420,80,610,270)).resize((230,230));canvas.paste(face,(400*i+70,425));d.text((400*i+10,5),name,fill='black')
canvas.save(root/'samples/edit-methods-comparison.png');print(json.dumps(report))
