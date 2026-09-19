"""Read model for the production workbench; never starts or submits inference."""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from . import pose_presets, pose_studio_presets
from pydantic import Field
from .schema import Outfit
from .workbench import SelectionRequest, BatchRequest, Conflict, get_selection, select_image, create_batch, ReviewRequest, review_image


class OutfitVersion(Outfit):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


def production_router(get_store, get_comfy=None):
    router = APIRouter(prefix='/production', tags=['production'])

    @router.get('/capabilities')
    async def capabilities():
        online = False
        if get_comfy:
            try:
                response = await get_comfy().client.get('/queue', timeout=2)
                response.raise_for_status()
                online = True
            except Exception:
                pass
        return {'selection': True, 'batches': True, 'outfit_versions': True,
                'generation_online': online, 'pose_input': 'pose_studio_3d'}

    @router.get('/snapshot')
    def snapshot(character_id: str | None = None):
        store = get_store()
        # One SQLite read transaction prevents jobs, outputs and approvals from
        # being read at different moments while the worker ingests results.
        with store.connect() as db:
            db.execute('BEGIN')
            def records(kind, preserve_id=False):
                rows = db.execute('SELECT id,body FROM records WHERE kind=? ORDER BY rowid', (kind,)).fetchall()
                return {r['id']: (json.loads(r['body']) if preserve_id else dict(json.loads(r['body']), id=r['id'])) for r in rows}
            characters = records('character')
            if character_id is not None and character_id not in characters:
                raise HTTPException(404, 'Unknown character')
            specs = records('scene_spec')
            approvals = list(records('approval').values())
            assets = records('asset')
            poses = records('pose')
            selections = list(records('selection').values())
            reviews = list(records('asset_review').values())
            batches = list(records('production_batch').values())
            versions = list(records('outfit_version', preserve_id=True).values())
            jobs = [store.decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC').fetchall()]

        def spec_for(spec_id):
            return specs.get(spec_id, {}).get('spec', {})
        jobs = [dict(j, spec=spec_for(j['body'].get('scene_spec_id'))) for j in jobs]
        if character_id is not None:
            jobs = [j for j in jobs if j['spec'].get('character_id') == character_id]
            approvals = [a for a in approvals if a['character_id'] == character_id]
        asset_ids = {a for j in jobs for a in (j['outputs'] or [])}
        asset_ids.update(j['body'].get('reference_asset_id') for j in jobs)
        asset_ids.update(a['asset_id'] for a in approvals)
        pose_ids = {j['body'].get('pose_asset_id') for j in jobs}
        chosen_poses = list(poses.values())
        asset_ids.update(p['render_asset_id'] for p in chosen_poses)
        compact_assets = []
        for a in assets.values():
            spec = spec_for(a.get('scene_spec_id'))
            if character_id is not None and a['id'] not in asset_ids and spec.get('character_id') != character_id:
                continue
            # Do not resend embedded node graphs, model inventories or paths on
            # every progress poll. Full provenance stays at /jobs/{id}/record.
            item = {k: a[k] for k in ('id', 'role', 'job_id', 'parent_asset_id', 'scene_spec_id', 'width', 'height', 'mode', 'sha256', 'created') if k in a}
            item['download_url'] = '/assets/' + a['id'] + '/file'
            item['spec'] = spec
            compact_assets.append(item)
        return {'schema_version': 1,
                'characters': [c for c in characters.values() if character_id is None or c['id'] == character_id],
                'jobs': jobs, 'assets': compact_assets, 'approvals': approvals,
                'reviews': [v for v in reviews if character_id is None or v['character_id'] == character_id],
                'selections': [v for v in selections if character_id is None or v['character_id'] == character_id],
                'batches': [v for v in batches if character_id is None or v['character_id'] == character_id],
                'outfit_versions': [v for v in versions if character_id is None or v['character_id'] == character_id],
                'poses': [{k: p[k] for k in ('id', 'render_asset_id', 'lighting_prompt', 'preset_id') if k in p} for p in chosen_poses]}
    @router.post('/characters/{character_id}/outfits', status_code=201)
    def create_outfit(character_id: str, body: OutfitVersion):
        try:
            return get_store().append_outfit(character_id, body.model_dump(exclude={'name','parent_id'}), body.name, body.parent_id)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))
    def invoke(operation, *args):
        try: return operation(get_store(), *args)
        except LookupError as e: raise HTTPException(404, str(e))
        except Conflict as e: raise HTTPException(409, str(e))
        except ValueError as e: raise HTTPException(422, str(e))

    @router.get('/characters/{character_id}/selection')
    def read_selection(character_id: str):
        return invoke(get_selection, character_id)

    @router.put('/characters/{character_id}/selection')
    def update_selection(character_id: str, body: SelectionRequest):
        return invoke(select_image, character_id, body)

    @router.post('/characters/{character_id}/batches', status_code=201)
    def submit_batch(character_id: str, body: BatchRequest):
        return invoke(create_batch, character_id, body)
    @router.put('/characters/{character_id}/assets/{asset_id}/review')
    def review(character_id: str, asset_id: str, body: ReviewRequest):
        return invoke(review_image, character_id, asset_id, body)

    @router.get('/characters/{character_id}/manifest')
    def manifest(character_id: str):
        return JSONResponse(snapshot(character_id), headers={'Content-Disposition': 'attachment; filename="caster-assets.json"'})
    @router.get('/pose-presets')
    def list_presets(): return pose_studio_presets.catalog()

    @router.get('/pose-presets/{index}/image')
    def preset_image(index: int, width: int | None = None, height: int | None = None):
        try:
            blob = pose_studio_presets.render(get_store(), index, width, height) if index >= 101 else pose_presets.render(index)
            return Response(blob, media_type='image/png', headers={'Cache-Control':'public, max-age=86400'})
        except LookupError as e: raise HTTPException(404, str(e))
        except ValueError as e: raise HTTPException(422, str(e))

    @router.post('/pose-presets/{index}', status_code=201)
    def save_preset(index: int, width: int | None = None, height: int | None = None):
        if index >= 101:return invoke(pose_studio_presets.materialize,index,width,height)
        return invoke(pose_presets.materialize,index)
    return router
