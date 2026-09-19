from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Outfit(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    tags: list[str]
    description: str = ''

class Character(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    name: str
    fixed_tags: list[str]
    description: str = ''
    outfits: list[Outfit] = Field(default_factory=list)
    @model_validator(mode='after')
    def unique_outfits(self):
        if len({o.id for o in self.outfits}) != len(self.outfits):
            raise ValueError('Outfit IDs must be unique')
        return self

class SceneSpec(Strict):
    asset_type: Literal['sprite','background','outfit','pose','expression','matte']
    character_id: str | None = None
    outfit_id: str | None = None
    action: str = ''
    expression: str = ''
    scene: str = ''
    composition: str = ''
    visual_tags: list[str] = Field(default_factory=list)
    description: str = ''
    unresolved: list[str] = Field(default_factory=list)
    canvas_preset: str | None = None
    @model_validator(mode='after')
    def coherent(self):
        if self.canvas_preset is not None:
            from .canvas import preset_size
            preset_size(self.canvas_preset)
        if self.asset_type == 'background' and (self.character_id or self.outfit_id):
            raise ValueError('Backgrounds cannot reference a character or outfit')
        if self.asset_type in ('sprite','outfit','pose','expression') and not self.character_id:
            raise ValueError('This asset type requires character_id')
        return self

class SceneRequest(Strict):
    story: str | None = Field(default=None,max_length=30000)
    character_id: str | None = None
    outfit_id: str | None = None
    asset_type: Literal['sprite','background','outfit','pose','expression','matte'] = 'sprite'
    manual: SceneSpec | None = None
    @model_validator(mode='after')
    def one_input(self):
        if bool(self.story) == bool(self.manual):
            raise ValueError('Provide exactly one of story or manual')
        return self

class JobRequest(Strict):
    scene_spec_id: str
    reference_asset_id: str | None = None
    pose_asset_id: str | None = None
    mask_asset_id: str | None = None
    face_region: tuple[int,int,int,int] | None = None
    seed: int = Field(default=9527,ge=0,le=2**63-1)
    idempotency_key: str = Field(min_length=1,max_length=128)

class Approval(Strict):
    kind: Literal['character','outfit','pose']
    character_id: str
    outfit_id: str | None = None
    note: str = ''

class PoseState(Strict):
    state: dict
    lighting_prompt: str = ''
    render_asset_id: str
