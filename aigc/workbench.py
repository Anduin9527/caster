"""Transactional selection and candidate batches for the production workbench."""
import hashlib
import json
import time
import uuid
from typing import Literal
from pydantic import Field
from .schema import Strict, SceneSpec, JobRequest


class Conflict(ValueError):
    pass


class SelectionRequest(Strict):
    expected_revision: int = Field(ge=0)
    stage: Literal['identity', 'outfit', 'pose']
    asset_id: str
    approve: bool = False


class Candidate(Strict):
    asset_id: str | None = None
    face_region: tuple[int, int, int, int] | None = None
    outfit_id: str | None = None
    pose_id: str | None = None
    expression: str = Field(default='', max_length=2000)
    seed: int = Field(default=9527, ge=0, le=2**63-1)


class BatchRequest(Strict):
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)
    role: Literal['identity', 'outfit', 'pose', 'expression', 'matte']
    candidates: list[Candidate] = Field(min_length=1, max_length=36)
    retry_of: str | None = None
    canvas_preset: str | None = None


def empty_selection(character_id):
    return dict(character_id=character_id, revision=0, identity_asset_id=None,
                outfit_asset_id=None, outfit_id=None, pose_asset_id=None)


class Transaction:
    def __init__(self, db):
        self.db = db

    def get(self, kind, id, required=True):
        row = self.db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, id)).fetchone()
        if row is None:
            if required: raise LookupError('Unknown ' + kind)
            return None
        return dict(json.loads(row['body']), id=id)

    def put(self, kind, id, value, replace=False):
        self.db.execute(('INSERT OR REPLACE' if replace else 'INSERT') + ' INTO records VALUES(?,?,?)',
                        (kind, id, json.dumps(value, ensure_ascii=False)))

    def selection(self, character_id):
        self.get('character', character_id)
        value = self.get('selection', character_id, False) or empty_selection(character_id)
        return {k: v for k, v in value.items() if k != 'id'}

    def approved(self, asset_id, kind, character_id, outfit_id):
        for row in self.db.execute("SELECT body FROM records WHERE kind='approval'"):
            a = json.loads(row['body'])
            if (a['asset_id'], a['kind'], a['character_id'], a.get('outfit_id')) == (asset_id, kind, character_id, outfit_id):
                return True
        return False

    def image(self, asset_id, character_id):
        asset = self.get('asset', asset_id)
        if asset.get('mode') != 'RGB' or asset.get('role') not in ('original', 'reference'):
            raise ValueError('Select an original RGB image')
        spec = self.get('scene_spec', asset['scene_spec_id'])['spec'] if asset.get('scene_spec_id') else {}
        if spec and spec.get('character_id') != character_id:
            raise ValueError('Image belongs to another character')
        if asset.get('job_id'):
            job = self.db.execute('SELECT state,outputs FROM jobs WHERE id=?', (asset['job_id'],)).fetchone()
            if not job or job['state'] != 'succeeded' or asset_id not in json.loads(job['outputs']):
                raise ValueError('Image is not a successful task output')
        return asset, spec


def get_selection(store, character_id):
    with store.connect() as db:
        db.execute('BEGIN')
        return Transaction(db).selection(character_id)


