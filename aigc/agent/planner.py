"""Intent + workbench context -> a frozen :class:`GenerationPlan`.

Everything the approval card shows is resolved here, before the user sees it:
canvas, concrete seeds, input asset SHA256, template snapshot, workflow version
and the compiled prompt. The plan never re-reads a template at execution time.

Prompt compilation deliberately calls the shared :func:`aigc.prompts.compile_prompt`
instead of a second implementation, so a worker that recompiled would produce the
same text.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..canvas import preset_size, source_size
from ..prompt_settings import get_prompt_settings
from ..prompts import compile_prompt
from ..schema import SceneSpec
from .contracts import (
    ROUTE_SOURCE_STAGE,
    ROUTES,
    GenerationPlan,
    PlanParameters,
    ProductionIntent,
    WorkbenchContext,
    content_hash,
    plan_from,
)
from .intent import identity_conflicts

ROOT = Path(__file__).resolve().parents[2]


class PlannerError(ValueError):
    pass


def _read_workflow_defaults(workflow: str) -> dict[str, Any]:
    """The executable graph, its field bindings and both digests.

    The bindings decide which node receives the prompt, the seed and the canvas,
    so the plan records their digest too: a binding change after planning is
    exactly as much of a content change as a graph change.
    """
    from ..workflows import digest, read_bindings, read_template

    path = ROOT / "workflows" / (workflow + ".api.json")
    if not path.is_file():
        raise PlannerError("工作流未安装：" + workflow)
    try:
        graph = read_template(workflow)
        bindings = read_bindings(workflow)
    except ValueError as error:
        raise PlannerError(str(error))
    sampler: dict[str, Any] = {}
    for node in graph.values():
        if node.get("class_type") in (
            "KSampler",
            "KSamplerAdvanced",
            "SamplerCustom",
            "SamplerCustomAdvanced",
        ):
            inputs = node.get("inputs", {})
            for key in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if key in inputs and isinstance(inputs[key], (int, float, str)):
                    sampler[key] = inputs[key]
            break
    return {"version": digest(graph), "bindings": digest(bindings), "sampler": sampler}


def _seeds(plan_id: str, revision: int, count: int) -> list[int]:
    """Concrete per-candidate seeds. Never left as the literal word "random"."""
    base = int(hashlib.sha256((plan_id + ":" + str(revision)).encode()).hexdigest()[:12], 16)
    seeds = []
    for index in range(count):
        seeds.append((base + index * 7919) % (2**63 - 1))
    return seeds


class Planner:
    def __init__(self, store, retrieval=None):
        self.store = store
        self.retrieval = retrieval

    # -- persistence -------------------------------------------------------- #
    def get(self, plan_id: str, revision: int | None = None) -> GenerationPlan:
        record = self.store.get("generation_plan", plan_id)
        if not record:
            raise PlannerError("未知计划：" + str(plan_id))
        if revision is None:
            return plan_from(record)
        history = self.store.get("generation_plan_revision", plan_id + ":" + str(revision))
        if not history:
            raise PlannerError("未知计划版本：" + str(plan_id) + ":" + str(revision))
        return plan_from(history)

    def revisions(self, plan_id: str) -> list[GenerationPlan]:
        rows = [
            r for r in self.store.list("generation_plan_revision") if r.get("plan_id") == plan_id
        ]
        return [plan_from(r) for r in sorted(rows, key=lambda r: r.get("revision", 0))]

    def latest_for(self, conversation_id: str) -> list[GenerationPlan]:
        rows = [
            r
            for r in self.store.list("generation_plan")
            if r.get("conversation_id") == conversation_id
        ]
        return [plan_from(r) for r in rows]

    def _persist(self, plan: GenerationPlan) -> GenerationPlan:
        # A revision snapshot is an idempotent upsert: mark_stale and cancel
        # rewrite the same revision rather than creating a duplicate.
        self.store.put(
            "generation_plan_revision",
            dict(plan.model_dump(), plan_id=plan.plan_id),
            plan.plan_id + ":" + str(plan.revision),
            replace=True,
        )
        self.store.put("generation_plan", plan.model_dump(), plan.plan_id, replace=True)
        return plan

    # -- plan construction -------------------------------------------------- #
    def prepare(
        self,
        conversation_id: str,
        context: WorkbenchContext,
        intent: ProductionIntent,
        plan_id: str | None = None,
    ) -> GenerationPlan:
        plan_id = plan_id or self._new_id()
        return self._persist(self.build(conversation_id, context, intent, plan_id, 0))

    def prepare_exact_prompt(
        self,
        *,
        conversation_id: str,
        character_id: str,
        plan_id: str,
        title: str,
        summary: str,
        prompt: dict[str, Any],
        spec: SceneSpec,
        seed: int,
        template_snapshot: dict[str, Any],
        outfit_id: str | None = None,
        change: list[str] | None = None,
    ) -> GenerationPlan:
        """Prepare a normal approval card around an already reviewed prompt.

        This is the narrow bridge used by controlled catalog experiments.  It
        does not authorize or enqueue work: the returned plan goes through the
        same :mod:`authorize` transaction as every Agent plan.  The caller owns
        the semantic recipe, while this method owns workflow/version/parameter
        freezing so a specialist flow cannot accidentally create a second
        execution contract.
        """
        if spec.asset_type != "sprite" or spec.character_id != character_id:
            raise PlannerError("精确提示词计划必须是绑定角色的文字立绘")
        if not self.store.get("character", character_id):
            raise PlannerError("角色不存在：" + character_id)
        if prompt.get("workflow_prompt_mode") != "exact" or not prompt.get("positive"):
            raise PlannerError("精确提示词计划缺少已编译的 positive prompt")
        workflow = ROUTES["anima_text"]["workflow"]
        defaults = _read_workflow_defaults(workflow)
        width, height = preset_size(spec.canvas_preset or "1024x1536")
        parameters = PlanParameters(
            width=width,
            height=height,
            seeds=[seed],
            canvas_preset=spec.canvas_preset,
            **defaults["sampler"],
        )
        now = time.time()
        plan = GenerationPlan(
            plan_id=plan_id,
            revision=0,
            conversation_id=conversation_id,
            character_id=character_id,
            route="anima_text",
            workflow=workflow,
            workflow_version=defaults["version"],
            workflow_bindings_hash=defaults["bindings"],
            asset_type="sprite",
            title=title,
            summary=summary,
            status="awaiting_approval",
            source_kind="none",
            source_asset_id=None,
            source_sha256=None,
            source_selection_revision=None,
            character_template_id=None,
            template_snapshot=template_snapshot,
            intent={"route": "anima_text", "source": "reviewed-exact-prompt"},
            prompt=prompt,
            parameters=parameters,
            spec=spec.model_dump(),
            outfit_id=outfit_id,
            keep=["固定 Miku 身份、构图、工作流与 seed"],
            change=list(change or []),
            allow_creative=[],
            clarify=[],
            depends_on=[],
            unresolved=[],
            job_ids=[],
            authorization_id=None,
            content_hash="0" * 64,
            created=now,
            updated=now,
        )
        plan.content_hash = content_hash(plan.hashed_fields())
        # Deterministic experiment IDs make prepare idempotent, but the
        # check-and-insert must be one transaction.  A late concurrent prepare
        # must never overwrite a plan that another request already approved.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("generation_plan", plan_id)
            ).fetchone()
            if row:
                current = plan_from(json.loads(row["body"]))
                if current.content_hash != plan.content_hash:
                    raise PlannerError("同一实验计划 ID 已绑定其他内容")
                return current
            revision_id = plan_id + ":0"
            orphan = db.execute(
                "SELECT 1 FROM records WHERE kind=? AND id=?",
                ("generation_plan_revision", revision_id),
            ).fetchone()
            if orphan:
                raise PlannerError("实验计划存在孤立版本记录，需要人工核对")
            db.execute(
                "INSERT INTO records VALUES(?,?,?)",
                (
                    "generation_plan_revision",
                    revision_id,
                    json.dumps(dict(plan.model_dump(), plan_id=plan_id), ensure_ascii=False),
                ),
            )
            db.execute(
                "INSERT INTO records VALUES(?,?,?)",
                ("generation_plan", plan_id, json.dumps(plan.model_dump(), ensure_ascii=False)),
            )
        return plan

    def build(
        self,
        conversation_id: str,
        context: WorkbenchContext,
        intent: ProductionIntent,
        plan_id: str,
        revision: int,
    ) -> GenerationPlan:
        """Resolve everything without persisting, so a revision cannot clobber another."""
        route = intent.route
        if route not in ROUTES:
            raise PlannerError("未知路线：" + route)
        spec_route = ROUTES[route]
        character = None
        if context.character_id:
            character = self.store.get("character", context.character_id)
            if not character:
                raise PlannerError("角色不存在：" + context.character_id)
        if (
            spec_route["asset_type"] in ("sprite", "outfit", "pose", "expression", "free")
            and not character
        ):
            raise PlannerError("该路线需要先确定角色")

        source_asset_id, source_sha256, source_revision, source_kind = self._resolve_source(
            route, context, character, intent
        )
        spec = self._build_spec(route, context, intent, source_asset_id)
        prompt = compile_prompt(spec, character, get_prompt_settings(self.store))
        workflow = spec_route["workflow"]
        defaults = _read_workflow_defaults(workflow)
        parameters = self._parameters(
            route, context, spec, intent, source_asset_id, defaults, plan_id, revision
        )
        keep, change, allow = self._describe(context, intent, route)
        clarify = [note for note in intent.clarify if note]
        # Structured checks that vector distance cannot guarantee.
        unresolved = list(dict.fromkeys(identity_conflicts(intent, character)))
        if any(note for note in spec.unresolved if note):
            unresolved.extend(note for note in spec.unresolved if note)
        snapshot = self._snapshot(intent, character)
        plan = GenerationPlan(
            plan_id=plan_id,
            revision=revision,
            conversation_id=conversation_id,
            character_id=context.character_id,
            route=route,
            workflow=workflow,
            workflow_version=defaults["version"],
            workflow_bindings_hash=defaults["bindings"],
            asset_type=spec_route["asset_type"],
            title=self._title(route, intent),
            summary=self._summary(route, intent, context),
            status="draft",
            source_kind=source_kind,
            source_asset_id=source_asset_id,
            source_sha256=source_sha256,
            source_selection_revision=source_revision,
            character_template_id=intent.character_template_id,
            template_snapshot=snapshot,
            intent=intent.model_dump(),
            prompt=prompt,
            parameters=parameters,
            spec=spec.model_dump(),
            outfit_id=spec.outfit_id,
            keep=keep,
            change=change,
            allow_creative=allow,
            clarify=clarify,
            depends_on=[],
            unresolved=unresolved,
            content_hash="0" * 64,
            created=time.time(),
            updated=time.time(),
        )
        plan.content_hash = content_hash(plan.hashed_fields())
        plan.status = "awaiting_approval" if not (plan.unresolved or plan.clarify) else "draft"
        return plan

    def revise(
        self, plan_id: str, context: WorkbenchContext, intent: ProductionIntent
    ) -> GenerationPlan:
        """Any pre-approval change produces a new revision; the old card is superseded.

        The current state is read and the supersede is written inside one
        transaction, so an approval that lands in between cannot be overwritten by
        a stale "superseded" write.
        """
        current = self.get(plan_id)
        if current.status == "queued":
            raise PlannerError("计划已入队，不能修改；请准备新的计划")
        if current.status == "cancelled":
            raise PlannerError("计划已取消")
        updated = self.build(
            current.conversation_id, context, intent, plan_id, current.revision + 1
        )
        now = time.time()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("generation_plan", plan_id)
            ).fetchone()
            if not row:
                raise PlannerError("未知计划：" + str(plan_id))
            latest = plan_from(json.loads(row["body"]))
            if latest.status == "queued":
                raise PlannerError("计划已入队，不能修改；请准备新的计划")
            if latest.status == "cancelled":
                raise PlannerError("计划已取消")
            for old in self.revisions(plan_id):
                if old.status not in ("awaiting_approval", "draft"):
                    continue
                superseded = old.model_copy(update={"status": "superseded", "updated": now})
                db.execute(
                    "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                    (
                        "generation_plan_revision",
                        plan_id + ":" + str(old.revision),
                        json.dumps(
                            dict(superseded.model_dump(), plan_id=plan_id), ensure_ascii=False
                        ),
                    ),
                )
            if latest.status == "stale":
                updated = updated.model_copy(update={"status": "draft"})
            db.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                (
                    "generation_plan_revision",
                    plan_id + ":" + str(updated.revision),
                    json.dumps(dict(updated.model_dump(), plan_id=plan_id), ensure_ascii=False),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                ("generation_plan", plan_id, json.dumps(updated.model_dump(), ensure_ascii=False)),
            )
        return updated

    def mark_stale(self, plan_id: str, reason: str) -> GenerationPlan:
        plan = self.get(plan_id)
        if plan.status in ("queued", "cancelled", "superseded"):
            return plan
        updated = plan.model_copy(
            update={
                "status": "stale",
                "updated": time.time(),
                "unresolved": list(dict.fromkeys(plan.unresolved + [reason])),
            }
        )
        return self._persist(updated)

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _new_id() -> str:
        return "plan-" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:20]

    def _resolve_source(
        self,
        route: str,
        context: WorkbenchContext,
        character: dict[str, Any] | None,
        intent: ProductionIntent,
    ) -> tuple[str | None, str | None, int | None, str]:
        stages = ROUTE_SOURCE_STAGE[route]
        if not stages or intent.reference_mode == "none":
            return None, None, None, "none"
        # Most downstream selected stage first: it is the state the user is
        # looking at. `anima_free` must not drop a selected outfit image just
        # because an identity image is also selected.
        asset_id = None
        for stage in reversed(stages):
            asset_id = context.selected(stage)
            if asset_id:
                break
        if not asset_id:
            raise PlannerError("该路线需要工作台里已选定的图片，请先选图")
        asset = self.store.get("asset", asset_id)
        if not asset:
            raise PlannerError("选图不存在：" + asset_id)
        if asset.get("mode") != "RGB" or asset.get("role") not in ("original", "reference"):
            raise PlannerError("请选择原始 RGB 图片作为来源")
        if character and asset.get("scene_spec_id"):
            spec = self.store.get("scene_spec", asset["scene_spec_id"])
            if spec and spec.get("spec", {}).get("character_id") not in (
                None,
                context.character_id,
            ):
                raise PlannerError("这张图属于其他角色")
        if not asset.get("sha256"):
            raise PlannerError("来源图缺少 SHA256，无法冻结执行内容")
        # The source must pass the existing approval semantics.
        self._require_approved_source(route, context, asset, character)
        return asset_id, asset["sha256"], context.selection_revision, "selected_image"

    def _require_approved_source(
        self,
        route: str,
        context: WorkbenchContext,
        asset: dict[str, Any],
        character: dict[str, Any] | None,
    ) -> None:
        """The source image must satisfy the workbench's approval semantics.

        Which approval kinds count depends on the route: a pose image is approved
        as ``pose``, an outfit image as ``outfit`` or ``character``. Refusing them
        all would make the pose and expression routes unusable.
        """
        from ..workbench import Transaction

        if not character:
            return
        spec = (
            self.store.get("scene_spec", asset["scene_spec_id"])
            if asset.get("scene_spec_id")
            else None
        )
        outfit_id = (spec or {}).get("spec", {}).get("outfit_id")
        kinds = {
            "local_expression": ("pose", "outfit", "character"),
            "qwen_pose": ("outfit", "character"),
            "anima_matte": ("pose", "outfit", "character"),
        }.get(route, ("outfit", "character"))
        with self.store.connect() as db:
            db.execute("BEGIN")
            tx = Transaction(db)
            approved = any(
                tx.approved(asset["id"], kind, context.character_id, outfit_id) for kind in kinds
            )
        if not approved:
            raise PlannerError("来源图尚未被批准用于该角色，请先在工作台显式选用")

    def _pose_state_for(self, context: WorkbenchContext, intent) -> str:
        """The saved pose state this plan will generate from.

        The pose workflow takes a ``pose_asset_id`` pointing at a saved pose
        state, not at the selected image, so the plan has to resolve it. Without
        this the job would fail on a missing workflow input.

        An explicit ``intent.pose_asset_id`` wins: that is how the first pose
        image is produced, before any pose image exists to infer from. Otherwise
        the link runs through the job that produced the selected image (the
        workbench records ``pose_asset_id`` there), with a pose state whose render
        *is* the selected image as a fallback.
        """
        if intent is not None and intent.pose_asset_id:
            if not self.store.get("pose", intent.pose_asset_id):
                raise PlannerError("找不到已保存的姿态状态：" + intent.pose_asset_id)
            return intent.pose_asset_id
        pose_asset_id = context.selected("pose")
        if not pose_asset_id:
            raise PlannerError("请指定要使用的已保存姿态状态，或先在工作台选定姿态图")
        asset = self.store.get("asset", pose_asset_id) or {}
        if asset.get("job_id"):
            job = self.store.job(asset["job_id"])
            state_id = (job or {}).get("body", {}).get("pose_asset_id")
            if state_id and self.store.get("pose", state_id):
                return state_id
        for record in self.store.list("pose"):
            if record.get("render_asset_id") == pose_asset_id:
                return record["id"]
        raise PlannerError("找不到所选姿态图对应的已保存姿态状态，请重新保存姿态")

    def _build_spec(
        self,
        route: str,
        context: WorkbenchContext,
        intent: ProductionIntent,
        source_asset_id: str | None,
    ) -> SceneSpec:
        asset_type = ROUTES[route]["asset_type"]
        outfit_id = None
        if asset_type in ("outfit",):
            outfit_id = intent.outfit_id or context.selected_outfit_id
            if not outfit_id:
                raise PlannerError("换装路线需要指定服装版本")
        elif asset_type in ("pose", "expression", "free"):
            outfit_id = context.selected_outfit_id
        common = dict(
            action=intent.action,
            expression=intent.expression,
            scene=intent.scene,
            composition=intent.composition,
            description=" ".join(intent.allow_creative),
            prompt_captions=list(intent.prompt_captions),
            excluded_tags=list(intent.excluded_tags),
        )
        if asset_type == "background":
            return SceneSpec(
                asset_type="background",
                **common,
                canvas_preset=intent.canvas_preset or "1024x1536",
                visual_tags=list(intent.visual_tags),
            )
        if asset_type == "sprite":
            return SceneSpec(
                asset_type="sprite",
                character_id=context.character_id,
                outfit_id=outfit_id,
                **common,
                canvas_preset=intent.canvas_preset or context.canvas_preset or "1024x1536",
                visual_tags=list(intent.visual_tags),
            )
        if asset_type == "free":
            # No canvas_preset: the canvas is inherited from the source image.
            return SceneSpec(
                asset_type="free",
                character_id=context.character_id,
                outfit_id=outfit_id,
                **common,
                visual_tags=list(intent.visual_tags),
            )
        if asset_type == "outfit":
            return SceneSpec(
                asset_type="outfit",
                character_id=context.character_id,
                outfit_id=outfit_id,
                **common,
                visual_tags=list(intent.visual_tags),
            )
        if asset_type == "pose":
            self._pose_state_for(context, intent)
            return SceneSpec(
                asset_type="pose",
                character_id=context.character_id,
                outfit_id=outfit_id,
                action=intent.action or "new pose",
                scene=intent.scene,
                composition=intent.composition,
                prompt_captions=list(intent.prompt_captions),
                excluded_tags=list(intent.excluded_tags),
            )
        if asset_type == "expression":
            if not intent.expression.strip():
                raise PlannerError("表情路线需要明确的表情描述")
            return SceneSpec(
                asset_type="expression",
                character_id=context.character_id,
                outfit_id=outfit_id,
                expression=intent.expression,
                action=intent.action,
                scene=intent.scene,
                composition=intent.composition,
                prompt_captions=list(intent.prompt_captions),
                excluded_tags=list(intent.excluded_tags),
            )
        if asset_type == "matte":
            return SceneSpec(
                asset_type="matte", character_id=context.character_id, outfit_id=outfit_id
            )
        raise PlannerError("该路线暂不支持：" + route)

    def _parameters(
        self,
        route: str,
        context: WorkbenchContext,
        spec: SceneSpec,
        intent: ProductionIntent,
        source_asset_id: str | None,
        defaults: dict[str, Any],
        plan_id: str,
        revision: int,
    ) -> PlanParameters:
        # Seeds are concrete before the card is shown, and stable per revision.
        seeds = _seeds(plan_id, revision, intent.count)
        pose_asset_id = self._pose_state_for(context, intent) if route == "qwen_pose" else None
        if spec.asset_type == "free":
            asset = self.store.get("asset", source_asset_id)
            width, height = source_size(asset)
        elif spec.canvas_preset:
            width, height = preset_size(spec.canvas_preset)
        else:
            asset = self.store.get("asset", source_asset_id) if source_asset_id else None
            if not asset:
                raise PlannerError("该路线需要来源图来确定画布")
            width, height = source_size(asset)
        return PlanParameters(
            width=width,
            height=height,
            seeds=seeds,
            canvas_preset=spec.canvas_preset,
            pose_asset_id=pose_asset_id,
            **defaults["sampler"],
        )

    @staticmethod
    def _describe(
        context: WorkbenchContext, intent: ProductionIntent, route: str
    ) -> tuple[list[str], list[str], list[str]]:
        keep = ["角色身份与既有服装版本"]
        if ROUTES[route]["needs_source"]:
            keep.append("来源图的画布尺寸")
        keep.extend(intent.keep)
        change = list(intent.change)
        if intent.action:
            change.append("动作：" + intent.action[:80])
        if intent.scene:
            change.append("场景：" + intent.scene[:80])
        if not change:
            change.append("按描述重新整理提示词")
        return keep, change, list(intent.allow_creative)

    @staticmethod
    def _title(route: str, intent: ProductionIntent) -> str:
        label = ROUTES[route]["label"]
        if intent.action:
            return label + "：" + intent.action[:30]
        if intent.expression:
            return label + "：" + intent.expression[:30]
        return label

    @staticmethod
    def _summary(route: str, intent: ProductionIntent, context: WorkbenchContext) -> str:
        parts = [ROUTES[route]["semantic"]]
        if context.character_name:
            parts.append("角色：" + context.character_name)
        if intent.allow_creative:
            parts.append("允许发挥：" + "、".join(intent.allow_creative[:5]))
        if intent.clarify:
            parts.append("待澄清：" + "、".join(intent.clarify))
        return "；".join(parts)

    @staticmethod
    def _snapshot(intent: ProductionIntent, character: dict[str, Any] | None) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if intent.character_template_id:
            snapshot["character_template_id"] = intent.character_template_id
        if character:
            snapshot["character_id"] = character["id"]
            snapshot["fixed_tags"] = list(character.get("fixed_tags") or [])
            snapshot["outfit_ids"] = [o["id"] for o in character.get("outfits") or []]
        return snapshot
