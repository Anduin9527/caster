import asyncio,json,time,fcntl,uuid
from .schema import SceneSpec
from .prompts import compile_prompt
from .workflows import build,validate_models
from .assets import save_image,asset_path

class Worker:
    def __init__(self,store,comfy):
        self.store=store;self.comfy=comfy
        self.lock=(store.root/'worker.lock').open('a')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    async def run(self):
        listener=None;listening_id=None
        try:
            while True:
                try:
                    active=self.store.jobs(['submitting','running','recovering','submission_uncertain'])
                    if active:
                        current=active[0]
                        if listening_id!=current['id'] or listener is None or listener.done():
                            if listener:listener.cancel()
                            listening_id=current['id']
                            listener=asyncio.create_task(self.comfy.progress(listening_id,lambda event,jid=listening_id:self.store.update_job(jid,progress=event)))
                        await self.reconcile(current)
                    else:
                        if listener:listener.cancel();listener=None;listening_id=None
                        waiting=self.store.jobs(['queued'])
                        if waiting:
                            q=await self.comfy.queue()
                            if not q.get('queue_running') and not q.get('queue_pending'):await self.execute(waiting[0])
                except Exception:
                    import logging
                    logging.exception('Worker transient error; durable queue retained')
                await asyncio.sleep(2)
        finally:
            if listener:listener.cancel()
            self.lock.close()
    async def execute(self,job):
        id=job['id'];body=job['body']
        try:
            spec_record=self.store.get('scene_spec',body['scene_spec_id']);spec=SceneSpec.model_validate(spec_record['spec'])
            character=self.store.get('character',spec.character_id) if spec.character_id else None
            prompt=compile_prompt(spec,character);inputs={}
            from .canvas import preset_size, source_size
            if spec.canvas_preset:
                inputs['width'],inputs['height']=preset_size(spec.canvas_preset)
            if body.get('reference_asset_id'):
                asset=self.store.get('asset',body['reference_asset_id']);inputs['reference']=await self.comfy.upload(asset_path(self.store,asset))
                if spec.asset_type in ('outfit','pose'):
                    inputs['width'],inputs['height']=source_size(asset)
            if body.get('pose_asset_id'):
                pose=self.store.get('pose',body['pose_asset_id'])
                if pose.get('preset_id',0)>=101:
                    from .pose_studio_presets import materialize
                    pose=materialize(self.store,pose['preset_id'],inputs['width'],inputs['height'])
                a=self.store.get('asset',pose['render_asset_id']);inputs['pose']=await self.comfy.upload(asset_path(self.store,a))
                prompt['positive']='Draw character from image2 in the pose shown in image1. Preserve face, hair and all outfit details from image2. '+spec.action+' '+(spec.expression or 'neutral expression')+' '+pose['lighting_prompt']
            if spec.asset_type=='expression':
                inputs['region']=json.dumps(body.get('face_region') or [])
                inputs['mask']=''
                if body.get('mask_asset_id'):
                    inputs['mask']=await self.comfy.upload(asset_path(self.store,self.store.get('asset',body['mask_asset_id'])))
                prompt['positive']='Change only the facial expression to '+spec.expression+'. Preserve identity, hair, clothing, framing and background.'
            graph,outputs,version=build(spec.asset_type,prompt,body['seed'],id,inputs)
            await validate_models(self.comfy,graph)
            from pathlib import Path
            deployment=Path(__file__).resolve().parents[1]
            provenance={}
            for filename in ('models-manifest.json','additional-models-manifest.json','nodes-manifest.json'):
                path=deployment/filename
                if path.exists():provenance[filename]=json.loads(path.read_text())
            self.store.put('execution',dict(version,prompt=prompt,output_nodes=outputs,provenance=provenance,started=time.time()),id,replace=True)
            # Persist intent before network I/O. On uncertainty NEVER auto-resubmit.
            if self.store.job(id)['state']!='queued':return
            self.store.update_job(id,state='submitting')
            try:pid=await self.comfy.submit(graph,id)
            except ValueError:raise
            except Exception:
                self.store.update_job(id,state='submission_uncertain',error='Submission result uncertain; reconciling history and queue, no automatic resubmission');return
            self.store.update_job(id,state='running',prompt_id=pid,error=None)
        except Exception as e:self.store.update_job(id,state='failed',error=str(e)[:4000])
    async def reconcile(self,job):
        id=job['id'];pid=job['prompt_id']
        try:
            if not pid:
                pid=await self.comfy.locate(id)
                if not pid:
                    self.store.update_job(id,state='submission_uncertain',error='No matching prompt in current ComfyUI history/queue. Operator reconciliation required; queue remains paused.');return
                self.store.update_job(id,prompt_id=pid,state='running',error=None)
            hist=await self.comfy.history(pid)
            if pid not in hist:
                q=await self.comfy.queue()
                if not any(x[1]==pid for x in q.get('queue_pending',[])+q.get('queue_running',[])):
                    self.store.update_job(id,state='submission_uncertain',error='Known prompt missing from history and queue; no automatic replay')
                return
            result=hist[pid];st=result.get('status',{})
            if st.get('status_str')=='error':
                message=json.dumps(st.get('messages'),ensure_ascii=False)
                state='needs_correction' if 'AIGC_FACE_SELECTION' in message else 'failed'
                self.store.update_job(id,state=state,error=message[:6000]);return
            if not st.get('completed'):return
            execution=self.store.get('execution',id)
            if not execution:raise ValueError('Missing persisted execution metadata')
            assets=[]
            for node,role in execution['output_nodes'].items():
                imgs=result.get('outputs',{}).get(node,{}).get('images',[])
                if not imgs:raise ValueError('Required SaveImage output missing: '+node)
                for index,entry in enumerate(imgs):
                    # Restart-safe ingestion: stable output key avoids duplicated assets.
                    key=id+':'+node+':'+str(index)
                    existing=self.store.get('output',key)
                    if existing:assets.append(existing['asset_id']);continue
                    blob=await self.comfy.download(entry)
                    a=save_image(self.store,blob,{'role':role,'job_id':id,'parent_asset_id':job['body'].get('reference_asset_id'),'scene_spec_id':job['body']['scene_spec_id'],'prompt_id':pid,'generation':execution,'source_output':entry},asset_id=uuid.uuid5(uuid.NAMESPACE_URL,key).hex)
                    self.store.put('output',{'asset_id':a['id']},key);assets.append(a['id'])
            self.store.put('history',result,id,replace=True)
            spec=self.store.get('scene_spec',job['body']['scene_spec_id'])['spec']
            if spec['asset_type']=='expression':
                from PIL import Image,ImageChops
                records=[self.store.get('asset',a) for a in assets]
                roles={a['role']:a for a in records}
                original=Image.open(asset_path(self.store,self.store.get('asset',job['body']['reference_asset_id']))).convert('RGB')
                edited=Image.open(asset_path(self.store,roles['original'])).convert('RGB')
                mask=Image.open(asset_path(self.store,roles['mask'])).convert('L')
                canvas=original.size==edited.size==mask.size
                outside_ok=canvas and ImageChops.multiply(ImageChops.difference(original,edited),mask.point(lambda v:255 if v==0 else 0).convert('RGB')).getbbox() is None
                report={'canvas_unchanged':canvas,'outside_mask_unchanged':outside_ok,'original_asset_preserved':job['body']['reference_asset_id'] not in assets,'face_metadata':result.get('outputs',{}).get('14',{})}
                self.store.put('validation',report,id,replace=True)
                if not all(report[k] for k in ['canvas_unchanged','outside_mask_unchanged','original_asset_preserved']):
                    self.store.update_job(id,outputs=assets)
                    raise ValueError('Expression pixel invariance validation failed; outputs preserved for diagnosis')
            self.store.update_job(id,state='succeeded',outputs=assets,error=None,progress={'completed':True,'elapsed_seconds':time.time()-execution['started']})
        except (ConnectionError,OSError):return
        except Exception as e:
            import httpx
            if isinstance(e,httpx.HTTPError):
                self.store.update_job(id,state='recovering',error='ComfyUI unavailable; will reconcile when reachable');return
            self.store.update_job(id,state='failed',error=str(e)[:4000])
