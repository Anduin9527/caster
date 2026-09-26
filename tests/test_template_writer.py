"""The incremental writer's contract: same shape as a build, same refusals.

What matters here is not that a point is written - it is that the point written
by the running service is the point the offline build would have written, and
that a writer refuses exactly when a reader refuses. A writer that silently
produced a different point ID or payload would leave two points for one
template, or make the next verification report drift on a correct point.
"""

import json

import pytest

from aigc.rag import RagSettings, RagUnavailable, TemplateIndexWriter
from aigc.rag_index import payload_of, point_id, template_document


def workspace(tmp_path, collection_names=None, commit="abc"):
    root = tmp_path / "rag"
    (root / "models").mkdir(parents=True)
    (root / "models" / "manifest.json").write_text(
        json.dumps({"models": {"qwen3-embedding-0.6b": {"commit": commit, "local_path": "/m"}}})
    )
    out = root / "output" / "index-v2"
    out.mkdir(parents=True)
    from aigc.rag_encoder import DEFAULT_INSTRUCTION, fingerprint

    body = {
        "model": {
            "commit": commit,
            "dim": 1024,
            "max_length": 2048,
            "fingerprint": fingerprint(commit, 1024, 2048, DEFAULT_INSTRUCTION),
            "task": DEFAULT_INSTRUCTION,
        },
        "collection_names": (
            collection_names
            if collection_names is not None
            else {"wiki": "wiki_v2", "templates": "templates_v2"}
        ),
    }
    (out / "manifest.json").write_text(json.dumps(body))
    return root


class RecordingClient:
    """Records upserts and deletes; answers the alias check from the manifest."""

    def __init__(self, aliases=None):
        self.upserts = []
        self.deletes = []
        self.aliases = (
            aliases if aliases is not None else {"wiki": "wiki_v2", "templates": "templates_v2"}
        )

    def get_aliases(self):
        client = self
        return type(
            "A",
            (),
            {
                "aliases": [
                    type("B", (), {"alias_name": alias, "collection_name": collection})()
                    for alias, collection in client.aliases.items()
                ]
            },
        )()

    def upsert(self, collection_name, points, wait=True):
        self.upserts.append((collection_name, points))
        return type("R", (), {"status": "completed"})()

    def delete(self, collection_name, points_selector, wait=True):
        self.deletes.append((collection_name, points_selector))
        return type("R", (), {"status": "completed"})()

    def count(self, collection_name, exact=True):
        return type("C", (), {"count": len(self.upserts)})()


class StubDocumentEncoder:
    def encode_documents(self, texts):
        import numpy as np

        return [np.full(1024, 1.0 / 32, dtype="float32") for _ in texts]


def writer_for(tmp_path, client=None, encoder=None, **kwargs):
    writer = TemplateIndexWriter(RagSettings({"AIGC_RAG_DIR": str(workspace(tmp_path, **kwargs))}))
    writer._client = client or RecordingClient()
    writer._encoder = encoder or StubDocumentEncoder()
    return writer


def template(template_id="maid", kind="character", tags=None):
    return {
        "id": template_id,
        "kind": kind,
        "name": template_id,
        "tags": tags or ["maid", "apron"],
        "categories": [],
        "trigger": template_id,
        "description": template_id + " description",
        "source": "user",
        "source_revision": "7",
    }


def test_reused_writer_refuses_alias_drift_before_another_write(tmp_path):
    writer = writer_for(tmp_path)
    writer.upsert(template())
    writer.client.aliases["templates"] = "different-collection"
    with pytest.raises(RagUnavailable, match="不一致"):
        writer.upsert(template("second"))
    assert len(writer.client.upserts) == 1


def test_write_pins_verified_collection_if_manifest_changes_during_encoding(tmp_path):
    writer = writer_for(tmp_path)

    class SwitchingEncoder(StubDocumentEncoder):
        def encode_documents(self, texts):
            manifest = writer.settings.index_manifest()
            manifest["collection_names"]["templates"] = "unverified-new-collection"
            writer.settings.manifest_path.write_text(json.dumps(manifest))
            return super().encode_documents(texts)

    writer._encoder = SwitchingEncoder()
    writer.upsert(template())
    assert writer.client.upserts[0][0] == "templates_v2"
    with pytest.raises(RagUnavailable, match="不一致"):
        writer.upsert(template("second"))


def test_the_written_point_is_the_one_a_build_would_write(tmp_path):
    """The point ID and the payload come from the shared module, so the online
    writer and the offline build cannot disagree about the shape of a point."""
    writer = writer_for(tmp_path)
    record = template()
    identifier = writer.upsert(record)
    assert identifier == point_id(template_document(record, writer.version))
    collection, points = writer.client.upserts[0]
    assert collection == "templates_v2", "writes to the published collection"
    assert len(points) == 1
    written = points[0]
    assert written.id == identifier
    assert written.payload == payload_of(template_document(record, writer.version))
    assert written.payload["kind"] == "character_template"
    assert written.payload["template_id"] == "maid"
    assert written.payload["source_url"] == "/prompt-templates/maid/image"
    assert written.payload["text_sha256"]
    assert "text" not in written.payload, "long text never enters the payload"
    assert list(written.vector) == [1.0 / 32] * 1024


def test_an_outfit_template_is_written_under_the_outfit_kind(tmp_path):
    writer = writer_for(tmp_path)
    writer.upsert(template("suit", kind="outfit"))
    assert writer.client.upserts[0][1][0].payload["kind"] == "outfit_template"


def test_a_refusing_encoder_blocks_the_write(tmp_path):
    """A same-dimension model swap must not be able to write into a collection
    built by another encoder."""
    writer = writer_for(tmp_path, commit="abc")
    writer.settings.commit = "a-different-model"
    with pytest.raises(RagUnavailable, match="编码器配置与已发布索引不一致"):
        writer.upsert(template())
    assert writer.client.upserts == []


def test_an_unswitched_alias_blocks_the_write(tmp_path):
    writer = writer_for(
        tmp_path, client=RecordingClient(aliases={"wiki": "wiki_v1", "templates": "templates_v1"})
    )
    with pytest.raises(RagUnavailable, match="alias 指向与 manifest 不一致"):
        writer.upsert(template())
    assert writer.client.upserts == []


def test_a_delete_removes_the_point_by_document_id(tmp_path):
    """By payload filter, because the point ID contains the document kind and
    the record that would have said which kind is already gone."""
    writer = writer_for(tmp_path)
    writer.delete("maid")
    collection, selector = writer.client.deletes[0]
    assert collection == "templates_v2"
    condition = selector.filter.must[0]
    assert condition.key == "doc_id"
    assert condition.match.value == "maid"


def test_a_delete_is_also_refused_on_a_version_mismatch(tmp_path):
    writer = writer_for(tmp_path, commit="abc")
    writer.settings.commit = "a-different-model"
    with pytest.raises(RagUnavailable, match="不一致"):
        writer.delete("maid")
    assert writer.client.deletes == []


def test_the_status_reports_a_dead_service_as_a_state(tmp_path):
    class Dead:
        def get_aliases(self):
            raise ConnectionRefusedError("qdrant is down")

        def count(self, **kwargs):
            raise ConnectionRefusedError("qdrant is down")

    writer = writer_for(tmp_path, client=Dead())
    status = writer.status()
    assert status["write_available"] is False
    assert "qdrant is down" in status["reason"]