def select_image(store, character_id, request: SelectionRequest):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        tx = Transaction(db)
        current = tx.selection(character_id)
        if current['revision'] != request.expected_revision:
            raise Conflict('Selection changed; refresh before selecting')
        asset, spec = tx.image(request.asset_id, character_id)
        outfit_id = spec.get('outfit_id')
        kind = {'identity': 'character', 'outfit': 'outfit', 'pose': 'pose'}[request.stage]
        if request.stage == 'identity':
            if spec and spec['asset_type'] != 'sprite': raise ValueError('Identity requires a character image')
        elif request.stage == 'outfit':
            if not current['identity_asset_id']: raise ValueError('Select an identity first')
            # Previously approved clothed identities remain usable as the initial
            # outfit. This is an explicit choice, never an automatic migration.
            if request.asset_id == current['identity_asset_id']:
                kind = 'character'
            elif spec.get('asset_type') != 'outfit' or asset.get('parent_asset_id') != current['identity_asset_id']:
                raise ValueError('Outfit must derive from the selected identity')
            if not outfit_id: raise ValueError('Image has no outfit version')
        else:
            if not current['outfit_asset_id']: raise ValueError('Select an outfit image first')
            if spec.get('asset_type') != 'pose' or outfit_id != current['outfit_id'] or asset.get('parent_asset_id') != current['outfit_asset_id']:
                raise ValueError('Pose must derive from the selected outfit image')
        approved = tx.approved(asset['id'], kind, character_id, outfit_id)
        if not approved:
            if not request.approve: raise ValueError('Explicit approval required')
            if not spec or not asset.get('job_id'): raise ValueError('New approval requires a successful generated result')
            tx.put('approval', uuid.uuid4().hex, dict(asset_id=asset['id'], kind=kind, character_id=character_id, outfit_id=outfit_id, note='Explicit workbench image selection'))
        field = request.stage + '_asset_id'
        if current[field] == asset['id']: return current
        selected = dict(current, **{field: asset['id']}, revision=current['revision'] + 1)
        if request.stage == 'identity':
            selected.update(outfit_asset_id=None, outfit_id=None, pose_asset_id=None)
        if request.stage == 'outfit':
            selected.update(outfit_id=outfit_id, pose_asset_id=None)
        tx.put('selection', character_id, selected, replace=True)
        tx.put('selection_history', character_id + ':' + str(selected['revision']), selected)
        return selected


