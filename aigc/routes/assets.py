"""Assets endpoints with per-application dependencies."""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from ..assets import asset_path, save_image
from ..schema import Approval
from ..store import Store
from ..thumbnails import thumbnail
from .common import required


def assets_router(get_store: Callable[[], Store]) -> APIRouter:
    router = APIRouter(tags=["Assets"])

    @router.post("/assets", status_code=201)
    async def upload_asset(file: UploadFile = File(...), role: str = Form("reference")):
        store = get_store()
        if role not in ("reference", "mask", "pose_render"):
            raise HTTPException(422, "Invalid upload role")
        try:
            return save_image(
                store, await file.read(64 * 1024 * 1024 + 1), {"role": role, "source": "upload"}
            )
        except Exception as e:
            raise HTTPException(422, str(e))

    @router.get("/assets")
    async def assets():
        store = get_store()
        return store.list("asset")

    @router.get("/assets/{id}")
    async def asset(id: str):
        store = get_store()
        a = required(store, "asset", id)
        return dict(a, download_url="/assets/" + id + "/file")

    @router.get("/assets/{id}/file")
    async def asset_file(id: str):
        store = get_store()
        return FileResponse(
            asset_path(store, required(store, "asset", id)),
            media_type="image/png",
            filename=id + ".png",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @router.get("/assets/{id}/thumbnail")
    def asset_thumbnail(id: str, request: Request, size: Literal["384", "768", "1536"] = "384"):
        store = get_store()
        a = required(store, "asset", id)
        path = asset_path(store, a)
        version = a.get("sha256") or str(path.stat().st_mtime_ns)
        etag = f'"thumb-v2-{size}-{version}"'
        headers = {"Cache-Control": "private, max-age=31536000, immutable", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(thumbnail(str(path), version, int(size)), media_type="image/webp", headers=headers)

    @router.post("/assets/{id}/approve")
    async def approve(id: str, body: Approval):
        store = get_store()
        a = required(store, "asset", id)
        c = required(store, "character", body.character_id)
        from ..workbench import Transaction

        try:
            with store.connect() as db:
                Transaction(db).image(id, body.character_id)
        except (LookupError, ValueError) as e:
            raise HTTPException(422, str(e))
        if body.kind in ("outfit", "pose") and not a.get("scene_spec_id"):
            raise HTTPException(422, "Approval requires a generated result of this type")
        if body.outfit_id and body.outfit_id not in {o["id"] for o in c["outfits"]}:
            raise HTTPException(422, "Unknown outfit")
        if a["role"] in ("mask", "crop", "pose_render", "transparent") or a["mode"] == "RGBA":
            raise HTTPException(422, "Approval requires original RGB character image")
        if a.get("scene_spec_id"):
            spec = required(store, "scene_spec", a["scene_spec_id"])["spec"]
            if (spec.get("character_id"), spec.get("outfit_id")) != (
                body.character_id,
                body.outfit_id,
            ):
                raise HTTPException(422, "Approval identity differs from generation identity")
            if body.kind in ("outfit", "pose") and spec["asset_type"] != body.kind:
                raise HTTPException(422, "Approval requires a matching result type")
            if body.kind == "character" and spec["asset_type"] != "sprite":
                raise HTTPException(422, "Character approval requires an identity result")
        return store.put("approval", dict(body.model_dump(), asset_id=id))

    return router
