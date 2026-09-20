"""Execute one prepared inspection graph without writing production approvals.

Stores submission intent before submitting; uncertain submissions are reconciled,
never replayed. Invoke separately for each explicitly selected test stage.
"""
from _config import API_URL, COMFY_URL, DATA_DIR
import argparse, asyncio, fcntl, hashlib, json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aigc.comfy import Comfy

async def run(root, stage):
    graph=json.loads((root/f'{stage}.api.json').read_text())
    path=root/f'{stage}.run.json'
    digest=hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest()
    record=json.loads(path.read_text()) if path.exists() else dict(job_key=root.name+'-'+stage,graph_sha256=digest)
    if record['graph_sha256']!=digest:raise ValueError('Graph changed; use a new stage name')
    def save():
        part=path.with_suffix('.part');part.write_text(json.dumps(record,indent=2));part.replace(path)
    if record.get('status')=='complete':
        for f,h in record['files'].items():assert hashlib.sha256((root/f).read_bytes()).hexdigest()==h
        print('Already complete');return
    c=Comfy(COMFY_URL)
    try:
        pid=record.get('prompt_id')
        if not pid and record.get('submit_started'):
            pid=await c.locate(record['job_key'])
            if not pid:raise RuntimeError('Uncertain submission; inspect queue/history, do not retry')
        if not pid:
            q=await c.queue()
            if q['queue_running'] or q['queue_pending']:raise RuntimeError('Queue busy; not submitted')
            record.update(status='submitting',submit_started=time.time());save()
            pid=await c.submit(graph,record['job_key'])
        record.update(prompt_id=pid,status='running');save();print(stage,pid,flush=True)
        while True:
            h=(await c.history(pid)).get(pid)
            if h and h.get('status',{}).get('status_str')=='error':
                record.update(status='failed');save();(root/f'{stage}.history.json').write_text(json.dumps(h,indent=2));raise RuntimeError('Execution failed; inspect history')
            if h and h.get('status',{}).get('completed'):
                assert h['status']['status_str']=='success'
                files={}
                for node,out in h.get('outputs',{}).items():
                    for i,img in enumerate(out.get('images',[])):
                        if img.get('type')!='output':continue
                        blob=await c.download(img);name=f'{stage}-{node}-{i}.png'
                        (root/name).write_bytes(blob);files[name]=hashlib.sha256(blob).hexdigest()
                assert files
                (root/f'{stage}.history.json').write_text(json.dumps(h,indent=2))
                record.update(status='complete',files=files,elapsed_seconds=time.time()-record['submit_started']);save()
                print(stage,'complete',record['elapsed_seconds'],flush=True);return
            await asyncio.sleep(3)
    finally:await c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('stage');a=p.parse_args()
    if not a.stage.replace('-','').isalnum():raise ValueError('Invalid stage')
    with (a.directory/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        asyncio.run(run(a.directory,a.stage))
