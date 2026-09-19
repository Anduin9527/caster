import asyncio
from io import BytesIO
import httpx
from PIL import Image
from fastapi import FastAPI
from aigc.store import Store
from aigc.template_api import template_router


def test_template_paging_cache_revalidates_after_edit(tmp_path):
    store = Store(tmp_path)
    for i in range(15):
        store.put('prompt_template', {'kind': 'character', 'name': f'角色{i}', 'tags': ['blue'], 'categories': ['作品'], 'source': 'upstream'}, str(i))
    store.put('prompt_template', {'kind': 'character', 'name': '个人', 'tags': ['green'], 'categories': [], 'source': 'user'}, 'mine')
    app = FastAPI()
    app.include_router(template_router(lambda: store))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            url='/prompt-templates?kind=character&source=upstream&limit=12'
            first=await c.get(url)
            assert len(first.json()['items']) == 12
            assert first.json()['total'] == 15
            assert first.json()['categories'] == ['作品']
            assert (await c.get(url, headers={'If-None-Match': first.headers['etag']})).status_code == 304
            assert len((await c.get(url+'&offset=12')).json()['items']) == 3
            assert (await c.get(url+'&q=角色14')).json()['total'] == 1
            assert (await c.get('/prompt-templates?source=user')).json()['total'] == 1
            store.put('prompt_template', {'kind':'character', 'name':'更新', 'tags':['red'], 'categories':['作品'], 'source':'upstream'}, '0', replace=True)
            updated=await c.get(url,headers={'If-None-Match':first.headers['etag']})
            assert updated.status_code==200
            assert updated.headers['etag']!=first.headers['etag']
    asyncio.run(check())


def test_thumbnail_preserves_alpha_original_and_cache(tmp_path, monkeypatch):
    import aigc.api as api
    from aigc.assets import save_image, asset_path
    store=Store(tmp_path)
    monkeypatch.setattr(api, 'store', store)
    output=BytesIO()
    Image.new('RGBA',(832,1216),(100,50,20,0)).save(output,format='PNG')
    asset=save_image(store,output.getvalue(),{'role':'transparent'})
    before=asset_path(store,asset).read_bytes()
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://test') as c:
            url=f'/assets/{asset["id"]}/thumbnail'
            r=await c.get(url)
            assert r.status_code==200 and r.headers['content-type']=='image/webp'
            image=Image.open(BytesIO(r.content))
            assert image.size==(263,384) and image.mode=='RGBA'
            assert image.getpixel((0,0))[3]==0
            assert 'immutable' in r.headers['cache-control']
            assert (await c.get(url,headers={'If-None-Match':r.headers['etag']})).status_code==304
            assert (await c.get('/assets/missing/thumbnail')).status_code==404
            assert (await c.get(f'/assets/{asset["id"]}/file')).content==before
    asyncio.run(check())
    assert asset_path(store,asset).read_bytes()==before
