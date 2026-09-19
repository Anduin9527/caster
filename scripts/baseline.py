import json,time,urllib.request,pathlib,uuid
root=pathlib.Path(__file__).resolve().parents[1]
def graph(prompt, width=832,height=1216):
 return {'1':{'class_type':'UNETLoader','inputs':{'unet_name':'AnimaYume_v15_base.safetensors','weight_dtype':'default'}},'2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_3_06b_base.safetensors','type':'stable_diffusion','device':'default'}},'3':{'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors'}},'4':{'class_type':'CLIPTextEncode','inputs':{'text':prompt,'clip':['2',0]}},'5':{'class_type':'CLIPTextEncode','inputs':{'text':'low quality, blurry, malformed hands, cropped feet, text, watermark','clip':['2',0]}},'6':{'class_type':'EmptyLatentImage','inputs':{'width':width,'height':height,'batch_size':1}},'7':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['4',0],'negative':['5',0],'latent_image':['6',0],'seed':9527,'steps':30,'cfg':5.0,'sampler_name':'euler_ancestral','scheduler':'normal','denoise':1.0}},'8':{'class_type':'VAEDecode','inputs':{'samples':['7',0],'vae':['3',0]}},'9':{'class_type':'SaveImage','inputs':{'images':['8',0],'filename_prefix':'aigc/baseline'}}}
if __name__=='__main__':
 root.joinpath('workflows').mkdir(exist_ok=True)
 for kind,w,h,p in [('sprite',832,1216,'1girl, solo, full body, silver hair, blue eyes, navy blue long coat, white blouse, black boots, standing, neutral expression, simple light gray background. A clean anime character reference illustration, entire body and feet visible.'),('background',1344,768,'no people, empty scene, quiet library, wooden bookshelves, warm afternoon sunlight, wide shot. An anime visual novel background with a clear open foreground.')]:
  g=graph(p,w,h);root.joinpath('workflows',kind+'.api.json').write_text(json.dumps(g,indent=2))
  payload={'prompt':g,'client_id':'aigc-baseline','extra_data':{'aigc_job_id':'baseline-'+kind}}
  start=time.time()
  req=urllib.request.Request('http://127.0.0.1:8188/prompt',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  result=json.load(urllib.request.urlopen(req));pid=result['prompt_id'];print(kind,pid,flush=True)
  root.joinpath('workflows',kind+'.submission.json').write_text(json.dumps(result))
  while True:
   hist=json.load(urllib.request.urlopen('http://127.0.0.1:8188/history/'+pid))
   if pid in hist:
    record=hist[pid];record['elapsed_seconds']=time.time()-start
    root.joinpath('workflows',kind+'.result.json').write_text(json.dumps(record,indent=2));print(kind,record.get('status'),time.time()-start,flush=True);break
   time.sleep(5)
