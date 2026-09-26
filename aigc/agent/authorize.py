"""Approval, generation authorization and idempotent enqueue.

The invariant this module exists to protect: **no GPU work without an explicit
user approval, and the executed content equals the approved content.** A card is
approved against a plan revision and its content hash; the transaction re-checks
the plan state, the input asset and the workbench selection revision, then writes
the authorization record and its jobs atomically. A double click or a replayed
request returns the same batch instead of a second one.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .contracts import GenerationPlan, plan_from

ROOT = Path(__file__).resolve().parents[2]


class ApprovalError(ValueError):
    pass


class ApprovalConflict(ApprovalError):
    """The card no longer matches reality and must be re-prepared."""


def authorization_id(plan_id: str, revision: int, content_hash: str) -> str:
    return (
        "auth-"
        + hashlib.sha256((plan_id + ":" + str(revision) + ":" + content_hash).encode()).hexdigest()[
            :24
        ]
    )


def get_authorization(store, auth_id: str) -> dict[str, Any] | None:
    return store.get("generation_authorization", auth_id)


def authorizations_for(store, plan_id: str) -> list[dict[str, Any]]:
    return [r for r in store.list("generation_authorization") if r.get("plan_id") == plan_id]


def _job_body(
    plan: GenerationPlan, spec_id: str, seed: int, auth_id: str, index: int
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "scene_spec_id": spec_id,
        "seed": seed,
        "idempotency_key": "plan:" + auth_id + ":" + str(index),
        # Frozen execution snapshot. The worker must run exactly this prompt.
        "agent_plan_id": plan.plan_id,
        "agent_plan_revision": plan.revision,
        "agent_content_hash": plan.content_hash,
        "agent_authorization_id": auth_id,
        "agent_prompt": plan.prompt,
        "agent_workflow": plan.workflow,
        "agent_workflow_version": plan.workflow_version,
    }
    if plan.source_kind == "selected_image" and plan.source_asset_id:
        body["reference_asset_id"] = plan.source_asset_id
    if plan.parameters.pose_asset_id:
        body["pose_asset_id"] = plan.parameters.pose_asset_id
    if plan.parameters.mask_asset_id:
        body["mask_asset_id"] = plan.parameters.mask_asset_id
    if plan.parameters.face_region:
        body["face_region"] = list(plan.parameters.face_region)
    return body


def _workflow_snapshot(workflow: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Read the graph and its field bindings, and hash both.

    The hashes must equal the plan's ``workflow_version`` and
    ``workflow_bindings_hash``; a mismatch means the installed workflow changed
    between planning and approving, which the caller must refuse rather than
    silently execute something else. Both the graph and the bindings are frozen:
    the bindings decide which node receives the prompt, so freezing only the
    graph would still let execution drift.
    """
    from ..workflows import digest, read_bindings, read_template

    try:
        graph = read_template(workflow)
        bindings = read_bindings(workflow)
    except ValueError as error:
        raise ApprovalError(str(error))
    return graph, bindings, digest(graph), digest(bindings)


def _verify_source(db, plan: GenerationPlan) -> None:
    """Re-read the live store; a changed input invalidates the card.

    Uses the caller's transaction connection, so the source asset and the
    workbench selection are read from the same snapshot that will be written.
    """
    if plan.source_kind != "selected_image" or not plan.source_asset_id:
        return
    row = db.execute(
        "SELECT body FROM records WHERE kind=? AND id=?", ("asset", plan.source_asset_id)
    ).fetchone()
    if not row:
        raise ApprovalConflict("来源图已被删除，需要重新准备计划")
    if json.loads(row["body"]).get("sha256") != plan.source_sha256:
        raise ApprovalConflict("来源图内容已变化，需要重新准备计划")
    if not plan.character_id:
        return
    from ..workbench import Transaction

    try:
        selection = Transaction(db).selection(plan.character_id)
    except LookupError:
        raise ApprovalConflict("角色已不存在，需要重新准备计划")
    if (
        plan.source_selection_revision is not None
        and selection["revision"] != plan.source_selection_revision
    ):
        raise ApprovalConflict(
            "工作台选图已变化（revision %s → %s），请重新确认后再批准"
            % (plan.source_selection_revision, selection["revision"])
        )


