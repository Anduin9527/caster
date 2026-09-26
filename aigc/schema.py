from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Outfit(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    tags: list[str]
    description: str = ""
    # Legacy outfits load with empty values. New curated outfits freeze the
    # garment prose and exclusions beside their canonical tags so a later
    # prompt compiler never has to rediscover semantic choices.
    caption_en: list[str] = Field(default_factory=list, max_length=4)
    excluded_tags: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def prompt_recipe_is_coherent(self):
        if len({tag.casefold() for tag in self.tags}) != len(self.tags):
            raise ValueError("Outfit tags must be unique")
        if len({tag.casefold() for tag in self.excluded_tags}) != len(self.excluded_tags):
            raise ValueError("Excluded outfit tags must be unique")
        if {tag.casefold() for tag in self.tags} & {tag.casefold() for tag in self.excluded_tags}:
            raise ValueError("Included and excluded outfit tags overlap")
        return self


class CharacterPromptSections(Strict):
    """Semantic identity buckets used by the ordered Anima compiler.

    ``fixed_tags`` stays as the compatibility snapshot. New character records
    also preserve these buckets so the prompt compiler never has to guess
    whether an appearance tag is a character or a series.
    """

    character: list[str] = Field(default_factory=list, max_length=50)
    series: list[str] = Field(default_factory=list, max_length=50)
    general: list[str] = Field(default_factory=list, max_length=500)


class Character(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str
    fixed_tags: list[str]
    prompt_sections: CharacterPromptSections | None = None
    description: str = ""
    outfits: list[Outfit] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_outfits(self):
        if len({o.id for o in self.outfits}) != len(self.outfits):
            raise ValueError("Outfit IDs must be unique")
        return self


class SceneSpec(Strict):
    asset_type: Literal["sprite", "background", "outfit", "pose", "expression", "matte", "free"]
    character_id: str | None = None
    outfit_id: str | None = None
    action: str = ""
    expression: str = ""
    scene: str = ""
    composition: str = ""
    visual_tags: list[str] = Field(default_factory=list)
    prompt_captions: list[str] = Field(default_factory=list, max_length=8)
    excluded_tags: list[str] = Field(default_factory=list, max_length=100)
    description: str = ""
    unresolved: list[str] = Field(default_factory=list)
    canvas_preset: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.canvas_preset is not None:
            from .canvas import preset_size

            preset_size(self.canvas_preset)
        if self.asset_type == "background" and (self.character_id or self.outfit_id):
            raise ValueError("Backgrounds cannot reference a character or outfit")
        if self.asset_type in ("sprite", "outfit", "pose", "expression") and not self.character_id:
            raise ValueError("This asset type requires character_id")
        return self


class SceneRequest(Strict):
    story: str | None = Field(default=None, max_length=30000)
    character_id: str | None = None
    outfit_id: str | None = None
    asset_type: Literal["sprite", "background", "outfit", "pose", "expression", "matte", "free"] = (
        "sprite"
    )
    manual: SceneSpec | None = None

    @model_validator(mode="after")
    def one_input(self):
        if bool(self.story) == bool(self.manual):
            raise ValueError("Provide exactly one of story or manual")
        return self


class JobRequest(Strict):
    scene_spec_id: str
    reference_asset_id: str | None = None
    pose_asset_id: str | None = None
    mask_asset_id: str | None = None
    face_region: tuple[int, int, int, int] | None = None
    seed: int = Field(default=9527, ge=0, le=2**63 - 1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class Approval(Strict):
    kind: Literal["character", "outfit", "pose"]
    character_id: str
    outfit_id: str | None = None
    note: str = ""


class PoseState(Strict):
    state: dict
    lighting_prompt: str = ""
    render_asset_id: str
