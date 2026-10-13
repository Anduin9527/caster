"""Public HTTP read models, independent of SQLite's extensible record format.

Input validation stays in the domain models. Read models retain stored metadata
and describe the fields clients can depend on, including legacy nullable values.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .workbench import BatchRequest


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Health(BaseModel):
    status: Literal["ok"]
    worker_alive: bool
    execution_mode: Literal["local", "rabbitmq"] = "local"
    broker_connected: bool | None = None
    outbox_pending: int = 0


class Capabilities(BaseModel):
    selection: bool
    batches: bool
    outfit_versions: bool
    generation_online: bool
    pose_input: str


class CharacterOutfit(ReadModel):
    id: str
    tags: list[str]
    description: str = ""


class CharacterRecord(ReadModel):
    id: str
    name: str
    fixed_tags: list[str]
    description: str = ""
    outfits: list[CharacterOutfit]


class ProductionSpec(ReadModel):
    asset_type: str | None = None
    character_id: str | None = None
    outfit_id: str | None = None
    expression: str = ""
    action: str = ""


class ProductionAsset(ReadModel):
    id: str
    role: str
    mode: str | None = None
    width: int | None = None
    height: int | None = None
    download_url: str
    spec: ProductionSpec
    parent_asset_id: str | None = None
    job_id: str | None = None


class ProgressValue(ReadModel):
    value: float | None = None
    max: float | None = None


class JobProgress(ProgressValue):
    completed: bool | None = None
    type: str | None = None
    data: ProgressValue | None = None


class JobBody(ReadModel):
    scene_spec_id: str
    reference_asset_id: str | None = None


class DeliveryInfo(BaseModel):
    generation: int
    attempts: int
    received: bool
    retryable: bool
    request_id: str


class JobRecord(ReadModel):
    id: str
    state: Literal[
        "queued",
        "submitting",
        "running",
        "recovering",
        "submission_uncertain",
        "succeeded",
        "failed",
        "needs_correction",
        "cancelled",
    ]
    outputs: list[str]
    error: str | None = None
    created: float
    progress: JobProgress | None = None
    body: JobBody
    delivery: DeliveryInfo | None = None


class ProductionJob(JobRecord):
    spec: ProductionSpec


class ProductionSelection(ReadModel):
    character_id: str
    revision: int
    identity_asset_id: str | None
    outfit_asset_id: str | None
    outfit_id: str | None
    pose_asset_id: str | None


class ProductionBatch(ReadModel):
    id: str
    character_id: str
    job_ids: list[str]
    source_asset_id: str | None
    request: BatchRequest
    created: float


class OutfitVersionRecord(CharacterOutfit):
    name: str
    parent_id: str | None = None


class ApprovalRecord(ReadModel):
    id: str
    asset_id: str
    character_id: str
    kind: Literal["character", "outfit", "pose"]
    outfit_id: str | None = None


class PoseRecord(ReadModel):
    id: str
    render_asset_id: str
    lighting_prompt: str = ""
    preset_id: int | None = None


class ReviewRecord(ReadModel):
    asset_id: str
    decision: Literal["accepted", "rejected"]
    note: str = ""


class ProductionSnapshot(BaseModel):
    schema_version: Literal[1]
    characters: list[CharacterRecord]
    jobs: list[ProductionJob]
    assets: list[ProductionAsset]
    approvals: list[ApprovalRecord]
    poses: list[PoseRecord]
    selections: list[ProductionSelection]
    batches: list[ProductionBatch]
    outfit_versions: list[OutfitVersionRecord]
    reviews: list[ReviewRecord]


class ProductionPreset(BaseModel):
    id: int
    name: str
    source: str
    revision: str
    format: str
    preview_url: str


class PromptSettings(BaseModel):
    schema_version: Literal[1]
    artist_style: str
    fixed_positive: str
    fixed_negative: str
    content_hash: str
    source: Literal["default", "saved"]
    updated_at: float | None = None
