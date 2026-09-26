"""Durable, ordered Agent events, independent of model execution."""

import json
import time
from typing import Any

from .contracts import AgentEvent


class EventLog:
    """Durable, cursor-addressable event log per conversation."""

    def __init__(self, store):
        self.store = store

    def append(
        self, conversation_id: str, run_id: str | None, type: str, payload: dict[str, Any]
    ) -> AgentEvent:
        """Allocate the sequence and insert the event in one write transaction.

        Splitting the two lets another writer take sequence 2 and commit before
        this writer's 1: a client that already advanced its cursor past 2 would
        never see 1. Doing both under ``BEGIN IMMEDIATE`` keeps cursor order and
        visibility order identical.
        """
        key = "agent_event_seq:" + conversation_id
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("counter", key)
            ).fetchone()
            if row:
                seq = int(json.loads(row["body"])["value"]) + 1
            else:
                # A database written before the counter existed still holds
                # events: seed the sequence from the highest stored one, or this
                # append would reuse an event id that is already taken.
                seq = self._highest_stored_seq(db, conversation_id) + 1
            db.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?)",
                ("counter", key, json.dumps({"value": seq})),
            )
            event = AgentEvent(
                event_id=conversation_id + ":" + str(seq),
                conversation_id=conversation_id,
                run_id=run_id,
                type=type,
                at=time.time(),
                payload=payload,
            )
            db.execute(
                "INSERT INTO records VALUES(?,?,?)",
                (
                    "agent_event",
                    event.event_id,
                    json.dumps(dict(event.model_dump(), seq=seq), ensure_ascii=False),
                ),
            )
        return event

    @staticmethod
    def _highest_stored_seq(db, conversation_id: str) -> int:
        """Highest sequence already stored for this conversation, 0 if none."""
        prefix = conversation_id + ":"
        highest = 0
        for row in db.execute(
            "SELECT id FROM records WHERE kind='agent_event' AND id>=? AND id<?",
            (prefix, conversation_id + ";"),
        ):
            suffix = row["id"][len(prefix) :] if row["id"].startswith(prefix) else ""
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        return highest

    def since(self, conversation_id: str, after: str = "", limit: int = 200) -> list[AgentEvent]:
        with self.store.connect() as db:
            cursor = 0
            if after:
                row = db.execute(
                    "SELECT body FROM records WHERE kind='agent_event' AND id=?",
                    (after,),
                ).fetchone()
                record = json.loads(row["body"]) if row else {}
                if record.get("conversation_id") != conversation_id:
                    raise LookupError("Unknown event cursor: " + after)
                cursor = int(record.get("seq", 0))
            rows = db.execute(
                "SELECT body FROM records WHERE kind='agent_event' "
                "AND json_extract(body, '$.conversation_id')=? "
                "AND CAST(json_extract(body, '$.seq') AS INTEGER)>? "
                "ORDER BY CAST(json_extract(body, '$.seq') AS INTEGER) LIMIT ?",
                (conversation_id, cursor, max(0, limit)),
            ).fetchall()
        return [
            AgentEvent.model_validate(
                {k: v for k, v in json.loads(row["body"]).items() if k not in ("seq", "id")}
            )
            for row in rows
        ]

    def latest(self, conversation_id: str, limit: int = 200) -> list[AgentEvent]:
        """Recent evidence in cursor order, for a conversation snapshot."""
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT body FROM records WHERE kind='agent_event' "
                "AND json_extract(body, '$.conversation_id')=? "
                "ORDER BY CAST(json_extract(body, '$.seq') AS INTEGER) DESC LIMIT ?",
                (conversation_id, max(0, limit)),
            ).fetchall()
        return [
            AgentEvent.model_validate(
                {k: v for k, v in json.loads(row["body"]).items() if k not in ("seq", "id")}
            )
            for row in reversed(rows)
        ]
