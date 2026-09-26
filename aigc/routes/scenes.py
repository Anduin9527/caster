"""Scenes endpoints with per-application dependencies."""

import sqlite3
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from ..llm import parse_scene
from ..schema import Character, PoseState, SceneRequest, SceneSpec
from ..store import Store
from .common import required, validate_spec


def scenes_router(get_store: Callable[[], Store], config: dict[str, str]) -> APIRouter:
    router = APIRouter(tags=["Scenes"])

    @router.post("/characters", status_code=201)
    async def create_character(body: Character):
        store = get_store()
        try:
            return store.put("character", body.model_dump(), body.id)
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "Character exists; immutable identity requires a new character ID"
            )

    @router.get("/characters")
    async def characters():
        store = get_store()
        return store.list("character")

    @router.get("/characters/{id}")
    async def character(id: str):
        store = get_store()
        return required(store, "character", id)

    @router.post("/scene-specs", status_code=201)
    async def scene_specs(body: SceneRequest):
        store = get_store()
        metadata = {"source": "manual"}
        if body.manual:
            spec = validate_spec(store, body.manual)
        else:
            c = required(store, "character", body.character_id) if body.character_id else None
            if body.outfit_id and (not c or body.outfit_id not in {x["id"] for x in c["outfits"]}):
                raise HTTPException(422, "Unknown outfit")
            try:
                spec, metadata = await parse_scene(body, c, config)
            except RuntimeError as e:
                raise HTTPException(503, str(e))
            except Exception:
                raise HTTPException(
                    502, "LLM request or schema correction failed; check server configuration"
                )
            validate_spec(store, spec)
        return store.put("scene_spec", {"spec": spec.model_dump(), "metadata": metadata})

    @router.get("/scene-specs/{id}")
    async def get_spec(id: str):
        store = get_store()
        return required(store, "scene_spec", id)

    @router.put("/scene-specs/{id}")
    async def revise_spec(id: str, body: SceneSpec):
        store = get_store()
        required(store, "scene_spec", id)
        validate_spec(store, body)
        # Immutable revision: existing jobs keep their exact submitted specification.
        return store.put(
            "scene_spec",
            {
                "spec": body.model_dump(),
                "metadata": {"source": "manual-revision", "parent_spec_id": id},
            },
        )

    @router.post("/poses", status_code=201)
    async def poses(body: PoseState):
        store = get_store()
        a = required(store, "asset", body.render_asset_id)
        if a["role"] != "pose_render":
            raise HTTPException(422, "Requires pose_render asset")
        return store.put("pose", body.model_dump())

    @router.get("/poses")
    async def list_poses():
        store = get_store()
        return store.list("pose")

    return router
