"""Conversations, messages and runs, persisted in the business SQLite.

A conversation is bound to one character task; every user message is
persisted and gets a message/run ID; replaying the same message is idempotent;
runs in one conversation are strictly ordered.
"""

import json
import time
import uuid
from typing import Any

from .contracts import WorkbenchContext


def new_id() -> str:
    return uuid.uuid4().hex


def _read(db, kind, record_id):
    row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
    return dict(json.loads(row["body"]), id=record_id) if row else None


def _write(db, kind, record):
    db.execute(
        "INSERT OR REPLACE INTO records VALUES(?,?,?)",
        (
            kind,
            record["id"],
            json.dumps({k: v for k, v in record.items() if k != "id"}, ensure_ascii=False),
        ),
    )


def _conversation(db, conversation_id):
    body = _read(db, "agent_conversation", conversation_id)
    if body is None:
        raise LookupError("Unknown conversation: " + str(conversation_id))
    return body


def _touch(db, conversation, **changes):
    conversation.update(changes, updated=time.time())
    _write(db, "agent_conversation", conversation)


def _require_idle(db, conversation, run_id=None):
    active_id = conversation.get("active_run_id")
    if active_id and active_id != run_id:
        active = _read(db, "agent_run", active_id)
        if active and active.get("status") in ("running", "stopping"):
            raise RuntimeError("该对话已有一轮正在运行，请先停止或等待完成")


class Conversation:
    def __init__(self, store):
        self.store = store

    # -- conversations ------------------------------------------------------ #
    def create(self, character_id: str | None, title: str = "") -> dict[str, Any]:
        body = {
            "character_id": character_id,
            "title": title or "新的制作对话",
            "created": time.time(),
            "updated": time.time(),
            "active_run_id": None,
            "message_count": 0,
            "run_count": 0,
        }
        return self.store.put("agent_conversation", body, new_id())

    def get(self, conversation_id: str) -> dict[str, Any]:
        record = self.store.get("agent_conversation", conversation_id)
        if not record:
            raise LookupError("Unknown conversation: " + str(conversation_id))
        return record

    def list_conversations(self, character_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.store.list("agent_conversation")
        if character_id:
            rows = [r for r in rows if r.get("character_id") == character_id]
        return sorted(rows, key=lambda r: r.get("updated", 0), reverse=True)

    def touch(self, conversation_id: str, **changes) -> None:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _touch(db, _conversation(db, conversation_id), **changes)

    def rebind(self, conversation_id: str, character_id: str | None) -> dict[str, Any]:
        """Switching character never leaves the old source image behind."""
        self.touch(conversation_id, character_id=character_id, selection_revision=0)
        return self.get(conversation_id)

    # -- messages ----------------------------------------------------------- #
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        idempotency_key: str | None = None,
        context: WorkbenchContext | None = None,
        kind: str = "text",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one message. The same idempotency key returns the same message.

        The key is scoped to its conversation: a client that reuses one key across
        conversations (a fixed request id, a retried batch) must not silently
        inherit another conversation's message. A key replayed with different
        content is a client bug, not a second message.
        """
        key = idempotency_key or new_id()
        record_id = "msg-" + conversation_id + ":" + key
        body: dict[str, Any] = {
            "id": record_id,
            "conversation_id": conversation_id,
            "role": role,
            "kind": kind,
            "content": content,
            "created": time.time(),
        }
        if context is not None:
            body["context"] = context.model_dump()
        if extra:
            body.update(extra)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conversation = _conversation(db, conversation_id)
            existing = _read(db, "agent_message", record_id)
            if existing:
                if existing.get("content") != content or existing.get("role") != role:
                    raise ValueError("相同的幂等键被用于不同内容，请更换 idempotency_key")
                return existing
            if role == "user":
                _require_idle(db, conversation)
            _write(db, "agent_message", body)
            _touch(db, conversation, message_count=conversation.get("message_count", 0) + 1)
        return body

    def history(self, conversation_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = [
            r
            for r in self.store.list("agent_message")
            if r.get("conversation_id") == conversation_id
        ]
        return sorted(rows, key=lambda r: r.get("created", 0))[-limit:]

    # -- runs --------------------------------------------------------------- #
    def start_run(
        self, conversation_id: str, message_id: str, run_id: str | None = None
    ) -> dict[str, Any]:
        run_id = run_id or "run-" + message_id
        body = {
            "id": run_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "status": "running",
            "created": time.time(),
            "updated": time.time(),
            "error": "",
            "tool_calls": 0,
            "model": "",
            "base_url": "",
        }
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conversation = _conversation(db, conversation_id)
            existing = _read(db, "agent_run", run_id)
            if existing:
                if existing["conversation_id"] != conversation_id:
                    raise ValueError("Run belongs to another conversation")
                if existing.get("status") != "failed":
                    return existing
            # A failed retry must obey the same ordering as a new run.
            _require_idle(db, conversation, run_id)
            if existing:
                body = dict(existing, status="running", error="", updated=time.time())
            _write(db, "agent_run", body)
            _touch(
                db,
                conversation,
                active_run_id=run_id,
                run_count=conversation.get("run_count", 0) + int(existing is None),
            )
        return body

    def get_run(self, run_id: str) -> dict[str, Any]:
        record = self.store.get("agent_run", run_id)
        if not record:
            raise LookupError("Unknown run: " + str(run_id))
        return record

    def finish_run(self, run_id: str, status: str, **changes) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            body = _read(db, "agent_run", run_id)
            if body is None:
                raise LookupError("Unknown run: " + str(run_id))
            body.update(changes, status=status, updated=time.time())
            _write(db, "agent_run", body)
            conversation = _conversation(db, body["conversation_id"])
            if conversation.get("active_run_id") == run_id:
                _touch(db, conversation, active_run_id=None)
        return body

    def runs(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = [
            r for r in self.store.list("agent_run") if r.get("conversation_id") == conversation_id
        ]
        return sorted(rows, key=lambda r: r.get("created", 0), reverse=True)
