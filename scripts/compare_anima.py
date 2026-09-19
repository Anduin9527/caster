"""Run a prepared two-graph comparison serially, recording intent before submit.

All files live under the specified project data directory. Uncertain submissions
are reconciled by their saved unique job key; never automatically replayed.
"""
import argparse,asyncio,fcntl,hashlib,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aigc.comfy import Comfy

async def run(root):
    root=root.resolve()
    comfy=Comfy('http://127.0.0.1:8188')
    try:
        for name in ('before','after'):
            path=root/(name+'.run.json')
            graph=json.loads((root/(name+'.api.json')).read_text())
            digest=hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest()
            record=json.loads(path.read_text()) if path.exists() else {'job_key':root.name+'-'+name,'graph_sha256':digest}
            if record['graph_sha256']!=digest:raise RuntimeError('Comparison graph changed; use a new run directory')
            def save():
                part=path.with_suffix('.part');part.write_text(json.dumps(record,indent=2));part.replace(path)
            if record.get('status')=='complete':
                assert hashlib.sha256((root/(name+'.png')).read_bytes()).hexdigest()==record['image_sha256']
                continue
            pid=record.get('prompt_id')
            if not pid and record.get('submit_started'):
                pid=await comfy.locate(record['job_key'])
                if not pid:raise RuntimeError('Uncertain submission; inspect queue/history before manual recovery')
            if not pid:
                while True:
                    queue = await comfy.queue()
                    if not queue.get('queue_running') and not queue.get('queue_pending'): break
                    await asyncio.sleep(3)
                record.update(submit_started=time.time(),status='submitting');save()
                pid=await comfy.submit(graph,record['job_key'])
            record.update(prompt_id=pid,status='running');save()
            print(name,pid,flush=True)
            while True:
                history=(await comfy.history(pid)).get(pid)
                if history and history.get('status',{}).get('completed'):
                    if history['status'].get('status_str')!='success':
                        record.update(status='failed',history=history);save();raise RuntimeError(name+' failed')
                    entry=history['outputs']['9']['images'][0]
                    blob=await comfy.download(entry)
                    (root/(name+'.png')).write_bytes(blob)
                    (root/(name+'.history.json')).write_text(json.dumps(history,indent=2))
                    record.update(status='complete',image_sha256=hashlib.sha256(blob).hexdigest(),elapsed_seconds=time.time()-record['submit_started'],output=entry)
                    save(); print(name,'complete',round(record['elapsed_seconds'],1),flush=True);break
                if history and history.get('status',{}).get('status_str')=='error':
                    record.update(status='failed',history=history);save();raise RuntimeError(name+' execution error')
                await asyncio.sleep(3)
    finally:await comfy.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    with (args.directory/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        asyncio.run(run(args.directory))
