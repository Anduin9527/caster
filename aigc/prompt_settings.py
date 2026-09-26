"""Persisted runtime prompt preferences, separate from reusable templates."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Annotated

from fastapi import APIRouter
from pydantic import Field

from .anima_defaults import DEFAULT_ARTIST_STYLE, DEFAULT_FIXED_NEGATIVE, DEFAULT_FIXED_POSITIVE
from .schema import Strict

PromptText = Annotated[str, Field(max_length=12000)]
SETTINGS_ID = "anima"


class PromptSettingsUpdate(Strict):
    artist_style: PromptText = DEFAULT_ARTIST_STYLE
    fixed_positive: PromptText = DEFAULT_FIXED_POSITIVE
    fixed_negative: PromptText = DEFAULT_FIXED_NEGATIVE


def _canonical(value: dict) -> dict:
    return {
        key: str(value.get(key, "")).strip()
        for key in ("artist_style", "fixed_positive", "fixed_negative")
    }


def settings_hash(value: dict) -> str:
    raw = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def get_prompt_settings(store) -> dict:
    record = store.get("prompt_settings", SETTINGS_ID)
    values = _canonical(
        record
        or {
            "artist_style": DEFAULT_ARTIST_STYLE,
            "fixed_positive": DEFAULT_FIXED_POSITIVE,
            "fixed_negative": DEFAULT_FIXED_NEGATIVE,
        }
    )
    return {
        "schema_version": 1,
        **values,
        "content_hash": settings_hash(values),
        "source": "saved" if record else "default",
        "updated_at": (record or {}).get("updated_at"),
    }


def save_prompt_settings(store, body: PromptSettingsUpdate) -> dict:
    values = _canonical(body.model_dump())
    record = {"schema_version": 1, **values, "updated_at": time.time()}
    store.put("prompt_settings", record, SETTINGS_ID, replace=True)
    return get_prompt_settings(store)


def prompt_settings_router(get_store):
    router = APIRouter(prefix="/prompt-settings", tags=["Prompt settings"])

    @router.get("")
    def read_prompt_settings():
        return get_prompt_settings(get_store())

    @router.put("")
    def write_prompt_settings(body: PromptSettingsUpdate):
        return save_prompt_settings(get_store(), body)

    return router
