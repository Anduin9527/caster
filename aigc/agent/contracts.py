"""Cross-layer contracts shared by retrieval, the agent, the API and the workbench.

These schemas describe the data exchanged across modules. Unknown fields are rejected so a
model that invents a field fails loudly instead of silently changing generation
parameters.
"""

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .redaction import contains_credential

SCHEMA_VERSION = 1

# Hard, explicit route table. A model may ask for a route by name only; it can
# never submit a workflow path, and the backend owns route -> workflow mapping.
ROUTES: dict[str, dict] = {
    "anima_free": {
        "workflow": "anima_free",
        "asset_type": "free",
        "label": "Anima 自由生成",
        "needs_source": True,
        "semantic": "自由动作／交互／构图，沿用已选图的画布与身份",
    },
    "anima_text": {
        "workflow": "sprite",
        "asset_type": "sprite",
        "label": "Anima 文字立绘",
        "needs_source": False,
        "semantic": "无参考图的纯文字立绘",
    },
    "anima_outfit": {
        "workflow": "outfit",
        "asset_type": "outfit",
        "label": "Anima 换装",
        "needs_source": True,
        "semantic": "在已选身份图上追加服装版本",
    },
    "qwen_pose": {
        "workflow": "pose",
        "asset_type": "pose",
        "label": "姿态生成",
        "needs_source": True,
        "semantic": "需要已保存的姿态状态，不接收自由动作描述",
    },
    "local_expression": {
        "workflow": "expression",
        "asset_type": "expression",
        "label": "局部表情",
        "needs_source": True,
        "semantic": "从已选姿态图独立分支，只改表情",
    },
    "anima_background": {
        "workflow": "background",
        "asset_type": "background",
        "label": "背景生成",
        "needs_source": False,
        "semantic": "无人背景",
    },
    "anima_matte": {
        "workflow": "matte",
        "asset_type": "matte",
        "label": "透明导出",
        "needs_source": True,
        "semantic": "对已选图做抠图",
    },
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Which selected image each route consumes, listed upstream -> downstream, the
# same order the workbench chain derives them (identity -> outfit -> pose). A
# route with several stages takes the *most downstream* image the user actually
# selected, because that is the character state they are currently looking at:
# falling back to the identity image while an outfit image is selected would
# silently throw away the outfit the user chose. Mirrors the existing workbench
# source rules so the agent can never pick an image the manual flow would reject.
ROUTE_SOURCE_STAGE = {
    "anima_free": ("identity", "outfit"),
    "anima_outfit": ("identity",),
    "qwen_pose": ("outfit",),
    "local_expression": ("pose",),
    "anima_matte": ("identity", "outfit"),
    "anima_text": (),
    "anima_background": (),
}


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
class SearchHit(Strict):
    """One retrievable document.

    ``score`` is the hit's branch-local ranking signal, never a probability of
    being right. Its scale depends on the stage that produced it: dense cosine,
    reciprocal-rank fusion, or a cross-encoder score. Composition retrieval can
    interleave several branches for coverage, so final display order need not be
    monotonic by this value. Callers must use list order and ``score_semantics``
    rather than compare scores across branches or runs.
    """

    doc_id: str = Field(min_length=1, max_length=200)
    kind: Literal["character_template", "outfit_template", "tag", "wiki"]
    template_id: str | None = None
    title: str = Field(max_length=500)
    summary: str = Field(default="", max_length=4000)
    source: str = Field(default="local", max_length=2000)
    source_revision: str = Field(default="", max_length=128)
    match: Literal["exact", "alias", "token", "semantic", "none"]
    score: float = Field(default=0.0, ge=0)
    preview_url: str | None = None
    # A hit whose template disappeared from the business store must never be used
    # as an execution input; the caller re-reads the live record before executing.
    stale: bool = False
    # Wiki provenance, so a hit can be traced back to the corpus record.
    source_id: str | None = None
    chunk_id: str | None = None
    # A name/alias point can support a name match, but it says nothing about the
    # entry's body. Callers must not quote it as body evidence.
    name_only: bool = False
    # Independent retrieval fields that supported this rank.  Empty means an
    # older/single-field adapter did not report the distinction.
    matched_fields: list[Literal["name", "definition"]] = Field(default_factory=list, max_length=2)
    # Set only when the deterministic whole-query resolver supplied the hit.
    # Wiki other_names are recall-only and therefore never produce a safe pin.
    name_provenance: Literal["canonical", "translated_name", "wiki_other_name"] | None = None

    @model_validator(mode="after")
    def template_hits_carry_ids(self):
        if self.kind.endswith("_template") and not self.template_id:
            raise ValueError("Template hits must carry the real template ID")
        return self


# --------------------------------------------------------------------------- #
# Workbench context
# --------------------------------------------------------------------------- #
class UncommittedDraft(Strict):
    """Local, un-submitted workbench state. Never mixed with server truth."""

    stage: str = Field(max_length=64)
    note: str = Field(default="", max_length=2000)
    values: dict[str, Any] = Field(default_factory=dict)


class WorkbenchContext(Strict):
    """What the user is looking at right now, sent with every message."""

    character_id: str | None = None
    character_name: str = ""
    stage: Literal["none", "identity", "outfit", "pose", "expression", "export"] = "none"
    selected_asset_ids: dict[str, str | None] = Field(default_factory=dict)
    selected_outfit_id: str | None = None
    selection_revision: int = Field(default=0, ge=0)
    # Explicitly separate from selection_revision: an uncommitted draft is local
    # only and must never be treated as an approved source image.
    uncommitted_draft: UncommittedDraft | None = None
    candidate_set_id: str | None = None
    canvas_preset: str | None = None
    known_character_ids: list[str] = Field(default_factory=list, max_length=500)
    # Guided mode changes reusable workbench state in explicit stages. Direct
    # mode prepares a one-off image plan and never mutates the character library.
    interaction_mode: Literal["guided", "direct"] = "guided"

    @model_validator(mode="after")
    def known_characters_include_active(self):
        if self.character_id and self.character_id not in self.known_character_ids:
            raise ValueError("Active character must be listed in known_character_ids")
        return self

    def selected(self, stage: str) -> str | None:
        return self.selected_asset_ids.get(stage)


class WorkbenchChange(Strict):
    """A user-visible, content-bound proposal for a reusable workbench write."""

    change_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    operation: Literal["create_character", "append_outfit"]
    status: Literal["awaiting_approval", "applied", "cancelled", "stale"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    character_id: str = Field(min_length=1, max_length=128)
    character_name: str = Field(default="", max_length=2000)
    focus: Literal["identity", "outfit"]
    character_template_id: str | None = Field(default=None, max_length=128)
    character_template_name: str = Field(default="", max_length=2000)
    character_preview_url: str | None = Field(default=None, max_length=2000)
    character_tags: list[str] = Field(default_factory=list, max_length=500)
    outfit_template_id: str | None = Field(default=None, max_length=128)
    outfit_template_name: str = Field(default="", max_length=2000)
    outfit_preview_url: str | None = Field(default=None, max_length=2000)
    outfit_tags: list[str] = Field(default_factory=list, max_length=500)
    outfit_captions: list[str] = Field(default_factory=list, max_length=4)
    excluded_outfit_tags: list[str] = Field(default_factory=list, max_length=100)
    # Frozen source data is private to the deterministic apply path. The frontend
    # only needs the display fields above, but approval must apply exactly what
    # the user saw even if the template index changes in the meantime.
    character_template_snapshot: dict[str, Any] = Field(default_factory=dict)
    outfit_template_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_character_hash: str = Field(default="", max_length=128)
    content_hash: str = Field(min_length=64, max_length=64)
    created_at: float = 0.0
    applied_at: float | None = None

    def hashed_fields(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "character_id": self.character_id,
            "character_name": self.character_name,
            "focus": self.focus,
            "character_template_id": self.character_template_id,
            "character_template_snapshot": self.character_template_snapshot,
            "character_tags": self.character_tags,
            "outfit_template_id": self.outfit_template_id,
            "outfit_template_snapshot": self.outfit_template_snapshot,
            "outfit_tags": self.outfit_tags,
            "outfit_captions": self.outfit_captions,
            "excluded_outfit_tags": self.excluded_outfit_tags,
            "source_character_hash": self.source_character_hash,
        }


def workbench_change_from(record: dict[str, Any]) -> "WorkbenchChange":
    return WorkbenchChange.model_validate({k: v for k, v in record.items() if k != "id"})


# --------------------------------------------------------------------------- #
# Production intent and generation plan
# --------------------------------------------------------------------------- #
class ProductionIntent(Strict):
    """The structured making intent the agent derives from natural language."""

    route: str = Field(max_length=64)
    action: str = Field(default="", max_length=4000)
    expression: str = Field(default="", max_length=2000)
    scene: str = Field(default="", max_length=4000)
    composition: str = Field(default="", max_length=4000)
    visual_tags: list[str] = Field(default_factory=list, max_length=200)
    prompt_captions: list[str] = Field(default_factory=list, max_length=8)
    excluded_tags: list[str] = Field(default_factory=list, max_length=100)
    character_template_id: str | None = None
    character_name: str | None = None
    outfit_template_ids: list[str] = Field(default_factory=list, max_length=50)
    outfit_id: str | None = None
    # The saved pose state to generate from. Explicit so the first pose image can
    # be produced before any pose image has been selected, and so a specific saved
    # state can be chosen rather than only reusing the previous one.
    pose_asset_id: str | None = None
    count: int = Field(default=1, ge=1, le=8)
    reference_mode: Literal["selected_image", "none"] = "selected_image"
    keep: list[str] = Field(default_factory=list, max_length=100)
    change: list[str] = Field(default_factory=list, max_length=100)
    allow_creative: list[str] = Field(default_factory=list, max_length=100)
    clarify: list[str] = Field(default_factory=list, max_length=100)
    canvas_preset: str | None = None

    @model_validator(mode="after")
    def known_route(self):
        if self.route not in ROUTES:
            raise ValueError("Unknown route: " + self.route)
        if ROUTES[self.route]["needs_source"] and self.reference_mode == "none":
            raise ValueError("Route " + self.route + " requires a source image")
        return self


class PlanParameters(Strict):
    """Every value that changes pixels, resolved before the card is shown."""

    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)
    seeds: list[int] = Field(min_length=1, max_length=8)
    steps: int | None = None
    cfg: float | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    denoise: float | None = Field(default=None, ge=0, le=1)
    canvas_preset: str | None = None
    face_region: list[int] | None = None
    mask_asset_id: str | None = None
    pose_asset_id: str | None = None


class GenerationPlan(Strict):
    """One card == one input-fixed, parameter-fixed batch awaiting approval."""

    plan_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0)
    conversation_id: str = Field(max_length=128)
    character_id: str | None = None
    route: str = Field(max_length=64)
    workflow: str = Field(max_length=64)
    workflow_version: str = Field(default="", max_length=128)
    # Digest of the workflow's field bindings (which node receives the prompt,
    # seed and canvas). Frozen next to the graph: a binding change after planning
    # changes the produced image just as a graph change does.
    workflow_bindings_hash: str = Field(default="", max_length=128)
    asset_type: str = Field(max_length=64)
    title: str = Field(max_length=200)
    summary: str = Field(default="", max_length=8000)
    status: Literal["draft", "awaiting_approval", "queued", "superseded", "cancelled", "stale"]
    # Input provenance
    source_kind: Literal["none", "selected_image", "template_preview", "upload"]
    source_asset_id: str | None = None
    source_sha256: str | None = None
    source_selection_revision: int | None = Field(default=None, ge=0)
    character_template_id: str | None = None
    template_snapshot: dict[str, Any] = Field(default_factory=dict)
    # The structured intent the card was built from, so a partial PATCH merges
    # into it instead of rebuilding an empty one.
    intent: dict[str, Any] = Field(default_factory=dict)
    # What the user sees and what gets executed
    prompt: dict[str, Any] = Field(default_factory=dict)
    parameters: PlanParameters
    spec: dict[str, Any] = Field(default_factory=dict)
    outfit_id: str | None = None
    keep: list[str] = Field(default_factory=list, max_length=100)
    change: list[str] = Field(default_factory=list, max_length=100)
    allow_creative: list[str] = Field(default_factory=list, max_length=100)
    clarify: list[str] = Field(default_factory=list, max_length=100)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    unresolved: list[str] = Field(default_factory=list, max_length=50)
    job_ids: list[str] = Field(default_factory=list, max_length=8)
    authorization_id: str | None = None
    content_hash: str = Field(min_length=8, max_length=128)
    created: float = 0.0
    updated: float = 0.0

    @model_validator(mode="after")
    def coherent(self):
        if self.route not in ROUTES:
            raise ValueError("Unknown route: " + self.route)
        expected = ROUTES[self.route]
        if self.workflow != expected["workflow"] or self.asset_type != expected["asset_type"]:
            raise ValueError("Route/workflow/asset_type disagree; the backend owns this mapping")
        if expected["needs_source"] and not self.source_asset_id:
            raise ValueError("Route " + self.route + " requires a source asset")
        if not expected["needs_source"] and self.source_kind == "selected_image":
            raise ValueError("Route " + self.route + " takes no reference image")
        if self.status == "queued" and not self.job_ids:
            raise ValueError("A queued plan must reference its jobs")
        return self

    @property
    def count(self) -> int:
        return len(self.parameters.seeds)

    def hashed_fields(self) -> dict[str, Any]:
        """Every field that can change the produced image.

        The workflow version and binding digests are included: approving against
        one graph and executing another would produce different pixels even with
        an identical prompt and seed.
        """
        return {
            "route": self.route,
            "workflow": self.workflow,
            "asset_type": self.asset_type,
            "character_id": self.character_id,
            "outfit_id": self.outfit_id,
            "source_asset_id": self.source_asset_id,
            "source_sha256": self.source_sha256,
            "prompt": self.prompt,
            "parameters": self.parameters.model_dump(),
            "spec": self.spec,
            "template_snapshot": self.template_snapshot,
            "workflow_version": self.workflow_version,
            "workflow_bindings_hash": self.workflow_bindings_hash,
        }


