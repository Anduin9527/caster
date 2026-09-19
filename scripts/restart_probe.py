"""Real queue recovery experiment: restart API while owned Comfy prompt runs."""
import json,time,subprocess
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1];c=httpx.Client(base_url='http://127.0.0.1:8189',timeout=10)
def post(route,d):r=c.post(route,json=d);r.raise_for_status();return r.json()
s=post('/scene-specs',{'manual':{'asset_type':'background','scene':'An empty moonlit garden with stone paths, trees and a fountain.','composition':'wide shot','description':'Anime visual novel background.'}})
j=post('/jobs',{'scene_spec_id':s['id'],'seed':9631,'idempotency_key':'restart-recovery-probe-v1'})
start=time.time();observations=[]
while time.time()-start<30:
 j=c.get('/jobs/'+j['id']).json()
 if j['prompt_id']:
  q=httpx.get('http://127.0.0.1:8188/queue').json()
  if any(x[1]==j['prompt_id'] for x in q['queue_running']):break
 time.sleep(.5)
else:raise RuntimeError('No running prompt observed; restart experiment not performed')
pid=j['prompt_id'];before=j
subprocess.run([str(root/'.venv/bin/python'),str(root/'scripts/service.py'),'stop'],check=True)
subprocess.run([str(root/'.venv/bin/python'),str(root/'scripts/service.py'),'start'],check=True)
while time.time()-start<180:
 j=c.get('/jobs/'+j['id']).json()
 observations.append({'at':time.time(),'state':j['state'],'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free','--format=csv,noheader'],text=True)})
 if j['state'] in ('succeeded','failed','submission_uncertain'):break
 time.sleep(2)
h=httpx.get('http://127.0.0.1:8188/history').json()
matching=[p for p,v in h.items() if len(v.get('prompt',[]))>3 and v['prompt'][3].get('aigc_job_id')==j['id']]
report={'before_restart':{k:before[k] for k in ['id','state','prompt_id']},'after_restart':{k:j[k] for k in ['id','state','prompt_id','outputs','error']},'same_prompt_id':pid==j['prompt_id'],'matching_history_count':len(matching),'observations':observations}
(root/'restart-recovery.json').write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k!='observations'})
assert j['state']=='succeeded' and pid==j['prompt_id'] and len(matching)==1
