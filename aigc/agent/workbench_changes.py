"""Prepare and approve reusable workbench changes outside the model tool loop."""

import hashlib
import json
import time
import uuid
from typing import Any

from ..anima_defaults import escape_template_tags
from ..schema import Character, Outfit
from ..templates import character_prompt_sections
from .contracts import WorkbenchChange, content_hash, workbench_change_from
from .retrieval import normalize


class WorkbenchChangeError(ValueError):
    pass


class WorkbenchChangeConflict(WorkbenchChangeError):
    pass


def public_change(change: WorkbenchChange) -> dict[str, Any]:
    """Card payload: enough to approve and inspect, without frozen internals."""
    return change.model_dump(
        exclude={
            "character_template_snapshot",
            "outfit_template_snapshot",
            "source_character_hash",
        }
    )


def _preview(template_id: str) -> str:
    return "/prompt-templates/" + template_id + "/image"


def _prompt_tags(template: dict[str, Any]) -> list[str]:
    values = [template.get("trigger") or ""] + list(template.get("tags") or [])
    return [escape_template_tags(value) for value in values if str(value).strip()]


def _excluded(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            normalize(tag) for tag in (value or "").replace("，", ",").split(",") if normalize(tag)
        )
    )


def _template_excluded(template: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            normalize(tag) for tag in (template.get("excluded_tags") or []) if normalize(tag)
        )
    )


def _captions(template: dict[str, Any]) -> list[str]:
    return [
        str(value).strip() for value in (template.get("caption_en") or []) if str(value).strip()
    ]


def _check_caption_exclusions(captions: list[str], excluded: list[str]) -> None:
    """Refuse contradictory prose instead of heuristically rewriting it."""
    body = normalize(" ".join(captions))
    conflicts = [tag for tag in excluded if normalize(tag) in body]
    if conflicts:
        raise WorkbenchChangeError(
            "服装英文描述仍明确包含要排除的标签："
            + "、".join(conflicts)
            + "；请先修订并重新审阅描述"
        )


def _filter_outfit(tags: list[str], excluded: list[str]) -> list[str]:
    if not excluded:
        return tags
    present = {normalize(tag) for tag in tags}
    missing = [tag for tag in excluded if tag not in present]
    if missing:
        raise WorkbenchChangeError("服装模板中没有要排除的标签：" + "、".join(missing))
    result = [tag for tag in tags if normalize(tag) not in set(excluded)]
    if not result:
        raise WorkbenchChangeError("排除后服装模板为空")
    return result


def _template(store, template_id: str, kind: str) -> dict[str, Any]:
    value = store.get("prompt_template", template_id)
    if not value:
        raise WorkbenchChangeError("未知模板：" + template_id)
    if value.get("kind") != kind:
        raise WorkbenchChangeError(
            "选中的不是%s模板：%s" % ("角色" if kind == "character" else "服装", template_id)
        )
    return {k: v for k, v in value.items() if k != "id"} | {"id": template_id}


