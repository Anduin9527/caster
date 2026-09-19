import asyncio
from io import BytesIO
import httpx
from PIL import Image
from fastapi import FastAPI
from aigc.store import Store
from aigc.templates import HUB_REPO, HUB_REVISION
from aigc.template_previews import fetch_preview, cache_path, source_url
from aigc.template_api import template_router


def test_download_resume_and_local_image_route(tmp_path):
    store=Store(tmp_path)
    t=store.put('prompt_template',{'kind':'character','source':HUB_REPO,'source_revision':HUB_REVISION,'source_key':'yamazaki sousuke||free!'},'hero')
    assert source_url(t)=='https://blobs.animadex.net/Outputs/thumbs/yamazaki%20sousuke%2C%20free!.webp'
    assert source_url(dict(t,source='user')) is None
    calls=[]
    output=BytesIO(); Image.new('RGB',(600,900),'blue').save(output,format='PNG')
    def serve(request):
        calls.append(request.url)
        return httpx.Response(200,content=output.getvalue(),headers={'content-type':'image/png'})
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        assert fetch_preview(store,t,client)['status']=='downloaded'
        assert fetch_preview(store,t,client)['status']=='cached'
    assert len(calls)==1
    path=cache_path(store,t)
    assert Image.open(path).size==(256,384)
    app=FastAPI(); app.include_router(template_router(lambda:store))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            r=await client.get('/prompt-templates/hero/image')
            assert r.status_code==200 and r.content==path.read_bytes()
            assert (await client.get('/prompt-templates/hero/image',headers={'If-None-Match':r.headers['etag']})).status_code==304
            assert (await client.get('/prompt-templates/missing/image')).headers['cache-control']=='no-store'
    asyncio.run(check())
    assert store.list('approval')==[] and store.jobs()==[]


def test_invalid_upstream_does_not_poison_cache(tmp_path):
    store=Store(tmp_path)
    t={'id':'a','kind':'character','source':HUB_REPO,'source_revision':HUB_REVISION,'source_key':'a||b'}
    import pytest
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'html',headers={'content-type':'text/html'}))) as client:
        with pytest.raises(ValueError,match='non-image'):fetch_preview(store,t,client)
    assert not cache_path(store,t).exists()
