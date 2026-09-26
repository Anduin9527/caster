"""Keeping the published template collection in step with the business store.

The offline build fills the template collection from a read-only snapshot, so a
template created or edited afterwards is invisible to semantic search until
something writes it. This module is that something.

Two halves, deliberately separate:

* **Enqueue** runs inside the request that wrote the template. It persists a
  marker in the same business SQLite, so a crash between "the template is
  saved" and "the index knows about it" leaves a durable reminder instead of a
  silently stale index. It never talks to Qdrant and never blocks on it.
* **Drain** is a background loop that reads the markers, reads the *current*
  record for each one, writes the point, and only then clears the marker. A
  crash at any point leaves the marker, and re-running is safe because the point
  ID is a function of the document.

What the drain does not do is trust the marker's contents. A marker says "this
template changed"; what gets written is whatever the business store holds now.
A marker for a template that has since been deleted is reconciled against the
live store - its point is removed - rather than written from memory.

Delivery is idempotent by construction rather by bookkeeping: the point ID is a
function of the document, so re-delivering a template replaces its own point.
There is deliberately no "is this revision newer" optimisation - a revision
compared against a *global* counter would drop a template that was never
superseded, because any other template's edit bumps that counter.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any

DIRTY_TABLE = "rag_template_dirty"
_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS %s("
    "id TEXT PRIMARY KEY, revision INTEGER NOT NULL, op TEXT NOT NULL, "
    "queued_at REAL NOT NULL)" % DIRTY_TABLE
)
OPS = ("upsert", "delete")


def _ensure_table(store) -> None:
    with store.connect() as db:
        db.execute(_CREATE_TABLE)


def mark_template_dirty(store, template_id: str, op: str = "upsert") -> int:
    """Persist "this template needs re-indexing". Call after a successful write.

    Returns the template revision the marker was queued at. It is recorded for
    diagnosis ("when did this become dirty"), not for deciding what to write:
    the drain always writes the live record.
    """
    if op not in OPS:
        raise ValueError("op must be one of %s" % (OPS,))
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Created here rather than in Store.__init__ so the schema of the
        # business database does not change for callers that never sync.
        db.execute(_CREATE_TABLE)
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("counter", "agent_template_revision")
        ).fetchone()
        revision = int(json.loads(row["body"])["value"]) if row else 0
        # One row per template: a second edit before the drain replaces the
        # marker instead of queueing the same template twice.
        db.execute(
            "INSERT INTO %s VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, "
            "op=excluded.op, queued_at=excluded.queued_at" % DIRTY_TABLE,
            (str(template_id), revision, op, time.time()),
        )
    return revision


def mark_template_batch_in_transaction(db, changes: dict[str, str], revision: int) -> None:
    """Queue a replacement set inside the caller's existing transaction.

    Bulk catalog promotion must commit record deletes/inserts and their Qdrant
    reconciliation markers atomically.  Opening one connection per template
    would leave a crash window where the business store and semantic index
    disagree, so the promotion path uses this transaction-aware companion.
    """
    invalid = sorted(set(changes.values()) - set(OPS))
    if invalid:
        raise ValueError("op must be one of %s" % (OPS,))
    db.execute(_CREATE_TABLE)
    queued_at = time.time()
    db.executemany(
        "INSERT INTO %s VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, "
        "op=excluded.op, queued_at=excluded.queued_at" % DIRTY_TABLE,
        [
            (str(template_id), int(revision), op, queued_at)
            for template_id, op in sorted(changes.items())
        ],
    )


class TemplateSync:
    """The drain: markers in, points written, markers cleared."""

    def __init__(self, store, writer=None, batch: int = 16, interval: float = 5.0):
        self.store = store
        self.writer = writer
        self.batch = max(1, int(batch))
        self.interval = float(interval)
        self.last_success_at = 0.0
        self.last_error = ""
        self.last_error_at = 0.0
        self.synced = 0
        self.deleted = 0
        _ensure_table(store)

    # -- queue -------------------------------------------------------------- #
    def pending(self) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id, revision, op, queued_at FROM %s "
                "ORDER BY queued_at, id LIMIT ?" % DIRTY_TABLE,
                (self.batch,),
            ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_all(self) -> int:
        """Re-mark every template in the business store. The explicit rebuild."""
        records = self.store.list("prompt_template")
        for record in records:
            mark_template_dirty(self.store, str(record.get("id") or ""), "upsert")
        return len(records)

    # -- drain -------------------------------------------------------------- #
    def drain_once(self) -> dict[str, Any]:
        """Write one batch. Never raises: a failure is reported and retried.

        Markers are cleared only after Qdrant confirms the write, so an
        interrupted batch is retried from the same place.
        """
        if self.writer is None:
            self._fail("没有配置 RAG 索引，模板同步不可用")
            return {"synced": 0, "failed": len(self.pending()), "reason": self.last_error}
        batch = self.pending()
        if not batch:
            return {"synced": 0, "failed": 0, "reason": ""}
        synced = deleted = failed = 0
        reason = ""
        for marker in batch:
            try:
                outcome = self._apply(marker)
            except Exception as error:
                # The marker stays, so the next attempt retries this template.
                failed += 1
                reason = type(error).__name__ + "：" + str(error)[:200]
                continue
            self._clear(marker["id"])
            if outcome == "deleted":
                self.deleted += 1
                deleted += 1
            else:
                self.synced += 1
                synced += 1
        if failed:
            self._fail(reason)
        else:
            self.last_success_at = time.time()
            self.last_error = ""
        return {"synced": synced, "failed": failed, "deleted": deleted, "reason": reason}

    def _apply(self, marker: dict[str, Any]) -> str:
        """Write one marker against the live record."""
        template_id = str(marker["id"])
        record = self.store.get("prompt_template", template_id)
        if record is None or marker.get("op") == "delete":
            # The business store is the fact source: a template that is gone has
            # no point, whatever the marker asked for.
            self.writer.delete(template_id)
            return "deleted"
        self.writer.upsert(record)
        return "upserted"

    def _clear(self, template_id: str) -> None:
        with self.store.connect() as db:
            db.execute("DELETE FROM %s WHERE id=?" % DIRTY_TABLE, (str(template_id),))

    def _fail(self, reason: str) -> None:
        self.last_error = reason
        self.last_error_at = time.time()

    # -- reporting ---------------------------------------------------------- #
    def status(self) -> dict[str, Any]:
        """What an operator needs to see: is it current, and if not, why not."""
        try:
            pending = self.pending()
        except sqlite3.Error as error:  # pragma: no cover - unreadable store
            pending = []
            self._fail(type(error).__name__ + "：" + str(error)[:200])
        writer_status = (
            self.writer.status()
            if self.writer is not None
            else {"write_available": False, "reason": "writer not configured"}
        )
        return {
            "dirty_count": len(pending),
            "synced_total": self.synced,
            "deleted_total": self.deleted,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "writer": writer_status,
        }

    # -- loop --------------------------------------------------------------- #
    async def run(self) -> None:
        """Drain until cancelled. Started by the API lifespan, not per request."""
        while True:
            try:
                self.drain_once()
            except Exception as error:  # the loop outlives a bad batch
                self._fail(type(error).__name__ + "：" + str(error)[:200])
            await asyncio.sleep(self.interval)
