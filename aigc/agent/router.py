"""The ``/agent`` HTTP surface: settings, conversations, messages, events, plans.

Approve is the only endpoint that can create GPU work, and it goes through
:func:`aigc.agent.authorize.approve` — never through the legacy ``/jobs`` route.
"""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .authorize import ApprovalConflict, ApprovalError, approve, cancel
from .contracts import WorkbenchContext
from .planner import Planner, PlannerError
from .sessions import Conversation
from .settings import (
    SettingsError,
    clear,
    list_models,
    provider_presets,
    resolve,
    save,
    test_connection,
)


class SettingsBody(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    provider: str = "custom"
    remember: bool = True
    keep_existing_key: bool = False


class ConversationBody(BaseModel):
    character_id: str | None = None
    title: str = Field(default="", max_length=200)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    context: WorkbenchContext
    idempotency_key: str | None = Field(default=None, max_length=128)


class ApproveBody(BaseModel):
    revision: int = Field(ge=0)
    content_hash: str = Field(default="", max_length=128)
    selection_revision: int | None = None


class WorkbenchChangeApprovalBody(BaseModel):
    content_hash: str = Field(min_length=64, max_length=64)


async def sse_frames(
    events_since,
    conversation_id: str,
    cursor: str,
    is_disconnected,
    idle_sleep: float = 0.1,
    heartbeat: float = 15.0,
):
    """Yield SSE frames for a conversation, resuming from ``cursor``.

    Kept as a free function so the streaming contract (id/data framing, cursor
    advance, stop on disconnect) is testable without an endless HTTP body.
    """
    last_write = time.monotonic()
    while True:
        if await is_disconnected():
            return
        try:
            events = events_since(conversation_id, cursor)
        except LookupError:
            return
        for event in events:
            cursor = event.event_id
            yield (
                "id: "
                + cursor
                + "\ndata: "
                + json.dumps(event.model_dump(), ensure_ascii=False)
                + "\n\n"
            )
            last_write = time.monotonic()
        if not events:
            if time.monotonic() - last_write >= heartbeat:
                yield ": keep-alive\n\n"
                last_write = time.monotonic()
            await asyncio.sleep(idle_sleep)


def agent_router(engine, config):
    """Build routes over the application's lazy AgentEngine provider."""
    router = APIRouter(prefix="/agent", tags=["Agent"])
    config = dict(config)

    def get_store():
        return engine().store

    def sessions() -> Conversation:
        return Conversation(get_store())

    def planner() -> Planner:
        return Planner(get_store())

    def fail(error: Exception, status: int = 400) -> HTTPException:
        return HTTPException(status, str(error)[:500])

    # -- settings ----------------------------------------------------------- #
    @router.get("/settings")
    def read_settings():
        settings = resolve(config)
        payload = settings.public()
        payload["providers"] = provider_presets()
        payload["agent_enabled"] = bool(
            config.get("AIGC_AGENT_ENABLED", "1") not in ("0", "false", "no")
        )
        return payload

    @router.put("/settings")
    def write_settings(body: SettingsBody):
        try:
            settings = save(
                config,
                body.base_url,
                body.api_key,
                body.model,
                body.provider,
                body.remember,
                body.keep_existing_key,
            )
        except SettingsError as error:
            raise fail(error, 422)
        return settings.public()

    @router.delete("/settings")
    def delete_settings():
        return clear(config).public()

    @router.post("/settings/models")
    async def read_models():
        return await list_models(resolve(config))

    @router.post("/settings/test")
    async def post_test():
        return await test_connection(resolve(config))

    # -- conversations ------------------------------------------------------ #
    @router.post("/conversations", status_code=201)
    def create_conversation(body: ConversationBody):
        return sessions().create(body.character_id, body.title)

    @router.get("/conversations")
    def list_conversations(character_id: str | None = None):
        return sessions().list_conversations(character_id)

    @router.get("/conversations/{conversation_id}")
    def read_conversation(conversation_id: str):
        try:
            conversation = sessions().get(conversation_id)
        except LookupError as error:
            raise fail(error, 404)
        plans = planner().latest_for(conversation_id)
        from .workbench_changes import list_for_conversation, public_change

        return {
            "conversation": conversation,
            "messages": sessions().history(conversation_id),
            "runs": sessions().runs(conversation_id),
            "plans": [p.model_dump() for p in plans],
            "workbench_changes": [
                public_change(value)
                for value in list_for_conversation(get_store(), conversation_id)
            ],
            "events": [e.model_dump() for e in engine().events.latest(conversation_id)],
        }

    @router.put("/conversations/{conversation_id}/character")
    def rebind_character(conversation_id: str, body: ConversationBody):
        try:
            return sessions().rebind(conversation_id, body.character_id)
        except LookupError as error:
            raise fail(error, 404)

    @router.post("/conversations/{conversation_id}/messages")
    async def post_message(conversation_id: str, body: MessageBody):
        try:
            outcome = await engine().run_message(
                conversation_id, body.text, body.context, idempotency_key=body.idempotency_key
            )
        except LookupError as error:
            raise fail(error, 404)
        except RuntimeError as error:
            raise fail(error, 409)
        except ValueError as error:
            raise fail(error, 422)
        return {
            "run_id": outcome.run_id,
            "status": outcome.status,
            "error": outcome.error,
            "events": [e.model_dump() for e in engine().events.since(conversation_id)],
        }

    @router.get("/conversations/{conversation_id}/events")
    async def stream_events(conversation_id: str, request: Request, after: str = ""):
        cursor = request.headers.get("last-event-id") or after
        try:
            sessions().get(conversation_id)
            engine().events.since(conversation_id, cursor)
        except LookupError as error:
            raise fail(error, 404)

        return StreamingResponse(
            sse_frames(engine().events.since, conversation_id, cursor, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # -- runs --------------------------------------------------------------- #
    @router.post("/runs/{run_id}/stop")
    async def stop_run(run_id: str):
        try:
            return engine().stop(run_id)
        except LookupError as error:
            raise fail(error, 404)

    # -- plans -------------------------------------------------------------- #
    @router.get("/plans/{plan_id}")
    def read_plan(plan_id: str):
        try:
            return planner().get(plan_id).model_dump()
        except PlannerError as error:
            raise fail(error, 404)

    @router.get("/plans/{plan_id}/revisions")
    def read_revisions(plan_id: str):
        return [p.model_dump() for p in planner().revisions(plan_id)]

    @router.patch("/plans/{plan_id}")
    def revise_plan(plan_id: str, body: dict[str, Any]):
        from .contracts import ProductionIntent

        try:
            plan = planner().get(plan_id)
            fields = {k: v for k, v in body.items() if k != "context"}
            # Merge into the intent the card was built from: a partial patch that
            # only changes the candidate count must keep the original action,
            # scene and composition.
            merged = {**(plan.intent or {}), **fields}
            # The route belongs to the existing plan; a caller cannot switch it.
            merged["route"] = plan.route
            intent = ProductionIntent.model_validate(merged)
            context = WorkbenchContext.model_validate(body.get("context") or {})
            return planner().revise(plan_id, context, intent).model_dump()
        except (PlannerError, ValueError) as error:
            raise fail(error, 422)

    @router.post("/plans/{plan_id}/approve")
    def approve_plan(plan_id: str, body: ApproveBody):
        try:
            plan, authorization = approve(
                get_store(), plan_id, body.revision, body.content_hash, body.selection_revision
            )
        except ApprovalConflict as error:
            try:
                planner().mark_stale(plan_id, str(error))
            except PlannerError:
                pass
            raise fail(error, 409)
        except ApprovalError as error:
            raise fail(error, 422)
        engine().events.append(
            plan.conversation_id,
            None,
            "jobs.queued",
            {
                "plan_id": plan_id,
                "revision": plan.revision,
                "job_ids": plan.job_ids,
                "authorization_id": authorization["authorization_id"],
            },
        )
        return {"plan": plan.model_dump(), "authorization": authorization}

    @router.post("/plans/{plan_id}/cancel")
    def cancel_plan(plan_id: str):
        try:
            planner().get(plan_id)
        except PlannerError as error:
            raise fail(error, 404)
        try:
            return cancel(get_store(), plan_id).model_dump()
        except ApprovalError as error:
            raise fail(error, 409)

    # -- reusable workbench changes --------------------------------------- #
    @router.post("/workbench-changes/{change_id}/approve")
    def approve_workbench_change(change_id: str, body: WorkbenchChangeApprovalBody):
        from .workbench_changes import WorkbenchChangeConflict, WorkbenchChangeError, public_change
        from .workbench_changes import approve as approve_change

        try:
            change = approve_change(get_store(), change_id, body.content_hash)
        except WorkbenchChangeConflict as error:
            raise fail(error, 409)
        except WorkbenchChangeError as error:
            raise fail(error, 422)
        engine().events.append(
            change.conversation_id,
            None,
            "workbench.updated",
            {
                "change_id": change.change_id,
                "character_id": change.character_id,
                "character_name": change.character_name,
                "focus": change.focus,
                "reason": "用户已批准工作台变更",
            },
        )
        return public_change(change)

    @router.post("/workbench-changes/{change_id}/cancel")
    def cancel_workbench_change(change_id: str):
        from .workbench_changes import WorkbenchChangeConflict, WorkbenchChangeError, public_change
        from .workbench_changes import cancel as cancel_change

        try:
            return public_change(cancel_change(get_store(), change_id))
        except WorkbenchChangeConflict as error:
            raise fail(error, 409)
        except WorkbenchChangeError as error:
            raise fail(error, 404)

    # -- retrieval index ----------------------------------------------------- #
    @router.get("/index/status")
    def index_status(request: Request):
        """Is semantic search usable, and is the template collection current?

        The sync half reports the dirty count and the last failure, because a
        stale template collection is invisible to the caller otherwise: a search
        would simply not return the template they just created.
        """
        from ..rag import RagSettings, RagUnavailable

        payload: dict = {}
        try:
            settings = RagSettings(config)
            payload["index_version"] = str(config.get("AIGC_RAG_INDEX_VERSION") or "")
            payload["matches_published_index"] = settings.matches_published_index()
            payload["mismatch_reason"] = settings.mismatch_reason()
            payload["published_collections"] = settings.published_collections()
        except RagUnavailable as error:
            return {
                "semantic_available": False,
                "semantic_reason": str(error),
                "matches_published_index": False,
            }
        sync = getattr(request.app.state, "template_sync", None)
        if sync is None:
            # Not running under the API lifespan (tests, or a bare ASGI app).
            from ..rag import build_writer
            from .template_sync import TemplateSync

            sync = TemplateSync(get_store(), build_writer(config))
        payload["semantic_available"] = True
        payload["template_sync"] = sync.status()
        return payload

    @router.post("/index/sync")
    def index_sync_now(request: Request):
        """Drain the template queue now. The explicit "make it current" action."""
        from ..rag import build_writer
        from .template_sync import TemplateSync

        sync = getattr(request.app.state, "template_sync", None) or TemplateSync(
            get_store(), build_writer(config)
        )
        return sync.drain_once()

    @router.post("/index/rebuild")
    def index_rebuild(request: Request):
        """Re-mark every template so the next drain rewrites the whole collection.

        This does not delete or rebuild the collection: it is the explicit entry
        point for "the index may be wrong, re-derive it from the business store".
        """
        from ..rag import build_writer
        from .template_sync import TemplateSync

        sync = getattr(request.app.state, "template_sync", None) or TemplateSync(
            get_store(), build_writer(config)
        )
        return {"marked": sync.enqueue_all(), "drain": sync.drain_once()}

    return router
