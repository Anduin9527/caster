import hashlib
import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .template_previews import cache_path
from .template_translation import dictionary, display_for, lookup, searchable
from .templates import (
    PromptTemplate,
    TemplateBundle,
    TemplateConflict,
    TemplateSelection,
    import_bundle,
    materialize,
)


def _template_written(store, template_id: str) -> None:
    """A template changed: refresh the local index and mark it for re-indexing.

    The BM25 revision and the semantic dirty marker are written in the same
    place, so a template edit can never be visible to one path and not the other.
    The marker is durable and cheap; the vector write happens in the background
    drain, which never blocks a request.
    """
    from .agent.retrieval import bump_template_revision
    from .agent.template_sync import mark_template_dirty

    bump_template_revision(store)
    mark_template_dirty(store, template_id, "upsert")


def template_router(get_store):
    router = APIRouter(prefix="/prompt-templates", tags=["Prompt templates"])

    @router.get("")
    def list_templates(
        request: Request,
        kind: Literal["character", "outfit"] | None = None,
        q: str = "",
        category: str | None = None,
        source: Literal["upstream", "user"] | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ):
        rows = get_store().list("prompt_template")
        rows = [
            r
            for r in rows
            if (not kind or r["kind"] == kind)
            and (not source or (r.get("source") == "user") == (source == "user"))
        ]
        categories = sorted({c for r in rows for c in r.get("categories", [])})
        words = dictionary(get_store())
        rows = [r for r in rows if not category or category in r.get("categories", [])]
        if q:
            rows = [r for r in rows if searchable(r, display_for(r, words), q)]
        items = [dict(r, display=display_for(r, words)) for r in rows[offset : offset + limit]]
        payload = json.dumps(
            {
                "total": len(rows),
                "items": items,
                "categories": categories,
                "category_labels": {
                    c: lookup(words, c, 3) if kind == "character" else "" for c in categories
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        etag = '"' + hashlib.sha256(payload).hexdigest() + '"'
        headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(payload, media_type="application/json", headers=headers)

    @router.post("", status_code=201)
    async def create(body: PromptTemplate):
        try:
            record = get_store().put("prompt_template", body.model_dump(), body.id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Template exists; use PUT to edit")
        _template_written(get_store(), body.id)
        return record

    @router.post("/import")
    async def upload(file: UploadFile = File(...)):
        raw = await file.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise HTTPException(413, "Template bundle exceeds 16 MiB")
        try:
            bundle = TemplateBundle.model_validate_json(raw)
            return import_bundle(get_store(), bundle)
        except TemplateConflict as e:
            raise HTTPException(409, str(e))
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid template bundle; see schema_version=1 format")

    @router.get("/export")
    async def export():
        return {"schema_version": 1, "templates": get_store().list("prompt_template")}

    def selection_result(body):
        try:
            return materialize(get_store(), body)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @router.post("/preview")
    async def preview(body: TemplateSelection):
        return selection_result(body)

    @router.post("/instantiate", status_code=201)
    async def instantiate(body: TemplateSelection):
        result = selection_result(body)
        try:
            result["character"] = get_store().put(
                "character", result["character"], body.character_id
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Character exists; choose a new character ID")
        return result

    @router.get("/{id}/image")
    def preview_image(id: str, request: Request):
        row = get_store().get("prompt_template", id)
        if not row:
            raise HTTPException(404, "Unknown template", headers={"Cache-Control": "no-store"})
        path = cache_path(get_store(), row)
        if path is None or not path.is_file():
            raise HTTPException(
                404, "Template preview not cached", headers={"Cache-Control": "no-store"}
            )
        etag = '"' + path.stem + '"'
        headers = {"Cache-Control": "private, max-age=31536000, immutable", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return FileResponse(path, media_type="image/webp", headers=headers)

    @router.get("/{id}")
    async def get(id: str):
        row = get_store().get("prompt_template", id)
        if row is None:
            raise HTTPException(404, "Unknown template")
        return row

    @router.put("/{id}")
    async def edit(id: str, body: PromptTemplate):
        old = await get(id)
        if body.id != id or body.kind != old["kind"]:
            raise HTTPException(422, "Template ID and kind cannot change")
        record = get_store().put("prompt_template", body.model_dump(), id, replace=True)
        _template_written(get_store(), id)
        return record

    return router
