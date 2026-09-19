import pytest
from aigc.store import Store
from aigc.workbench import get_selection, select_image, create_batch, SelectionRequest, BatchRequest, Conflict


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    s.put('character', {'name':'A','fixed_tags':[], 'outfits':[{'id':'coat','tags':['coat']},{'id':'dress','tags':['dress']}]}, 'a')
    def image(id, kind, outfit=None, parent=None):
        s.put('scene_spec', {'spec':{'asset_type':kind,'character_id':'a','outfit_id':outfit}}, id)
        j = s.create_job({'idempotency_key':id,'scene_spec_id':id})
        s.update_job(j['id'],state='succeeded',outputs=[id])
        s.put('asset',{'role':'original','mode':'RGB','scene_spec_id':id,'job_id':j['id'],'parent_asset_id':parent}, id)
    image('identity','sprite','coat')
    image('clothes1','outfit','dress','identity')
    image('clothes2','outfit','dress','identity')
    image('pose1','pose','dress','clothes1')
    image('pose2','pose','dress','clothes1')
    image('legacy-pose','pose','coat','identity')
    s.put('asset',{'role':'pose_render'},'render')
    s.put('pose',{'render_asset_id':'render','state':{}},'saved-pose')
    return s


def choose(s, stage, asset, revision=None, approve=True):
    return select_image(s,'a',SelectionRequest(stage=stage,asset_id=asset,expected_revision=get_selection(s,'a')['revision'] if revision is None else revision, approve=approve))


def test_selection_is_explicit_atomic_and_preserves_history(store):
    assert get_selection(store,'a')['revision'] == 0
    with pytest.raises(ValueError,match='approval'): choose(store,'identity','identity',approve=False)
    choose(store,'identity','identity')
    choose(store,'outfit','clothes1')
    choose(store,'pose','pose1')
    previous = store.list('approval')
    choose(store,'pose','pose2')
    assert get_selection(store,'a')['pose_asset_id'] == 'pose2'
    assert all(a in store.list('approval') for a in previous)
    choose(store,'outfit','clothes2')
    assert get_selection(store,'a')['pose_asset_id'] is None
    with pytest.raises(ValueError, match='selected outfit'): choose(store,'pose','pose1')
    with pytest.raises(Conflict): choose(store,'outfit','clothes1',revision=1)
    assert len(store.list('selection_history')) == 5
    assert len(store.list('asset')) == 7


def test_legacy_approvals_do_not_implicitly_select(store):
    store.put('approval',{'asset_id':'identity','kind':'character','character_id':'a','outfit_id':'coat'})
    store.put('approval',{'asset_id':'legacy-pose','kind':'pose','character_id':'a','outfit_id':'coat'})
    before = store.list('approval')
    assert get_selection(store,'a')['identity_asset_id'] is None
    choose(store,'identity','identity',approve=False)
    choose(store,'outfit','identity',approve=False)
    choose(store,'pose','legacy-pose',approve=False)
    assert store.list('approval') == before


def test_batch_atomicity_idempotency_exact_parent_and_stale_revision(store):
    choose(store,'identity','identity')
    choose(store,'outfit','clothes1')
    choose(store,'pose','pose1')
    request = BatchRequest(role='expression',expected_revision=3,idempotency_key='emotions',candidates=[{'expression':'happy'},{'expression':'angry'}])
    batch = create_batch(store,'a',request)
    assert create_batch(store,'a',request)['id'] == batch['id']
    assert len(batch['job_ids']) == 2
    assert all(store.job(j)['body']['reference_asset_id']=='pose1' for j in batch['job_ids'])
    choose(store,'pose','pose2')
    # A lost HTTP response is recovered with the original key, even after selection changes.
    assert create_batch(store,'a',request)['id'] == batch['id']
    with pytest.raises(Conflict): create_batch(store,'a',request.model_copy(update={'idempotency_key':'new'}))
    before = len(store.jobs()),len(store.list('scene_spec'))
    invalid = BatchRequest(role='pose',expected_revision=4,idempotency_key='invalid',candidates=[{'pose_id':'saved-pose'},{'pose_id':'missing'}])
    with pytest.raises(LookupError): create_batch(store,'a',invalid)
    assert (len(store.jobs()),len(store.list('scene_spec'))) == before
    assert len(store.list('production_batch')) == 1