def _character_hash(character: dict[str, Any]) -> str:
    body = {k: v for k, v in character.items() if k != "id"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _finish(change: WorkbenchChange) -> WorkbenchChange:
    return change.model_copy(update={"content_hash": content_hash(change.hashed_fields())})


def prepare_character(
    store,
    conversation_id: str,
    character_template_id: str,
    requested_outfit: bool,
    outfit_template_id: str = "",
    excluded_outfit_tags: str = "",
    character_id: str = "",
    name: str = "",
) -> WorkbenchChange:
    if requested_outfit and not outfit_template_id:
        raise WorkbenchChangeError("用户要求了服装，必须选定完整服装模板后才能创建")
    if excluded_outfit_tags and not outfit_template_id:
        raise WorkbenchChangeError("排除服装标签时必须指定服装模板")
    character = _template(store, character_template_id, "character")
    outfit = _template(store, outfit_template_id, "outfit") if outfit_template_id else {}
    requested_excluded = _excluded(excluded_outfit_tags)
    outfit_tags = _filter_outfit(_prompt_tags(outfit), requested_excluded) if outfit else []
    _check_caption_exclusions(_captions(outfit), requested_excluded)
    excluded = list(dict.fromkeys([*_template_excluded(outfit), *requested_excluded]))
    target_id = character_id or ("agent-" + uuid.uuid4().hex[:16])
    if store.get("character", target_id):
        raise WorkbenchChangeConflict("角色 ID 已存在：" + target_id)
    display_name = name or character.get("name") or target_id
    change = WorkbenchChange(
        change_id="change-" + uuid.uuid4().hex,
        conversation_id=conversation_id,
        operation="create_character",
        status="awaiting_approval",
        title="创建角色：" + display_name,
        summary=(
            "写入完整角色模板"
            + ("和完整服装模板" if outfit else "")
            + "；只有明确排除的服装标签会被移除。"
        ),
        character_id=target_id,
        character_name=display_name,
        focus="identity",
        character_template_id=character_template_id,
        character_template_name=character.get("name") or character_template_id,
        character_preview_url=_preview(character_template_id),
        character_tags=_prompt_tags(character),
        outfit_template_id=outfit_template_id or None,
        outfit_template_name=outfit.get("name") or "",
        outfit_preview_url=_preview(outfit_template_id) if outfit else None,
        outfit_tags=outfit_tags,
        outfit_captions=_captions(outfit),
        excluded_outfit_tags=excluded,
        character_template_snapshot=character,
        outfit_template_snapshot=outfit,
        content_hash="0" * 64,
        created_at=time.time(),
    )
    change = _finish(change)
    store.put("workbench_change", change.model_dump(), change.change_id)
    return change


def prepare_outfit(
    store,
    conversation_id: str,
    character_id: str,
    outfit_template_id: str,
    excluded_outfit_tags: str = "",
    name: str = "",
    parent_id: str = "",
) -> WorkbenchChange:
    character = store.get("character", character_id)
    if not character:
        raise WorkbenchChangeError("角色不存在：" + character_id)
    outfit = _template(store, outfit_template_id, "outfit")
    requested_excluded = _excluded(excluded_outfit_tags)
    tags = _filter_outfit(_prompt_tags(outfit), requested_excluded)
    _check_caption_exclusions(_captions(outfit), requested_excluded)
    excluded = list(dict.fromkeys([*_template_excluded(outfit), *requested_excluded]))
    # This ID is fixed before approval, so the card and applied record are the
    # same operation and a double click remains idempotent.
    outfit_id = "agent-outfit-" + uuid.uuid4().hex[:16]
    snapshot = dict(
        outfit,
        _version_name=name or outfit.get("name") or outfit_id,
        _version_id=outfit_id,
        _parent_id=parent_id or "",
    )
    change = WorkbenchChange(
        change_id="change-" + uuid.uuid4().hex,
        conversation_id=conversation_id,
        operation="append_outfit",
        status="awaiting_approval",
        title="为%s追加%s" % (character.get("name") or character_id, outfit.get("name") or "服装"),
        summary="把完整服装模板追加为不可变服装版本；明确排除项不会写入。",
        character_id=character_id,
        character_name=character.get("name") or character_id,
        focus="outfit",
        outfit_template_id=outfit_template_id,
        outfit_template_name=outfit.get("name") or outfit_template_id,
        outfit_preview_url=_preview(outfit_template_id),
        outfit_tags=tags,
        outfit_captions=_captions(outfit),
        excluded_outfit_tags=excluded,
        outfit_template_snapshot=snapshot,
        source_character_hash=_character_hash(character),
        content_hash="0" * 64,
        created_at=time.time(),
    )
    change = _finish(change)
    store.put("workbench_change", change.model_dump(), change.change_id)
    return change


def list_for_conversation(store, conversation_id: str) -> list[WorkbenchChange]:
    changes = [
        workbench_change_from(value)
        for value in store.list("workbench_change")
        if value.get("conversation_id") == conversation_id
    ]
    changes.sort(key=lambda value: value.created_at)
    return changes


def approve(store, change_id: str, expected_hash: str = "") -> WorkbenchChange:
    now = time.time()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("workbench_change", change_id)
        ).fetchone()
        if not row:
            raise WorkbenchChangeError("工作台变更不存在")
        change = workbench_change_from(json.loads(row["body"]))
        if expected_hash and expected_hash != change.content_hash:
            raise WorkbenchChangeConflict("工作台变更内容已变化，请重新确认")
        if content_hash(change.hashed_fields()) != change.content_hash:
            raise WorkbenchChangeConflict("工作台变更内容校验失败")
        if change.status == "applied":
            return change
        if change.status != "awaiting_approval":
            raise WorkbenchChangeConflict("工作台变更已不可应用：" + change.status)

        if change.operation == "create_character":
            exists = db.execute(
                "SELECT 1 FROM records WHERE kind=? AND id=?", ("character", change.character_id)
            ).fetchone()
            if exists:
                raise WorkbenchChangeConflict("角色 ID 已被占用，请重新准备变更")
            char_template = change.character_template_snapshot
            outfits = []
            if change.outfit_template_id:
                outfit = change.outfit_template_snapshot
                outfits.append(
                    Outfit(
                        id=change.outfit_template_id,
                        tags=change.outfit_tags,
                        description=outfit.get("description") or "",
                        caption_en=change.outfit_captions,
                        excluded_tags=change.excluded_outfit_tags,
                    ).model_dump()
                )
            character = Character(
                id=change.character_id,
                name=change.character_name,
                fixed_tags=change.character_tags,
                prompt_sections=character_prompt_sections(char_template, True),
                description=char_template.get("description") or "",
                outfits=outfits,
            ).model_dump()
            character["template_snapshot"] = {
                "character": char_template,
                "outfits": ([change.outfit_template_snapshot] if change.outfit_template_id else []),
                "include_character_tags": True,
                "excluded_outfit_tags": change.excluded_outfit_tags,
            }
            db.execute(
                "INSERT INTO records VALUES(?,?,?)",
                ("character", change.character_id, json.dumps(character, ensure_ascii=False)),
            )
        else:
            row = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("character", change.character_id)
            ).fetchone()
            if not row:
                raise WorkbenchChangeConflict("目标角色已不存在")
            character = json.loads(row["body"])
            if (
                _character_hash(dict(character, id=change.character_id))
                != change.source_character_hash
            ):
                raise WorkbenchChangeConflict("角色内容已变化，请重新准备服装变更")
            snapshot = change.outfit_template_snapshot
            outfit_id = snapshot["_version_id"]
            if any(item["id"] == outfit_id for item in character.get("outfits") or []):
                raise WorkbenchChangeConflict("服装版本 ID 已存在")
            parent_id = snapshot.get("_parent_id") or None
            if parent_id and not any(
                item["id"] == parent_id for item in character.get("outfits") or []
            ):
                raise WorkbenchChangeConflict("父服装版本已不存在")
            outfit = Outfit(
                id=outfit_id,
                tags=change.outfit_tags,
                description=snapshot.get("description") or "",
                caption_en=change.outfit_captions,
                excluded_tags=change.excluded_outfit_tags,
            ).model_dump()
            character.setdefault("outfits", []).append(outfit)
            version = dict(
                outfit,
                name=snapshot["_version_name"],
                parent_id=parent_id,
                character_id=change.character_id,
            )
            db.execute(
                "UPDATE records SET body=? WHERE kind=? AND id=?",
                (json.dumps(character, ensure_ascii=False), "character", change.character_id),
            )
            db.execute(
                "INSERT INTO records VALUES(?,?,?)",
                (
                    "outfit_version",
                    change.character_id + ":" + outfit_id,
                    json.dumps(version, ensure_ascii=False),
                ),
            )

        change = change.model_copy(update={"status": "applied", "applied_at": now})
        db.execute(
            "UPDATE records SET body=? WHERE kind=? AND id=?",
            (json.dumps(change.model_dump(), ensure_ascii=False), "workbench_change", change_id),
        )
    return change


def cancel(store, change_id: str) -> WorkbenchChange:
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("workbench_change", change_id)
        ).fetchone()
        if not row:
            raise WorkbenchChangeError("工作台变更不存在")
        change = workbench_change_from(json.loads(row["body"]))
        if change.status == "applied":
            raise WorkbenchChangeConflict("已应用的工作台变更不能取消")
        if change.status == "cancelled":
            return change
        change = change.model_copy(update={"status": "cancelled"})
        db.execute(
            "UPDATE records SET body=? WHERE kind=? AND id=?",
            (json.dumps(change.model_dump(), ensure_ascii=False), "workbench_change", change_id),
        )
    return change
