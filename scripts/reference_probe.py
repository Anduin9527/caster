"""Run the adapted upstream Detailer and whole-image control serially in ComfyUI.
Submission receipts are persisted before polling; uncertain POST is never repeated.
"""
import json,time,uuid
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1];out=root/'reference-validation';out.mkdir(exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8188',timeout=60)
b=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30)
ref='2183d1aac32259fc8698cbd1dfbdf206'
r=c.post('/upload/image',files={'image':('reference-validation.png',b.get(f'/assets/{ref}/file').content,'image/png')},data={'overwrite':'true'});r.raise_for_status();filename=r.json()['name']
base=json.loads((root/'workflows/qwen-edit.api.json').read_text());base['7']['inputs']['image']=filename
schema=c.get('/object_info/VNCCS_QWEN_Detailer').json()['VNCCS_QWEN_Detailer']['input']
params={}
for name,definition in {**schema['required'],**schema['optional']}.items():
 if len(definition)>1 and 'default' in definition[1]:params[name]=definition[1]['default']
params.update(image=['7',0],bbox_detector=['12',0],model=['6',0],clip=['2',0],vae=['3',0],prompt='Change emotion to happy',threshold=.5,dilation=0,drop_size=10,feather=0,steps=4,cfg=1,seed=9751,sampler_name='euler',scheduler='simple',denoise=1,tiled_vae_decode=False,tile_size=512,target_size=1024,upscale_method='nearest-exact',crop_method='disabled',color_match_method='kornia_reinhard',seam_fix=True,qwen_2511=True,distortion_fix=True)
g={k:v for k,v in base.items() if int(k)<=7}
g['12']={'class_type':'UltralyticsDetectorProvider','inputs':{'model_name':'bbox/face_yolov8m.pt'}}
g['13']={'class_type':'VNCCS_QWEN_Detailer','inputs':params}
g['14']={'class_type':'SaveImage','inputs':{'images':['13',0],'filename_prefix':'aigc/reference-detailer'}}
whole=json.loads(json.dumps(base));whole['8']['inputs']['prompt']='Change only the facial expression to a gentle happy smile. Preserve identity, hair, clothing, body pose and background.';whole['9']['inputs']['seed']=9751;whole['11']['inputs']['filename_prefix']='aigc/whole-image-control'
(out/'adaptations.json').write_text(json.dumps({'upstream_commit':'70b752f2f1ac7a6aa22aa9418f730195c3cef58b','reference_asset_id':ref,'changes':['GGUF Q5 loader replaced by installed BF16 UNETLoader','LoRA path normalized to installed filename','legacy mvgd color option replaced by current kornia_reinhard','seed fixed to 9751','PreviewImage replaced by SaveImage','input image replaced with approved B pose 2'],'upstream_sam_connected':False,'production_expression_pipeline_uses_sam':True},indent=2))
for name,graph,node in [('reference-detailer',g,'14'),('whole-image-control',whole,'11')]:
 (root/'workflows'/f'{name}.api.json').write_text(json.dumps(graph,indent=2))
 receipt=out/f'{name}.submission.json';result_path=out/f'{name}.result.json'
 if result_path.exists():continue
 if receipt.exists():
  r=json.loads(receipt.read_text());pid=r.get('prompt_id')
  if not pid:raise RuntimeError('Submission uncertain: inspect ComfyUI history; do not resubmit')
 else:
  receipt.write_text(json.dumps({'state':'submitting','submitted':time.time()}))
  r=c.post('/prompt',json={'prompt':graph,'client_id':str(uuid.uuid4()),'extra_data':{'aigc_job_id':name+'-v1'}})
  if r.status_code!=200:
   (out/f'{name}.rejection.json').write_text(r.text);r.raise_for_status()
  r=r.json();pid=r['prompt_id'];receipt.write_text(json.dumps(r))
 print(name,pid,flush=True)
 while True:
  h=c.get('/history/'+pid);h.raise_for_status();h=h.json()
  if pid in h:break
  time.sleep(3)
 record=h[pid];result_path.write_text(json.dumps(record,indent=2))
 print(name,record['status']['status_str'],flush=True)
 for i,im in enumerate(record.get('outputs',{}).get(node,{}).get('images',[])):
  r=c.get('/view',params=im);r.raise_for_status();(out/f'{name}-{i}.png').write_bytes(r.content)
