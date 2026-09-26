"""Jobs endpoints with per-application dependencies."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from ..comfy import Comfy
from ..schema import JobRequest
from ..store import Store
from .common import required


def jobs_router(get_store: Callable[[], Store], get_comfy: Callable[[], Comfy]) -> APIRouter:
    router = APIRouter(tags=["Jobs"])

    @router.post("/jobs", status_code=201)
    async def create_job(body: JobRequest):
        store = get_store()
        # JobRequest forbids extra fields, so an agent-authored job body (frozen
        # prompt, authorization ID) can never enter here. Agent work reaches the
        # queue only through /agent/plans/{id}/approve, and the worker re-checks the
        # authorization record before executing anything.
        spec = required(store, "scene_spec", body.scene_spec_id)["spec"]
        if spec["unresolved"]:
            raise HTTPException(422, "Resolve ambiguous visual specification before generation")
        kind = spec["asset_type"]
        if kind in ("outfit", "pose", "expression", "matte"):
            if not body.reference_asset_id:
                raise HTTPException(422, "Reference required")
            a = required(store, "asset", body.reference_asset_id)
            if kind in ("outfit", "pose", "expression"):
                expected = "pose" if kind == "expression" else "character"
                approvals = store.list("approval")
                if not any(
                    x["asset_id"] == a["id"]
                    and x["kind"] in (("character", "outfit") if kind == "pose" else (expected,))
                    and x["character_id"] == spec["character_id"]
                    and (kind == "outfit" or x.get("outfit_id") == spec.get("outfit_id"))
                    for x in approvals
                ):
                    raise HTTPException(
                        422,
                        "Approved " + expected + " reference required for this character/outfit",
                    )
        if kind == "outfit" and not spec.get("outfit_id"):
            raise HTTPException(422, "Outfit version required")
        if kind == "pose":
            if not body.pose_asset_id:
                raise HTTPException(422, "Saved pose state required")
            required(store, "pose", body.pose_asset_id)
        if body.mask_asset_id:
            mask = required(store, "asset", body.mask_asset_id)
            ref = required(store, "asset", body.reference_asset_id)
            if (mask["width"], mask["height"]) != (ref["width"], ref["height"]):
                raise HTTPException(422, "Mask canvas must match reference")
        try:
            return store.create_job(body.model_dump())
        except ValueError as e:
            raise HTTPException(409, str(e))

    @router.get("/jobs")
    async def jobs():
        store = get_store()
        return store.jobs()

    @router.get("/jobs/{id}")
    async def job(id: str):
        store = get_store()
        j = store.job(id)
        if not j:
            raise HTTPException(404, "Unknown job")
        return dict(
            j,
            output_assets=[
                dict(required(store, "asset", a), download_url="/assets/" + a + "/file")
                for a in j["outputs"]
            ],
        )

    @router.post("/jobs/{id}/cancel")
    async def cancel(id: str):
        store = get_store()
        j = await job(id)
        if j["state"] == "queued":
            store.update_job(id, state="cancelled")
            return store.job(id)
        if j["state"] in ("running", "recovering") and j["prompt_id"]:
            if await get_comfy().cancel_pending(j["prompt_id"]):
                store.update_job(id, state="cancelled")
                return store.job(id)
        raise HTTPException(
            409, "Job not safely cancellable. Running inference is not globally interrupted."
        )

    @router.get("/approvals")
    async def approvals():
        store = get_store()
        return store.list("approval")

    @router.get("/jobs/{id}/record")
    async def generation_record(id: str):
        store = get_store()
        j = await job(id)
        return {
            "job": j,
            "execution": store.get("execution", id),
            "history": store.get("history", id),
            "validation": store.get("validation", id),
        }

    return router