def content_hash(fields: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def plan_from(record: dict[str, Any]) -> "GenerationPlan":
    """Validate a stored plan record, dropping the store's synthetic id field."""
    return GenerationPlan.model_validate({k: v for k, v in record.items() if k != "id"})


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
EVENT_TYPES = (
    "message.delta",
    "message.completed",
    "activity",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "candidates.ready",
    "retrieval.ready",
    "outfit.catalog.ready",
    "workbench.change.ready",
    "workbench.updated",
    "plan.ready",
    "plan.stale",
    "jobs.queued",
    "job.updated",
    "run.failed",
    "run.completed",
)

_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|password|credential|access[_-]?token|"
    r"refresh[_-]?token|private[_-]?key|bearer|authorization)",
    re.I,
)
# Identifier references are not secrets: an authorization_id or plan_id names a
# record, it does not carry credential material.
_REFERENCE_KEY = re.compile(r"(_id|_ids|_sha256|_hash|_count|_revision)$", re.I)


class AgentEvent(Strict):
    """A typed, persistable run event. Never carries secrets or model reasoning."""

    event_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    type: str = Field(max_length=64)
    at: float = 0.0
    schema_version: int = SCHEMA_VERSION
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_secrets(self):
        if self.type not in EVENT_TYPES:
            raise ValueError("Unknown event type: " + self.type)

        def scan(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    name = str(key)
                    if _SECRET_KEY.search(name) and not _REFERENCE_KEY.search(name):
                        raise ValueError(
                            "Event payload must not carry credential-like key: " + name
                        )
                    scan(item, path + "/" + name)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    scan(item, path + "/" + str(index))
            elif isinstance(value, str) and contains_credential(value):
                raise ValueError("Event payload must not carry credential-like text")

        scan(self.payload, "")
        return self
