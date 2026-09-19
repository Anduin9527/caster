import hashlib
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from aigc.store import Store
from aigc import pose_studio_presets as poses


def test_materialization_uses_exact_state_and_render_without_jobs(tmp_path,monkeypatch):
    store=Store(tmp_path)
    entry=dict(poses.ITEMS[101])
    state=b'{"bones":{"pelvis":[1,2,3]}}'
    stream=io.BytesIO(); Image.new('RGB',(1024,1024),'white').save(stream,format='PNG')
    blob=stream.getvalue()
    entry.update(json_sha256=hashlib.sha256(state).hexdigest(),render_sha256=hashlib.sha256(blob).hexdigest())
    monkeypatch.setitem(poses.ITEMS,101,entry)
    root=tmp_path/'pose-studio-library'
    (root/entry['json_path']).parent.mkdir(parents=True)
    (root/entry['json_path']).write_bytes(state)
    (root/'renders').mkdir()
    (root/'renders/101.png').write_bytes(blob)
    before=(store.jobs(),store.list('approval'))
    first=poses.materialize(store,101)
    assert poses.materialize(store,101)==first
    assert first['state']['pose']==json.loads(state)
    assert (store.jobs(),store.list('approval'))==before
    asset=store.get('asset',first['render_asset_id'])
    assert asset['role']=='pose_render' and asset['mode']=='RGB'
    assert (tmp_path/'files'/asset['path']).read_bytes()==blob
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aigc.production import production_router
    app=FastAPI();app.include_router(production_router(lambda:store))
    client=TestClient(app)
    response=client.post('/production/pose-presets/101')
    assert response.status_code==201 and response.json()==first
    response=client.get('/production/pose-presets/101/image')
    assert response.status_code==200 and response.content==blob
    assert len(client.get('/production/pose-presets').json())==16
    assert client.get('/production/pose-presets/999/image').status_code==404
    assert (store.jobs(),store.list('approval'))==before
    (root/'renders/101.png').write_bytes(b'corrupt')
    with pytest.raises(LookupError,match='checksum'):poses.render(store,101)
    with pytest.raises(LookupError):poses.render(store,999)
