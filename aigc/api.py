import asyncio,contextlib,os,sqlite3
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Request,Response
from fastapi.responses import FileResponse
from .schema import Character,SceneSpec,SceneRequest,JobRequest,Approval,PoseState
from .store import Store
from .assets import save_image,asset_path
from .thumbnails import thumbnail
from .comfy import Comfy
from .worker import Worker
from .llm import parse_scene

ROOT=Path(__file__).resolve().parents[1]
store=Store(os.environ.get('AIGC_DATA_DIR',str(ROOT/'data')))
comfy=Comfy(os.environ.get('AIGC_COMFY_URL','http://127.0.0.1:8188'))

@asynccontextmanager
async def lifespan(app):
    worker=Worker(store,comfy);task=asyncio.create_task(worker.run());app.state.worker=task
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):await task
    await comfy.close()
app=FastAPI(title='剧情驱动 AIGC 资产系统',version='0.1.0',lifespan=lifespan)

def required(kind,id):
    record=store.get(kind,id)
    if not record:raise HTTPException(404,'Unknown '+kind+': '+str(id))
    return record

def validate_spec(spec):
    if spec.character_id:
        c=required('character',spec.character_id)
        if spec.outfit_id and spec.outfit_id not in {x['id'] for x in c['outfits']}:raise HTTPException(422,'Unknown outfit')
    return spec

@app.get('/health')
async def health():return {'status':'ok','worker_alive':not app.state.worker.done()}

@app.post('/characters',status_code=201)
async def create_character(body:Character):
    try:return store.put('character',body.model_dump(),body.id)
    except sqlite3.IntegrityError:raise HTTPException(409,'Character exists; immutable identity requires a new character ID')
@app.get('/characters')
async def characters():return store.list('character')
@app.get('/characters/{id}')
async def character(id:str):return required('character',id)

@app.post('/scene-specs',status_code=201)
async def scene_specs(body:SceneRequest):
    metadata={'source':'manual'}
    if body.manual:spec=validate_spec(body.manual)
    else:
        c=required('character',body.character_id) if body.character_id else None
        if body.outfit_id and (not c or body.outfit_id not in {x['id'] for x in c['outfits']}):raise HTTPException(422,'Unknown outfit')
        try:spec,metadata=await parse_scene(body,c)
        except RuntimeError as e:raise HTTPException(503,str(e))
        except Exception:raise HTTPException(502,'LLM request or schema correction failed; check server configuration')
        validate_spec(spec)
    return store.put('scene_spec',{'spec':spec.model_dump(),'metadata':metadata})
@app.get('/scene-specs/{id}')
async def get_spec(id:str):return required('scene_spec',id)
@app.put('/scene-specs/{id}')
async def revise_spec(id:str,body:SceneSpec):
    required('scene_spec',id);validate_spec(body)
    # Immutable revision: existing jobs keep their exact submitted specification.
    return store.put('scene_spec',{'spec':body.model_dump(),'metadata':{'source':'manual-revision','parent_spec_id':id}})

@app.post('/assets',status_code=201)
async def upload_asset(file:UploadFile=File(...),role:str=Form('reference')):
    if role not in ('reference','mask','pose_render'):raise HTTPException(422,'Invalid upload role')
    try:return save_image(store,await file.read(64*1024*1024+1),{'role':role,'source':'upload'})
    except Exception as e:raise HTTPException(422,str(e))
@app.get('/assets')
async def assets():return store.list('asset')
@app.get('/assets/{id}')
async def asset(id:str):
    a=required('asset',id);return dict(a,download_url='/assets/'+id+'/file')
@app.get('/assets/{id}/file')
async def asset_file(id:str):return FileResponse(asset_path(store,required('asset',id)),media_type='image/png',filename=id+'.png',headers={'Cache-Control':'private, max-age=31536000, immutable'})
@app.get('/assets/{id}/thumbnail')
def asset_thumbnail(id:str,request:Request):
    a=required('asset',id)
    path=asset_path(store,a)
    version=a.get('sha256') or str(path.stat().st_mtime_ns)
    etag='"thumb-v1-'+version+'"'
    headers={'Cache-Control':'private, max-age=31536000, immutable','ETag':etag}
    if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers=headers)
    return Response(thumbnail(str(path),version),media_type='image/webp',headers=headers)