def create_batch(store, character_id, request: BatchRequest):
    if request.canvas_preset is not None:
        from .canvas import preset_size
        preset_size(request.canvas_preset)
        if request.role != 'identity':raise ValueError('Downstream canvas follows the selected source image')
    body = request.model_dump(exclude={'canvas_preset'} if request.canvas_preset is None else set())
    key = hashlib.sha256((character_id + ':' + request.idempotency_key).encode()).hexdigest()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        tx = Transaction(db)
        existing = tx.get('production_batch', key, False)
        if existing:
            if existing['request'] != body: raise Conflict('Batch key already used for another request')
            return existing
        current = tx.selection(character_id)
        if current['revision'] != request.expected_revision: raise Conflict('Selection changed; refresh before generating')
        character = tx.get('character', character_id)
        outfits = {o['id'] for o in character['outfits']}
        source = {'identity': None, 'outfit': current['identity_asset_id'], 'pose': current['outfit_asset_id'], 'expression': current['pose_asset_id'], 'matte': None}[request.role]
        if request.role not in ('identity', 'matte') and not source: raise ValueError('Select the required source image first')
        if source:
            _, source_spec = tx.image(source, character_id)
            source_outfit = source_spec.get('outfit_id')
            kinds = ('character',) if request.role == 'outfit' else ('pose',) if request.role == 'expression' else ('character', 'outfit')
            if not any(tx.approved(source, kind, character_id, source_outfit) for kind in kinds):
                raise ValueError('Source image is no longer approved')
        if request.retry_of:
            old = tx.get('production_batch', request.retry_of)
            if old['character_id'] != character_id: raise ValueError('Retry belongs to another character')
            if old['request'].get('canvas_preset') != request.canvas_preset:raise Conflict('Retry canvas changed; create a new batch')
            if old['source_asset_id'] != source or old['request']['role'] != request.role: raise Conflict('Source changed; create a new batch instead of retrying')
            retryable = False
            retry_candidates = []
            for index, job_id in enumerate(old['job_ids']):
                state = db.execute('SELECT state FROM jobs WHERE id=?', (job_id,)).fetchone()
                if state and state['state'] in ('failed', 'needs_correction', 'cancelled'):
                    retryable = True
                    retry_candidates.append(Candidate.model_validate(old['request']['candidates'][index]).model_dump(exclude={'face_region'}))
                if state and state['state'] not in ('failed', 'needs_correction', 'cancelled', 'succeeded'):
                    raise Conflict('Original batch still active or uncertain')
            if not retryable: raise ValueError('No failed or cancelled items to retry')
            for candidate in request.candidates:
                normalized = candidate.model_dump(exclude={'face_region'})
                if normalized not in retry_candidates: raise ValueError('Retry can only include failed or cancelled candidates')
                retry_candidates.remove(normalized)
        jobs = []
        for i, candidate in enumerate(request.candidates):
            item_source = source
            outfit_id = candidate.outfit_id if request.role == 'outfit' else current['outfit_id'] if request.role in ('pose', 'expression') else None
            if request.role == 'matte':
                if not candidate.asset_id: raise ValueError('Source asset required for transparency')
                original, original_spec = tx.image(candidate.asset_id, character_id)
                review = tx.get('asset_review', candidate.asset_id, False)
                outfit_id = original_spec.get('outfit_id')
                approved = any(tx.approved(candidate.asset_id, kind, character_id, outfit_id) for kind in ('character','outfit','pose'))
                if not approved and not (review and review['decision']=='accepted'): raise ValueError('Review the source image before transparency')
                item_source = candidate.asset_id
            elif candidate.asset_id: raise ValueError('Asset input only applies to transparency')
            if request.role == 'outfit' and outfit_id not in outfits: raise ValueError('Unknown outfit version')
            if candidate.outfit_id and candidate.outfit_id != outfit_id: raise ValueError('Candidate does not match selected outfit')
            if request.role == 'pose':
                if not candidate.pose_id: raise ValueError('Saved pose required')
                pose = tx.get('pose', candidate.pose_id)
                if tx.get('asset', pose['render_asset_id']).get('role') != 'pose_render': raise ValueError('Pose render missing')
            elif candidate.pose_id: raise ValueError('Pose input only applies to pose generation')
            if candidate.face_region:
                if request.role != 'expression': raise ValueError('Face region only applies to expressions')
                a = tx.get('asset', source)
                x1,y1,x2,y2 = candidate.face_region
                if not (0 <= x1 < x2 <= a['width'] and 0 <= y1 < y2 <= a['height']): raise ValueError('Face region is outside the source canvas')
            if request.role == 'expression' and not candidate.expression.strip(): raise ValueError('Expression description required')
            spec = SceneSpec(asset_type='sprite' if request.role == 'identity' else request.role,
                             character_id=character_id, outfit_id=outfit_id,
                             canvas_preset=request.canvas_preset if request.role=='identity' else None,
                             expression=candidate.expression if request.role == 'expression' else original_spec.get('expression','') if request.role == 'matte' else 'neutral expression',
                             composition='full body, feet visible', scene='simple gray background',
                             visual_tags=['simple neutral clothing'] if request.role == 'identity' else [])
            sid, jid = uuid.uuid4().hex, uuid.uuid4().hex
            tx.put('scene_spec', sid, dict(spec=spec.model_dump(), metadata={'source': 'workbench', 'batch_id': key, 'selection_revision': current['revision']}))
            job = JobRequest(scene_spec_id=sid, reference_asset_id=item_source, pose_asset_id=candidate.pose_id, face_region=candidate.face_region, seed=candidate.seed, idempotency_key='batch:' + key + ':' + str(i)).model_dump()
            now = time.time()
            db.execute('INSERT INTO jobs(id,idempotency_key,body,state,created,updated) VALUES(?,?,?,?,?,?)',
                       (jid, job['idempotency_key'], json.dumps(job), 'queued', now, now))
            jobs.append(jid)
        batch = dict(character_id=character_id, request=body, job_ids=jobs, source_asset_id=source, created=time.time())
        tx.put('production_batch', key, batch)
        return dict(batch, id=key)


class ReviewRequest(Strict):
    expected_revision: int = Field(ge=0)
    decision: Literal['accepted', 'rejected']
    note: str = Field(default='', max_length=2000)


def review_image(store, character_id, asset_id, request: ReviewRequest):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        tx = Transaction(db)
        selection = tx.selection(character_id)
        if selection['revision'] != request.expected_revision: raise Conflict('Selection changed; refresh before reviewing')
        asset, spec = tx.image(asset_id, character_id)
        if spec.get('asset_type') != 'expression' or asset.get('parent_asset_id') != selection['pose_asset_id']:
            raise ValueError('Review requires an expression from the selected pose')
        value = dict(character_id=character_id, asset_id=asset_id, decision=request.decision,
                     note=request.note, selection_revision=selection['revision'], updated=time.time())
        tx.put('asset_review', asset_id, value, replace=True)
        tx.put('asset_review_history', uuid.uuid4().hex, value)
        return value
