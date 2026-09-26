"""Template -> Qdrant sync: durability, idempotency and honest failure.

The writer is a stub: what is under test is the CASTER side of the contract -
that a marker survives a crash, that re-delivering it cannot write the wrong
point, that a failure is reported rather than swallowed, and that the drain
writes what the business store holds *now* rather than what the marker said.
"""

import time

import pytest

from aigc.agent.template_sync import TemplateSync, mark_template_dirty
from aigc.rag import RagUnavailable
from aigc.store import Store


class RecordingWriter:
    """Records what it was asked to write, and can be told to fail."""

    def __init__(self, fail_with=None):
        self.upserted = []
        self.deleted = []
        self.fail_with = fail_with

    def upsert(self, record):
        if self.fail_with:
            raise self.fail_with
        self.upserted.append(dict(record))
        return "point-" + str(record.get("id"))

    def delete(self, template_id):
        if self.fail_with:
            raise self.fail_with
        self.deleted.append(str(template_id))
        return 1

    def status(self):
        return {"write_available": not self.fail_with, "points": len(self.upserted)}


def template(template_id, kind="character", name=None, tags=None):
    return {
        "id": template_id,
        "kind": kind,
        "name": name or template_id,
        "tags": tags or ["maid"],
        "categories": [],
        "trigger": template_id,
        "description": template_id + " description",
        "source": "user",
        "source_revision": "1",
    }


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_a_template_write_marks_it_dirty(store):
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    sync = TemplateSync(store, RecordingWriter())
    assert [m["id"] for m in sync.pending()] == ["maid"]


def test_the_drain_writes_the_live_record(store):
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    writer = RecordingWriter()
    sync = TemplateSync(store, writer)
    result = sync.drain_once()
    assert result == {"synced": 1, "failed": 0, "deleted": 0, "reason": ""}
    assert [r["id"] for r in writer.upserted] == ["maid"]
    assert sync.pending() == []
    assert sync.status()["dirty_count"] == 0


def test_a_second_edit_before_the_drain_writes_once(store):
    """The marker is per template, not per edit: queueing the same template twice
    must not encode it twice, and must write the newest record."""
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    store.put("prompt_template", template("maid", tags=["coat"]), "maid", replace=True)
    mark_template_dirty(store, "maid")
    writer = RecordingWriter()
    TemplateSync(store, writer).drain_once()
    assert len(writer.upserted) == 1
    assert writer.upserted[0]["tags"] == ["coat"], "the newest record is written"


def test_an_interrupted_drain_is_retried_from_the_same_place(store):
    """The marker is cleared only after the write is confirmed, so a crash in the
    middle of a batch leaves the rest of the queue intact."""
    for index in range(3):
        store.put("prompt_template", template("t%d" % index), "t%d" % index)
        mark_template_dirty(store, "t%d" % index)
    writer = RecordingWriter()
    sync = TemplateSync(store, writer, batch=3)
    writer.fail_with = RuntimeError("qdrant is down")
    result = sync.drain_once()
    assert result["failed"] == 3
    assert [m["id"] for m in sync.pending()] == ["t0", "t1", "t2"], "nothing was cleared"
    assert "qdrant is down" in sync.status()["last_error"]
    # The retry succeeds and writes exactly the same three templates.
    writer.fail_with = None
    assert sync.drain_once() == {"synced": 3, "failed": 0, "deleted": 0, "reason": ""}
    assert sorted(r["id"] for r in writer.upserted) == ["t0", "t1", "t2"]


def test_a_restart_recovers_the_queue(store):
    """A new process sees the same markers: the queue is in the business store,
    not in the drain's memory."""
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    first = TemplateSync(store, RecordingWriter())
    assert len(first.pending()) == 1
    # "Restart": a fresh sync object over the same store, nothing drained.
    second = TemplateSync(store, RecordingWriter())
    assert [m["id"] for m in second.pending()] == ["maid"]
    writer = RecordingWriter()
    assert TemplateSync(store, writer).drain_once()["synced"] == 1


def test_a_duplicate_delivery_replaces_its_own_point(store):
    """Idempotency is a property of the point ID, so the same template delivered
    twice must not produce two points. The stub records deliveries; the real
    guarantee is that the ID is a function of the document."""
    from aigc.rag_index import point_id, template_document

    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    writer = RecordingWriter()
    sync = TemplateSync(store, writer)
    sync.drain_once()
    mark_template_dirty(store, "maid")
    sync.drain_once()
    assert [r["id"] for r in writer.upserted] == ["maid", "maid"]
    identifier = point_id(template_document(template("maid"), "templates-live"))
    assert identifier == point_id(template_document(template("maid"), "templates-live"))


