"""Resume acceptance from persisted approvals; never implicitly approve references."""
import json,httpx
from pathlib import Path
root=Path(__file__).resolve().parents[1]
c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=30)
def post(route,body):
 r=c.post(route,json=body);r.raise_for_status();return r.json()
existing={j['idempotency_key']:j for j in c.get('/jobs').json()}
approvals=c.get('/approvals').json();assets={a['id']:a for a in c.get('/assets').json()}
submitted=[];blocked=[]
def job(key,spec,**inputs):
 if key in existing:return existing[key]
 s=post('/scene-specs',{'manual':spec})
 j=post('/jobs',dict(scene_spec_id=s['id'],idempotency_key=key,seed=9751,**inputs));existing[key]=j;submitted.append(j['id']);return j
for ch,outfit in [('demo-a','navy'),('demo-b','casual')]:
 refs=[a for a in approvals if a['character_id']==ch and a['kind']=='character']
 if not refs:blocked.append(ch+': character approval missing');continue
 # Approved neutral poses are the only sources for expression branches.
 poses=[a for a in approvals if a['character_id']==ch and a['kind']=='pose']
 if len(poses)<3:blocked.append(ch+': fewer than 3 approved neutral poses')
 for pose in poses:
  for expression in ['a gentle happy smile','a surprised expression with raised eyebrows','an angry frown']:
   label={'a gentle happy smile':'happy','a surprised expression with raised eyebrows':'surprised','an angry frown':'angry'}[expression]
   key=f'acceptance-{ch}-{pose["asset_id"]}-{label}-v1'
   j=job(key,{'asset_type':'expression','character_id':ch,'outfit_id':outfit,'expression':expression},reference_asset_id=pose['asset_id'])
   if j['state']=='succeeded':
    source=next(assets[a] for a in j['outputs'] if assets[a]['role']=='original')
    job(key+'-alpha',{'asset_type':'matte','character_id':ch,'outfit_id':outfit},reference_asset_id=source['id'])
# Matting does not promote a result to a character or pose baseline.
for ch,outfit in [('demo-a','navy'),('demo-b','casual')]:
 for key,j in list(existing.items()):
  if key in {f'{ch}-pose-{i}-v1' for i in (1,2,3)} and j['state']=='succeeded':
   source=next(assets[a] for a in j['outputs'] if assets[a]['role']=='original')
   job(key+'-alpha',{'asset_type':'matte','character_id':ch,'outfit_id':outfit},reference_asset_id=source['id'])
report={'submitted':submitted,'blocked':blocked}
(root/'continuation-status.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,ensure_ascii=False))
