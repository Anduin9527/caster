import asyncio,hashlib,io,json
from pathlib import Path
import pytest
from PIL import Image
from aigc.canvas import PRESETS,preset_size
from aigc.schema import SceneSpec
from aigc.workbench import BatchRequest,create_batch
from aigc.workflows import build
from aigc.store import Store
from aigc.worker import Worker
from aigc import pose_studio_presets as poses


def test_preset_validation_and_identity_batch_persistence(tmp_path):
    store=Store(tmp_path);store.put('character',dict(name='Miku',fixed_tags=[],outfits=[]),'miku')
    for p in PRESETS:
        r=BatchRequest(role='identity',expected_revision=0,idempotency_key=p['id'],canvas_preset=p['id'],candidates=[{}])
        b=create_batch(store,'miku',r)
        assert create_batch(store,'miku',r)['id']==b['id']
        job=store.job(b['job_ids'][0]);spec=store.get('scene_spec',job['body']['scene_spec_id'])['spec']
        assert spec['canvas_preset']==p['id']
        w,h=preset_size(spec['canvas_preset'])
        g,_,_=build('sprite',{'positive':'test','negative':''},1,'id',{'width':w,'height':h})
        assert (g['6']['inputs']['width'],g['6']['inputs']['height'])==(w,h)
    with pytest.raises(ValueError):SceneSpec(asset_type='sprite',character_id='a',canvas_preset='99999x99999')
    with pytest.raises(ValueError,match='Downstream'):
        create_batch(store,'miku',BatchRequest(role='outfit',expected_revision=0,idempotency_key='bad',canvas_preset='1024x1024',candidates=[{}]))


def test_worker_outfit_inherits_actual_source_over_scene_canvas(tmp_path,monkeypatch):
    store=Store(tmp_path);store.put('character',dict(name='Miku',fixed_tags=[],outfits=[dict(id='coat',tags=['coat'])]),'miku')
    Image.new('RGB',(768,1152)).save(tmp_path/'files/ref.png')
    store.put('asset',dict(path='ref.png',width=768,height=1152),'ref')
    store.put('scene_spec',{'spec':SceneSpec(asset_type='outfit',character_id='miku',outfit_id='coat',canvas_preset='1024x1024').model_dump()},'s')
    job=store.create_job(dict(scene_spec_id='s',seed=1,reference_asset_id='ref',idempotency_key='outfit'))
    class Fake:
        async def upload(self,path):return 'ref.png'
        async def submit(self,graph,key):self.graph=graph;return 'pid'
    async def validate(*args):pass
    monkeypatch.setattr('aigc.worker.validate_models',validate)
    fake=Fake();worker=Worker(store,fake)
    try:asyncio.run(worker.execute(job))
    finally:worker.lock.close()
    assert store.job(job['id'])['state']=='running'
    # VAEEncode uses the uploaded source directly; no canvas resize can override it.
    assert fake.graph['13']['inputs']['image']=='ref.png'
    assert fake.graph['6']['inputs']['pixels']==['13',0]
    assert not any('width' in n['inputs'] or 'height' in n['inputs'] for n in fake.graph.values())


def test_native_render_versions_do_not_replace_legacy(tmp_path,monkeypatch):
    store=Store(tmp_path);item=dict(poses.ITEMS[105]);item['native_renders']={}
    root=tmp_path/'pose-studio-library';(root/'renders').mkdir(parents=True)
    state=b'{}';item['json_sha256']=hashlib.sha256(state).hexdigest()
    (root/item['json_path']).parent.mkdir(parents=True);(root/item['json_path']).write_bytes(state)
    for key,size in [('legacy',(1024,1024)),('1024x1536',(1024,1536)),('768x1152',(768,1152))]:
        out=io.BytesIO();Image.new('RGB',size,'white').save(out,format='PNG');blob=out.getvalue();digest=hashlib.sha256(blob).hexdigest()
        if key=='legacy':item['render_sha256']=digest;filename='105.png'
        else:item['native_renders'][key]=digest;filename='105-'+key+'.png'
        (root/'renders'/filename).write_bytes(blob)
    monkeypatch.setitem(poses.ITEMS,105,item)
    old=poses.materialize(store,105)
    first=poses.materialize(store,105,1024,1536);second=poses.materialize(store,105,768,1152)
    assert len({old['id'],first['id'],second['id']})==3
    assert poses.materialize(store,105,1024,1536)==first
    assert poses.render(store,105)==(root/'renders/105.png').read_bytes()
    assert Image.open(io.BytesIO(poses.render(store,105,768,1152))).size==(768,1152)
    assert not store.jobs() and not store.list('approval')