def test_a_deleted_template_has_its_point_removed(store):
    """The business store is the fact source: a marker whose template is gone is
    reconciled by deleting the point, not by writing a record from memory."""
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    with store.connect() as db:
        db.execute("DELETE FROM records WHERE kind='prompt_template' AND id='maid'")
    writer = RecordingWriter()
    result = TemplateSync(store, writer).drain_once()
    assert result == {"synced": 0, "failed": 0, "deleted": 1, "reason": ""}
    assert writer.deleted == ["maid"]
    assert writer.upserted == []


def test_an_explicit_delete_marker_removes_the_point(store):
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid", "delete")
    writer = RecordingWriter()
    TemplateSync(store, writer).drain_once()
    assert writer.deleted == ["maid"]


def test_a_missing_writer_is_reported_not_swallowed(store):
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    sync = TemplateSync(store, None)
    result = sync.drain_once()
    assert result["synced"] == 0 and result["failed"] == 1
    assert "RAG" in sync.status()["last_error"]
    assert sync.status()["writer"]["write_available"] is False


def test_the_status_reports_the_index_state(store, tmp_path):
    """An operator has to be able to see whether the collection is current."""
    import json as jsonlib

    root = tmp_path / "rag"
    (root / "models").mkdir(parents=True)
    (root / "models" / "manifest.json").write_text(
        jsonlib.dumps({"models": {"qwen3-embedding-0.6b": {"commit": "abc", "local_path": "/m"}}})
    )
    out = root / "output" / "index-v2"
    out.mkdir(parents=True)
    from aigc.rag_encoder import DEFAULT_INSTRUCTION, fingerprint

    (out / "manifest.json").write_text(
        jsonlib.dumps(
            {
                "model": {
                    "commit": "abc",
                    "dim": 1024,
                    "max_length": 2048,
                    "fingerprint": fingerprint("abc", 1024, 2048, DEFAULT_INSTRUCTION),
                    "task": DEFAULT_INSTRUCTION,
                },
                "collection_names": {"wiki": "wiki_v2", "templates": "templates_v2"},
            }
        )
    )
    from aigc.rag import RagSettings

    writer_status = RagSettings({"AIGC_RAG_DIR": str(root)}).matches_published_index()
    sync = TemplateSync(store, RecordingWriter())
    status = sync.status()
    assert status["dirty_count"] == 0
    assert status["synced_total"] == 0
    assert status["last_error"] == ""
    assert writer_status is True


def test_the_rebuild_entry_point_marks_every_template(store):
    for index in range(4):
        store.put("prompt_template", template("t%d" % index), "t%d" % index)
    writer = RecordingWriter()
    sync = TemplateSync(store, writer)
    assert sync.enqueue_all() == 4
    assert sync.drain_once() == {"synced": 4, "failed": 0, "deleted": 0, "reason": ""}
    assert sorted(r["id"] for r in writer.upserted) == ["t0", "t1", "t2", "t3"]


def test_a_refusing_writer_keeps_the_marker(store):
    """A version or alias refusal is a writer failure like any other: the marker
    stays so the queue is retried once the index is publishable again."""
    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")

    class Refusing(RecordingWriter):
        def upsert(self, record):
            raise RagUnavailable("编码器配置与已发布索引不一致")

    sync = TemplateSync(store, Refusing())
    assert sync.drain_once()["failed"] == 1
    assert "不一致" in sync.status()["last_error"]
    assert [m["id"] for m in sync.pending()] == ["maid"]


def test_the_loop_survives_a_bad_batch(store):
    """The background loop must not die on one failing batch."""
    import asyncio

    store.put("prompt_template", template("maid"), "maid")
    mark_template_dirty(store, "maid")
    sync = TemplateSync(store, RecordingWriter(fail_with=RuntimeError("boom")), interval=0.01)

    async def scenario():
        task = asyncio.create_task(sync.run())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    assert asyncio.run(scenario()) is True
    assert "boom" in sync.last_error
    assert sync.status()["dirty_count"] == 1


def test_the_marker_records_when_it_was_queued(store):
    store.put("prompt_template", template("maid"), "maid")
    before = time.time()
    mark_template_dirty(store, "maid")
    marker = TemplateSync(store, RecordingWriter()).pending()[0]
    assert marker["queued_at"] >= before
    assert marker["op"] == "upsert"
    assert isinstance(marker["revision"], int)


def test_an_unknown_op_is_rejected(store):
    with pytest.raises(ValueError):
        mark_template_dirty(store, "maid", "truncate")
