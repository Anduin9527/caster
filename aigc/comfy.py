import asyncio,json,hashlib
import httpx,websockets

class Comfy:
    def __init__(self,url):self.url=url.rstrip('/');self.client=httpx.AsyncClient(base_url=self.url,timeout=30)
    async def close(self):await self.client.aclose()
    async def info(self):
        r=await self.client.get('/object_info');r.raise_for_status();return r.json()
    async def history(self,pid=None):
        r=await self.client.get('/history'+('/'+pid if pid else ''));r.raise_for_status();return r.json()
    async def queue(self):
        r=await self.client.get('/queue');r.raise_for_status();return r.json()
    async def locate(self,job_id):
        hist=await self.history()
        for pid,item in hist.items():
            p=item.get('prompt',[])
            if len(p)>3 and p[3].get('aigc_job_id')==job_id:return pid
        q=await self.queue()
        for p in q.get('queue_running',[])+q.get('queue_pending',[]):
            if len(p)>3 and p[3].get('aigc_job_id')==job_id:return p[1]
        return None
    async def submit(self,graph,job_id):
        r=await self.client.post('/prompt',json={'prompt':graph,'client_id':'aigc-'+job_id,'extra_data':{'aigc_job_id':job_id}})
        if r.status_code==400:raise ValueError('Workflow validation failed: '+r.text[:4000])
        r.raise_for_status();return r.json()['prompt_id']
    async def upload(self,path):
        name=hashlib.sha256(path.read_bytes()).hexdigest()+'.png'
        with path.open('rb') as f:r=await self.client.post('/upload/image',files={'image':(name,f,'image/png')},data={'type':'input','subfolder':'aigc','overwrite':'false'})
        r.raise_for_status();d=r.json();return (d.get('subfolder','')+'/'+d['name']).lstrip('/')
    async def download(self,entry):
        if entry.get('type')!='output':raise ValueError('Refusing preview/temp output')
        r=await self.client.get('/view',params=entry);r.raise_for_status();return r.content
    async def progress(self,job_id,callback):
        url=self.url.replace('http://','ws://').replace('https://','wss://')+'/ws?clientId=aigc-'+job_id
        try:
            async with websockets.connect(url,max_size=4*1024*1024) as ws:
                async for msg in ws:
                    if not isinstance(msg,str):continue
                    event=json.loads(msg)
                    if event.get('type') in ('progress','executing','execution_error'):callback(event)
        except (OSError,websockets.WebSocketException):return
    async def cancel_pending(self,pid):
        q=await self.queue()
        if any(x[1]==pid for x in q.get('queue_pending',[])):
            r=await self.client.post('/queue',json={'delete':[pid]});r.raise_for_status()
            after=await self.queue()
            if any(x[1]==pid for x in after.get('queue_running',[])+after.get('queue_pending',[])):return False
            return pid not in await self.history(pid)
        return False
