"""Shared record validation at the HTTP boundary."""

from typing import Any

from fastapi import HTTPException

from ..schema import SceneSpec
from ..store import Store


def required(store: Store, kind: str, record_id: str | None) -> dict[str, Any]:
    record = store.get(kind, record_id)
    if record is None:
        raise HTTPException(404, f"Unknown {kind}: {record_id}")
    return record


def validate_spec(store: Store, spec: SceneSpec) -> SceneSpec:
    if spec.character_id:
        character = required(store, "character", spec.character_id)
        if spec.outfit_id and spec.outfit_id not in {x["id"] for x in character["outfits"]}:
            raise HTTPException(422, "Unknown outfit")
    return spec