def approve(
    store,
    plan_id: str,
    revision: int,
    expected_content_hash: str = "",
    expected_selection_revision: int | None = None,
) -> tuple[GenerationPlan, dict[str, Any]]:
    """Validate, authorize and atomically enqueue. Idempotent per (plan, revision, hash).

    The pre-transaction read only produces fast, readable errors for what the
    caller already told us. Every authoritative check — plan status, content hash,
    source asset, selection revision, workflow version — is repeated inside the
    ``BEGIN IMMEDIATE`` transaction, because a concurrent cancel or revision can
    land between the two reads.
    """
    record = store.get("generation_plan_revision", plan_id + ":" + str(revision))
    if not record:
        raise ApprovalError("未知计划版本：" + str(plan_id) + ":" + str(revision))
    plan = plan_from(record)
    if expected_content_hash and expected_content_hash != plan.content_hash:
        raise ApprovalConflict("计划内容已被修改，请刷新审批卡")
    if (
        expected_selection_revision is not None
        and plan.source_selection_revision is not None
        and expected_selection_revision != plan.source_selection_revision
    ):
        raise ApprovalConflict("审批卡基于旧的选图版本，请刷新后重试")
    auth_id = authorization_id(plan_id, revision, plan.content_hash)

    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("generation_authorization", auth_id)
        ).fetchone()
        if existing:
            # Double click / replay: return the very same batch, but only if the
            # stored plan still hashes to what was authorized.
            authorization = json.loads(existing["body"])
            stored = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("generation_plan", plan_id)
            ).fetchone()
            if (
                stored
                and plan_from(json.loads(stored["body"])).content_hash
                != authorization["content_hash"]
            ):
                raise ApprovalConflict("计划内容在批准后被修改，请重新准备计划")
            return plan_from(json.loads(stored["body"])), authorization
        # Re-read inside the write lock: this is the state that will be executed.
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?",
            ("generation_plan_revision", plan_id + ":" + str(revision)),
        ).fetchone()
        if not row:
            raise ApprovalError("未知计划版本：" + str(plan_id) + ":" + str(revision))
        plan = plan_from(json.loads(row["body"]))
        if plan.status == "queued":
            prior = [
                json.loads(r["body"])
                for r in db.execute(
                    "SELECT body FROM records WHERE kind='generation_authorization'"
                )
            ]
            prior = [
                a
                for a in prior
                if a.get("plan_id") == plan_id and a.get("plan_revision") == revision
            ]
            if prior:
                # An authorization exists for this revision; if the stored plan no
                # longer matches it, the executed content would differ from what
                # the user approved.
                if prior[0]["content_hash"] != plan.content_hash:
                    raise ApprovalConflict("计划内容在批准后被修改，请重新准备计划")
                stored = db.execute(
                    "SELECT body FROM records WHERE kind=? AND id=?", ("generation_plan", plan_id)
                ).fetchone()
                return plan_from(json.loads(stored["body"])), prior[0]
            raise ApprovalConflict("计划已入队但没有授权记录，需要人工核对")
        if plan.status != "awaiting_approval":
            raise ApprovalConflict("计划当前状态为 " + plan.status + "，不能批准")
        if plan.unresolved:
            raise ApprovalError("计划仍有未解决项：" + "、".join(plan.unresolved[:5]))
        _verify_source(db, plan)
        graph, bindings, graph_digest, bindings_digest = _workflow_snapshot(plan.workflow)
        if graph_digest != plan.workflow_version:
            raise ApprovalConflict("工作流已在准备后被修改，请重新准备计划")
        if bindings_digest != plan.workflow_bindings_hash:
            if not plan.workflow_bindings_hash:
                # A card prepared before the bindings digest existed carries no
                # binding version at all; it cannot be matched, so re-prepare it.
                raise ApprovalConflict("计划创建于旧版本，未记录字段绑定版本，请重新准备计划")
            raise ApprovalConflict("工作流字段绑定已在准备后被修改，请重新准备计划")
        spec_id = uuid.uuid4().hex
        spec_body = {
            "spec": plan.spec,
            "metadata": {
                "source": "agent-plan",
                "plan_id": plan_id,
                "plan_revision": revision,
                "content_hash": plan.content_hash,
                "conversation_id": plan.conversation_id,
            },
        }
        db.execute(
            "INSERT INTO records VALUES(?,?,?)",
            ("scene_spec", spec_id, json.dumps(spec_body, ensure_ascii=False)),
        )
        job_ids = []
        now = time.time()
        for index, seed in enumerate(plan.parameters.seeds):
            body = _job_body(plan, spec_id, seed, auth_id, index)
            row = db.execute(
                "SELECT id FROM jobs WHERE idempotency_key=?", (body["idempotency_key"],)
            ).fetchone()
            if row:
                job_ids.append(row["id"])
                continue
            job_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO jobs(id,idempotency_key,body,state,created,updated) VALUES(?,?,?,?,?,?)",
                (job_id, body["idempotency_key"], json.dumps(body), "queued", now, now),
            )
            job_ids.append(job_id)
        authorization = {
            "authorization_id": auth_id,
            "plan_id": plan_id,
            "plan_revision": revision,
            "content_hash": plan.content_hash,
            "conversation_id": plan.conversation_id,
            "character_id": plan.character_id,
            "workflow": plan.workflow,
            "workflow_version": plan.workflow_version,
            "workflow_bindings_hash": plan.workflow_bindings_hash,
            # The executable graph and bindings as they were when the
            # user approved it. Editing workflows/*.api.json or
            # bindings.json afterwards cannot change this.
            "workflow_graph": graph,
            "workflow_bindings": bindings,
            "job_ids": job_ids,
            "approved_at": now,
            "approved_by": "user",
            "source_asset_id": plan.source_asset_id,
            "source_sha256": plan.source_sha256,
            "source_selection_revision": plan.source_selection_revision,
        }
        db.execute(
            "INSERT INTO records VALUES(?,?,?)",
            ("generation_authorization", auth_id, json.dumps(authorization, ensure_ascii=False)),
        )
        queued = plan.model_copy(
            update={
                "status": "queued",
                "job_ids": job_ids,
                "authorization_id": auth_id,
                "updated": now,
            }
        )
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            (
                "generation_plan_revision",
                plan_id + ":" + str(revision),
                json.dumps(dict(queued.model_dump(), plan_id=plan_id), ensure_ascii=False),
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            ("generation_plan", plan_id, json.dumps(queued.model_dump(), ensure_ascii=False)),
        )
    return queued, authorization


def cancel(store, plan_id: str, revision: int | None = None) -> GenerationPlan:
    """Cancel a plan that has not been queued. Queued plans use the job cancel path.

    The status is read and written inside one ``BEGIN IMMEDIATE`` transaction: an
    approval that lands between a plain read and write-back would otherwise leave
    the plan marked cancelled while its jobs stay queued.
    """
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("generation_plan", plan_id)
        ).fetchone()
        if not row:
            raise ApprovalError("未知计划：" + str(plan_id))
        plan = plan_from(json.loads(row["body"]))
        if revision is not None and plan.revision != revision:
            raise ApprovalConflict("计划已有更新版本，请刷新后再操作")
        if plan.status == "queued":
            raise ApprovalConflict("计划已入队，请取消对应任务")
        if plan.status == "cancelled":
            return plan
        cancelled = plan.model_copy(update={"status": "cancelled", "updated": time.time()})
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            (
                "generation_plan_revision",
                plan_id + ":" + str(cancelled.revision),
                json.dumps(dict(cancelled.model_dump(), plan_id=plan_id), ensure_ascii=False),
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            ("generation_plan", plan_id, json.dumps(cancelled.model_dump(), ensure_ascii=False)),
        )
    return cancelled