@app.post('/assets/{id}/approve')
async def approve(id:str,body:Approval):
    a=required('asset',id);c=required('character',body.character_id)
    from .workbench import Transaction
    try:
        with store.connect() as db: Transaction(db).image(id, body.character_id)
    except (LookupError, ValueError) as e: raise HTTPException(422, str(e))
    if body.kind in ('outfit','pose') and not a.get('scene_spec_id'):raise HTTPException(422,'Approval requires a generated result of this type')
    if body.outfit_id and body.outfit_id not in {o['id'] for o in c['outfits']}:raise HTTPException(422,'Unknown outfit')
    if a['role'] in ('mask','crop','pose_render','transparent') or a['mode']=='RGBA':raise HTTPException(422,'Approval requires original RGB character image')
    if a.get('scene_spec_id'):
        spec=required('scene_spec',a['scene_spec_id'])['spec']
        if (spec.get('character_id'),spec.get('outfit_id'))!=(body.character_id,body.outfit_id):raise HTTPException(422,'Approval identity differs from generation identity')
        if body.kind in ('outfit','pose') and spec['asset_type']!=body.kind:raise HTTPException(422,'Approval requires a matching result type')
        if body.kind=='character' and spec['asset_type']!='sprite':raise HTTPException(422,'Character approval requires an identity result')
    return store.put('approval',dict(body.model_dump(),asset_id=id))

@app.post('/poses',status_code=201)
async def poses(body:PoseState):
    a=required('asset',body.render_asset_id)
    if a['role']!='pose_render':raise HTTPException(422,'Requires pose_render asset')
    return store.put('pose',body.model_dump())
@app.get('/poses')
async def list_poses():return store.list('pose')

@app.post('/jobs',status_code=201)
async def create_job(body:JobRequest):
    spec=required('scene_spec',body.scene_spec_id)['spec']
    if spec['unresolved']:raise HTTPException(422,'Resolve ambiguous visual specification before generation')
    kind=spec['asset_type']
    if kind in ('outfit','pose','expression','matte'):
        if not body.reference_asset_id:raise HTTPException(422,'Reference required')
        a=required('asset',body.reference_asset_id)
        if kind in ('outfit','pose','expression'):
            expected='pose' if kind=='expression' else 'character'
            approvals=store.list('approval')
            if not any(x['asset_id']==a['id'] and x['kind'] in (('character','outfit') if kind=='pose' else (expected,)) and x['character_id']==spec['character_id'] and (kind=='outfit' or x.get('outfit_id')==spec.get('outfit_id')) for x in approvals):raise HTTPException(422,'Approved '+expected+' reference required for this character/outfit')
    if kind=='outfit' and not spec.get('outfit_id'):raise HTTPException(422,'Outfit version required')
    if kind=='pose':
        if not body.pose_asset_id:raise HTTPException(422,'Saved pose state required')
        required('pose',body.pose_asset_id)
    if body.mask_asset_id:
        mask=required('asset',body.mask_asset_id);ref=required('asset',body.reference_asset_id)
        if (mask['width'],mask['height'])!=(ref['width'],ref['height']):raise HTTPException(422,'Mask canvas must match reference')
    try:return store.create_job(body.model_dump())
    except ValueError as e:raise HTTPException(409,str(e))
@app.get('/jobs')
async def jobs():return store.jobs()
@app.get('/jobs/{id}')
async def job(id:str):
    j=store.job(id)
    if not j:raise HTTPException(404,'Unknown job')
    return dict(j,output_assets=[dict(required('asset',a),download_url='/assets/'+a+'/file') for a in j['outputs']])
@app.post('/jobs/{id}/cancel')
async def cancel(id:str):
    j=await job(id)
    if j['state']=='queued':store.update_job(id,state='cancelled');return store.job(id)
    if j['state'] in ('running','recovering') and j['prompt_id']:
        if await comfy.cancel_pending(j['prompt_id']):store.update_job(id,state='cancelled');return store.job(id)
    raise HTTPException(409,'Job not safely cancellable. Running inference is not globally interrupted.')

@app.get('/approvals')
async def approvals():return store.list('approval')
@app.get('/jobs/{id}/record')
async def generation_record(id:str):
    j=await job(id)
    return {'job':j,'execution':store.get('execution',id),'history':store.get('history',id),'validation':store.get('validation',id)}

# Resolve the store lazily so API tests and deployments use the same data root.
from .template_api import template_router
app.include_router(template_router(lambda: store))

from .production import production_router
app.include_router(production_router(lambda: store, lambda: comfy))
