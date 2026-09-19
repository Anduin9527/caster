import asyncio,json,importlib.util
from pathlib import Path
import pytest,httpx
from PIL import Image,ImageChops
from aigc.schema import SceneSpec,SceneRequest
from aigc.store import Store
from aigc.prompts import compile_prompt
from aigc.worker import Worker
from aigc import llm

def test_prompt_tags_only_deduplicated():
    spec=SceneSpec(asset_type='sprite',character_id='a',visual_tags=['Blue Eyes','blue eyes'],description='Smile. Smile.')
    p=compile_prompt(spec,{'fixed_tags':['blue eyes'],'description':'Silver hair.','outfits':[]})
    assert p['positive'].count('blue eyes')==1
    assert 'Smile. Smile.' in p['positive']


def test_persistent_idempotency(tmp_path):
    s=Store(tmp_path);b={'idempotency_key':'one','scene_spec_id':'spec'}
    j=s.create_job(b)
    assert Store(tmp_path).create_job(b)['id']==j['id']
    with pytest.raises(ValueError):s.create_job(dict(b,scene_spec_id='different'))

class FakeComfy:
    def __init__(self):self.submitted=0;self.result={};self.found=None
    async def locate(self,id):return self.found
    async def history(self,id):return self.result
    async def queue(self):return {'queue_running':[],'queue_pending':[]}

def test_uncertain_submission_never_replayed(tmp_path):
    s=Store(tmp_path);j=s.create_job({'idempotency_key':'a'});s.update_job(j['id'],state='submitting')
    c=FakeComfy();w=Worker(s,c)
    asyncio.run(w.reconcile(s.job(j['id'])))
    assert s.job(j['id'])['state']=='submission_uncertain'
    assert c.submitted==0
    w.lock.close()

def test_restart_reconciles_oom_and_face_failure(tmp_path):
    s=Store(tmp_path);c=FakeComfy();w=Worker(s,c)
    for i,message,state in [('1','CUDA out of memory','failed'),('2','AIGC_FACE_SELECTION: no face','needs_correction')]:
        j=s.create_job({'idempotency_key':i});s.update_job(j['id'],state='running',prompt_id=i)
        c.result={i:{'status':{'status_str':'error','messages':[message]}}}
        asyncio.run(w.reconcile(Store(tmp_path).job(j['id'])))
        assert s.job(j['id'])['state']==state
        assert message in s.job(j['id'])['error']
    w.lock.close()

def test_disconnection_keeps_recoverable_state(tmp_path):
    class Offline(FakeComfy):
        async def history(self,id):raise httpx.ConnectError('offline')
    s=Store(tmp_path);j=s.create_job({'idempotency_key':'a'});s.update_job(j['id'],state='running',prompt_id='p')
    w=Worker(s,Offline());asyncio.run(w.reconcile(s.job(j['id'])))
    assert s.job(j['id'])['state']=='recovering';assert s.job(j['id'])['prompt_id']=='p';w.lock.close()

def test_exact_mask_boundary_and_canvas():
    path=Path(__file__).parents[1]/'custom_nodes/AIGC_LocalEdit/composite.py'
    spec=importlib.util.spec_from_file_location('composite',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    original=Image.new('RGB',(37,51),(17,32,203));before=original.tobytes()
    edited=Image.new('RGB',(9,13),'red');mask=Image.new('L',original.size)
    mask.paste(128,(11,15,19,22));out=m.masked_paste(original,edited,mask,(5,10,30,40))
    assert out.size==original.size;assert original.tobytes()==before
    for y in range(51):
        for x in range(37):
            if mask.getpixel((x,y))==0:assert out.getpixel((x,y))==original.getpixel((x,y))
    assert out.getpixel((12,16))!=original.getpixel((12,16))

def test_llm_one_correction(monkeypatch):
    responses=['not JSON',json.dumps({'asset_type':'background','description':'An empty library.'})];calls=[]
    async def handler(request):
        calls.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'content':responses.pop(0)}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    for k,v in [('ENDPOINT','https://example.invalid/v1'),('MODEL','test-model'),('API_KEY','test-secret')]:monkeypatch.setenv('AIGC_LLM_'+k,v)
    spec,meta=asyncio.run(llm.parse_scene(SceneRequest(story='空图书馆',asset_type='background'),None))
    assert spec.description=='An empty library.';assert meta['attempts']==2;assert len(calls)==2
    assert 'test-secret' not in json.dumps(calls)


