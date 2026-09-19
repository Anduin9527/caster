"""Prompt library: editable templates, immutable character snapshots, no inference."""
import hashlib
import json
import re
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .schema import Strict, Character, Outfit, SceneSpec
from .prompts import compile_prompt
from .anima_defaults import escape_template_tags

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]+$', max_length=128)]

class PromptTemplate(Strict):
    id: Identifier
    kind: Literal['character', 'outfit']
    name: Text
    trigger: str = Field(default='', max_length=10000)
    tags: list[Text] = Field(default_factory=list, max_length=500)
    description: str = Field(default='', max_length=30000)
    categories: list[Text] = Field(default_factory=list, max_length=50)
    source: str = Field(default='user', max_length=2000)
    source_revision: str = Field(default='', max_length=128)
    source_key: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def nonempty(self):
        if not (self.trigger.strip() or any(t.strip() for t in self.tags) or self.description.strip()):
            raise ValueError('Template needs prompt content')
        if not self.name.strip():
            raise ValueError('Template needs a name')
        return self

class TemplateBundle(Strict):
    schema_version: Literal[1] = 1
    templates: list[PromptTemplate] = Field(min_length=1, max_length=10000)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({t.id for t in self.templates}) != len(self.templates):
            raise ValueError('Duplicate template IDs')
        return self

class TemplateSelection(Strict):
    character_template_id: Identifier
    outfit_template_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    character_id: Identifier
    name: Text | None = None
    # Matching Hub's trigger-only vs trigger+tags choice is explicit.
    include_character_tags: bool = True
    @model_validator(mode='after')
    def unique_outfits(self):
        if len(set(self.outfit_template_ids)) != len(self.outfit_template_ids):
            raise ValueError('Duplicate outfit templates')
        return self

class TemplateConflict(ValueError):
    pass

def import_bundle(store, bundle):
    """Atomic and idempotent; import never overwrites user edits."""
    created = skipped = 0
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for template in bundle.templates:
            body = template.model_dump()
            old = conn.execute('SELECT body FROM records WHERE kind=? AND id=?', ('prompt_template', template.id)).fetchone()
            if old:
                if json.loads(old['body']) != body:
                    raise TemplateConflict('Template ID already has different content: '+template.id)
                skipped += 1
            else:
                conn.execute('INSERT INTO records VALUES(?,?,?)', ('prompt_template', template.id, json.dumps(body, ensure_ascii=False)))
                created += 1
    return {'created': created, 'skipped': skipped}

def prompt_tags(template, include_tags=True):
    # Keep weighted tags and escaped character names intact; compiler deduplicates.
    return [escape_template_tags(tag) for tag in
            (([template['trigger']] if template['trigger'].strip() else []) + (template['tags'] if include_tags else []))]

def materialize(store, selection):
    def get(id, kind):
        t = store.get('prompt_template', id)
        if not t:
            raise LookupError('Unknown template: '+id)
        if t['kind'] != kind:
            raise ValueError('Expected '+kind+' template: '+id)
        return t
    base = get(selection.character_template_id, 'character')
    outfits = [get(id, 'outfit') for id in selection.outfit_template_ids]
    character = Character(id=selection.character_id, name=selection.name or base['name'],
        fixed_tags=prompt_tags(base, selection.include_character_tags), description=base['description'],
        outfits=[Outfit(id=t['id'], tags=prompt_tags(t), description=t['description']) for t in outfits]).model_dump()
    character['template_snapshot'] = {'character': base, 'outfits': outfits,
                                      'include_character_tags': selection.include_character_tags}
    previews = []
    for outfit_id in selection.outfit_template_ids or [None]:
        spec = SceneSpec(asset_type='sprite', character_id=selection.character_id, outfit_id=outfit_id)
        previews.append({'outfit_id': outfit_id, 'prompt': compile_prompt(spec, character)})
    return {'character': character, 'previews': previews}

HUB_REPO = 'https://github.com/j955229/Comfyui-Anima-Tools-HUB'
HUB_REVISION = 'a0c351e81a24ebdbc7f47c524139a8dfe1226705'

def parse_clothing_js(text):
    # Parse the upstream JSON literal, never eval/execute downloaded JavaScript.
    match = re.fullmatch(r'\s*const clothingData\s*=\s*(\[.*\])\s*;\s*window\.clothingData\s*=\s*clothingData\s*;\s*', text, re.S)
    if not match:
        raise ValueError('Unsupported Hub clothing_data.js format')
    data = json.loads(match[1])
    if not isinstance(data, list):
        raise ValueError('Expected clothing array')
    return data

def hub_bundle(characters, clothing, revision=HUB_REVISION):
    templates = []
    def add(kind, key, **fields):
        id = 'hub-'+kind+'-'+hashlib.sha256((revision+'\0'+key).encode()).hexdigest()[:24]
        templates.append(PromptTemplate(id=id, kind=kind, source=HUB_REPO,
            source_revision=revision, source_key=key, **fields))
    for key, item in characters.items():
        add('character', key, name=key.split('||')[0], trigger=item['trigger'], tags=item['tags'],
            categories=key.split('||')[1:])
    for item in clothing:
        add('outfit', str(item['id']), name=item.get('name_zh') or item['name'],
            tags=[t.strip() for t in item['tags'].split(',') if t.strip()], categories=item.get('categories', []))
    return TemplateBundle(templates=templates)