def test_selection_rejects_failed_outputs_and_wrong_character(store):
    choose(store,'identity','identity')
    asset=store.get('asset','clothes1')
    store.update_job(asset['job_id'],state='failed')
    with pytest.raises(ValueError,match='successful'): choose(store,'outfit','clothes1')
    store.put('character',{'name':'B','outfits':[]},'b')
    with pytest.raises(ValueError,match='another character'):
        select_image(store,'b',SelectionRequest(stage='identity',asset_id='identity',expected_revision=0,approve=True))
    assert get_selection(store,'b')['revision']==0


def test_expression_review_and_transparency_keep_exact_parent(store):
    from aigc.workbench import review_image, ReviewRequest
    choose(store,'identity','identity'); choose(store,'outfit','clothes1'); choose(store,'pose','pose1')
    batch=create_batch(store,'a',BatchRequest(role='expression',expected_revision=3,idempotency_key='expression',candidates=[{'expression':'happy'}]))
    job=store.job(batch['job_ids'][0])
    store.put('asset',{'role':'original','mode':'RGB','job_id':job['id'],'scene_spec_id':job['body']['scene_spec_id'],'parent_asset_id':'pose1'},'smile')
    store.update_job(job['id'],state='succeeded',outputs=['smile'])
    matte=BatchRequest(role='matte',expected_revision=3,idempotency_key='alpha',candidates=[{'asset_id':'smile'}])
    with pytest.raises(ValueError,match='Review'): create_batch(store,'a',matte)
    review_image(store,'a','smile',ReviewRequest(expected_revision=3,decision='accepted'))
    result=create_batch(store,'a',matte)
    assert store.job(result['job_ids'][0])['body']['reference_asset_id']=='smile'
    choose(store,'pose','pose2')
    with pytest.raises(ValueError,match='selected pose'): review_image(store,'a','smile',ReviewRequest(expected_revision=4,decision='accepted'))
    assert store.get('asset_review','smile')['decision']=='accepted'


def test_retry_excludes_successful_items_and_cannot_duplicate_failed_candidate(store):
    first=create_batch(store,'a',BatchRequest(role='identity',expected_revision=0,idempotency_key='first',candidates=[{'seed':1},{'seed':2}]))
    store.update_job(first['job_ids'][0],state='succeeded')
    store.update_job(first['job_ids'][1],state='failed')
    args=dict(role='identity',expected_revision=0,idempotency_key='retry',retry_of=first['id'])
    with pytest.raises(ValueError,match='failed or cancelled'): create_batch(store,'a',BatchRequest(**args,candidates=[{'seed':1}]))
    with pytest.raises(ValueError,match='failed or cancelled'): create_batch(store,'a',BatchRequest(**args,candidates=[{'seed':2},{'seed':2}]))
    result=create_batch(store,'a',BatchRequest(**args,candidates=[{'seed':2}]))
    assert len(result['job_ids'])==1
    assert store.job(first['job_ids'][1])['state']=='failed'


def test_expression_face_region_must_fit_source_canvas(store):
    choose(store,'identity','identity'); choose(store,'outfit','clothes1'); choose(store,'pose','pose1')
    asset=store.get('asset','pose1'); store.put('asset',dict(asset,width=100,height=200),'pose1',replace=True)
    args=dict(role='expression',expected_revision=3,idempotency_key='face')
    with pytest.raises(ValueError,match='outside'): create_batch(store,'a',BatchRequest(**args,candidates=[{'expression':'happy','face_region':[0,0,101,20]}]))
    result=create_batch(store,'a',BatchRequest(**args,candidates=[{'expression':'happy','face_region':[1,2,50,80]}]))
    assert store.job(result['job_ids'][0])['body']['face_region']==[1,2,50,80]


def test_six_vnccs_presets_render_without_inference_and_save_idempotently(store):
    import io
    from PIL import Image
    from aigc import pose_presets
    entries=pose_presets.catalog()
    assert [p['id'] for p in entries]==[1,2,3,4,5,6]
    assert all(p['format']=='vnccs_2d' and p['revision'] in p['source'] for p in entries)
    for item in entries:
        blob=pose_presets.render(item['id'])
        assert Image.open(io.BytesIO(blob)).size==(512,1536)
    before=len(store.jobs()),len(store.list('approval'))
    a=pose_presets.materialize(store,1)
    b=pose_presets.materialize(store,1)
    assert a==b
    assert a['state']['format']=='vnccs_2d'
    assert store.get('asset',a['render_asset_id'])['role']=='pose_render'
    assert (len(store.jobs()),len(store.list('approval')))==before
    with pytest.raises(LookupError):pose_presets.render(7)