def test_llm_stops_after_second_invalid_output(monkeypatch):
    calls=[]
    async def handler(request):calls.append(1);return httpx.Response(200,json={'choices':[{'message':{'content':'invalid'}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    for k,v in [('ENDPOINT','https://example.invalid/v1'),('MODEL','test'),('API_KEY','fake')]:monkeypatch.setenv('AIGC_LLM_'+k,v)
    with pytest.raises(ValueError,match='after correction'):asyncio.run(llm.parse_scene(SceneRequest(story='空房间',asset_type='background'),None))
    assert len(calls)==2

def test_all_save_outputs_collected_once_after_restart(tmp_path):
    from io import BytesIO
    s=Store(tmp_path);spec=s.put('scene_spec',{'spec':{'asset_type':'matte'}})
    j=s.create_job({'idempotency_key':'one','scene_spec_id':spec['id']});s.update_job(j['id'],state='running',prompt_id='p')
    s.put('execution',{'output_nodes':{'3':'transparent','4':'mask'},'started':0},j['id'])
    out=BytesIO();Image.new('RGBA',(8,8),(2,3,4,123)).save(out,format='PNG')
    class Done(FakeComfy):
        async def download(self,entry):return out.getvalue()
    c=Done();c.result={'p':{'status':{'completed':True,'status_str':'success'},'outputs':{'3':{'images':[{'filename':'alpha.png','type':'output'}]},'4':{'images':[{'filename':'mask.png','type':'output'}]}}}}
    w=Worker(s,c);asyncio.run(w.reconcile(s.job(j['id'])));first=s.job(j['id'])['outputs']
    assert len(first)==2
    s.update_job(j['id'],state='running');asyncio.run(w.reconcile(s.job(j['id'])))
    assert s.job(j['id'])['outputs']==first;assert len(s.list('asset'))==2;w.lock.close()

def test_api_rejects_unknown_character_and_unapproved_reference(tmp_path,monkeypatch):
    monkeypatch.setenv('AIGC_DATA_DIR',str(tmp_path))
    from aigc import api
    from aigc.schema import Character,JobRequest
    from aigc.assets import save_image
    from fastapi import HTTPException
    from io import BytesIO
    monkeypatch.setattr(api,'store',Store(tmp_path))
    with pytest.raises(HTTPException) as err:api.validate_spec(SceneSpec(asset_type='sprite',character_id='missing'))
    assert err.value.status_code==404
    asyncio.run(api.create_character(Character(id='a',name='A',fixed_tags=['silver hair'])))
    spec=asyncio.run(api.scene_specs(SceneRequest(manual=SceneSpec(asset_type='expression',character_id='a',expression='smile'))))
    blob=BytesIO();Image.new('RGB',(16,16)).save(blob,format='PNG');a=save_image(api.store,blob.getvalue(),{'role':'reference'})
    with pytest.raises(HTTPException) as err:asyncio.run(api.create_job(JobRequest(scene_spec_id=spec['id'],reference_asset_id=a['id'],idempotency_key='one')))
    assert err.value.status_code==422;assert not api.store.jobs()

def test_expression_ingestion_rejects_outside_mask_change(tmp_path):
    from io import BytesIO
    from aigc.assets import save_image,asset_path
    def png(color,mode='RGB'):
        b=BytesIO();Image.new(mode,(8,8),color).save(b,format='PNG');return b.getvalue()
    s=Store(tmp_path);a=save_image(s,png('blue'),{'role':'reference'});before=asset_path(s,a).read_bytes()
    spec=s.put('scene_spec',{'spec':{'asset_type':'expression'}})
    j=s.create_job({'idempotency_key':'expr','scene_spec_id':spec['id'],'reference_asset_id':a['id']});s.update_job(j['id'],state='running',prompt_id='p')
    s.put('execution',{'output_nodes':{'1':'original','2':'mask'},'started':0},j['id'])
    class Done(FakeComfy):
        async def download(self,entry):return png('red') if entry['filename']=='edited' else png(0,'L')
    c=Done();c.result={'p':{'status':{'completed':True,'status_str':'success'},'outputs':{'1':{'images':[{'filename':'edited','type':'output'}]},'2':{'images':[{'filename':'mask','type':'output'}]}}}}
    w=Worker(s,c);asyncio.run(w.reconcile(s.job(j['id'])))
    assert s.job(j['id'])['state']=='failed';assert len(s.job(j['id'])['outputs'])==2
    assert s.get('validation',j['id'])['outside_mask_unchanged'] is False
    assert asset_path(s,a).read_bytes()==before;w.lock.close()
