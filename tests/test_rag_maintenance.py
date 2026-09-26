"""Offline index maintenance contracts; no model, GPU or Qdrant server needed."""

import json
import sqlite3
import sys
from contextlib import closing

import numpy as np
import pytest
from qdrant_client import QdrantClient, models

from aigc.rag_index import cache_key, payload_of, point_id
from scripts import rag_publish_alias, rag_verify_index
from scripts.rag_build_index import Cache, ensure_unpublished, load_templates, sha256_file


def test_vector_cache_rejects_invalid_batches_before_overwriting_good_vectors(tmp_path):
    path = tmp_path / "vectors.sqlite3"
    with closing(Cache(path)) as cache:
        cache.store(["good"], np.asarray([[1.0, 0.0]]))
        for invalid in (np.ones((2, 2)), np.asarray([[float("nan"), 0]]), np.zeros((1, 2))):
            with pytest.raises(ValueError):
                cache.store(["good"], invalid)
        assert cache.lookup(["good"])["good"].tolist() == [1.0, 0.0]
        cache.db.execute("INSERT INTO vectors VALUES(?,?,?)", ("truncated", 2, b"short"))
        cache.db.commit()
        assert cache.lookup(["truncated"]) == {}
    before = path.read_bytes()
    with closing(Cache(path, readonly=True)) as cache:
        assert cache.lookup(["good"])["good"].tolist() == [1.0, 0.0]
        with pytest.raises(sqlite3.OperationalError):
            cache.store(["new"], np.asarray([[0.0, 1.0]]))
    assert path.read_bytes() == before
    with pytest.raises(sqlite3.OperationalError):
        Cache(tmp_path / "absent.sqlite3", readonly=True)
    assert not (tmp_path / "absent.sqlite3").exists()


def test_build_refuses_published_collection_but_allows_an_unpublished_resume():
    with closing(QdrantClient(":memory:")) as client:
        client.create_collection(
            "live", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
        )
        client.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(collection_name="live", alias_name="templates"),
                )
            ]
        )
        with pytest.raises(ValueError, match="published collections: live"):
            ensure_unpublished(client, ["live"])
        ensure_unpublished(client, ["candidate"])
        with pytest.raises(ValueError, match="distinct nonempty"):
            ensure_unpublished(client, ["candidate", "candidate"])


@pytest.fixture
def template_index(tmp_path):
    snapshot = tmp_path / "input" / "templates-v1.json"
    snapshot.parent.mkdir()
    snapshot.write_text(
        json.dumps(
            {
                "templates": [
                    {"id": "a", "kind": "character", "name": "A", "tags": ["red hair"]},
                    {"id": "b", "kind": "outfit", "name": "B", "tags": ["dress"]},
                ]
            }
        )
    )
    documents, _ = load_templates(snapshot)
    cache_path = tmp_path / "cache.sqlite3"
    with closing(Cache(cache_path)) as cache:
        cache.store([cache_key(document, "encoder") for document in documents], np.eye(2))
    manifest = {
        "model": {"fingerprint": "encoder", "dim": 2},
        "collection_names": {"wiki": "wiki_unused", "template": "templates_candidate"},
        "collections": {"templates_candidate": {"documents": 2}},
        "inputs": {"templates_sha256": sha256_file(snapshot)},
    }
    with closing(QdrantClient(":memory:")) as client:
        client.create_collection(
            "templates_candidate",
            vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
        )
        client.upsert(
            "templates_candidate",
            points=[
                models.PointStruct(
                    id=point_id(document), payload=payload_of(document), vector=vector.tolist()
                )
                for document, vector in zip(documents, np.eye(2))
            ],
        )
        yield tmp_path, manifest, client, cache_path, documents


def test_template_only_verification_needs_no_wiki_and_checks_every_sample(template_index):
    workspace, manifest, client, cache_path, _ = template_index
    result = rag_verify_index._verify(workspace, manifest, client, 2, cache_path)
    assert result["ok"], result["problems"]
    assert result["cache_comparisons"] == result["sampled_points"] == 2
    assert result["collection_names"] == {"template": "templates_candidate"}
    assert not (workspace / "output" / "wiki-v1").exists()


def test_verification_reports_bad_cache_dimensions_and_missing_collections(template_index):
    workspace, manifest, client, cache_path, documents = template_index
    with closing(Cache(cache_path)) as cache:
        cache.store([cache_key(documents[0], "encoder")], np.asarray([[1.0, 0.0, 0.0]]))
    result = rag_verify_index._verify(workspace, manifest, client, 2, cache_path)
    assert not result["ok"]
    assert any("vector shape mismatch" in item for item in result["problems"])
    client.delete_collection("templates_candidate")
    result = rag_verify_index._verify(workspace, manifest, client, 2, cache_path)
    assert not result["ok"]
    assert any("does not exist" in item for item in result["problems"])


def test_verification_closes_client_on_input_failure(tmp_path, monkeypatch):
    class Client:
        closed = False

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(rag_verify_index, "QdrantClient", lambda **_kwargs: client)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"collections": {}}))
    with pytest.raises(ValueError, match="actually built"):
        rag_verify_index.verify(tmp_path, manifest, "unused", 2)
    assert client.closed


def test_partial_publication_uses_only_the_targets_returned_by_verification(tmp_path, monkeypatch):
    operations = []

    class Client:
        closed = False

        def update_collection_aliases(self, change_aliases_operations):
            operations.extend(change_aliases_operations)

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(
        rag_publish_alias,
        "verify",
        lambda *_args: {
            "ok": True,
            "collection_names": {"template": "verified"},
            "expected_counts": {"verified": 2},
            "sampled_points": 2,
            "service_counts": {"verified": 2},
        },
    )
    monkeypatch.setattr(rag_publish_alias, "QdrantClient", lambda **_kwargs: client)
    # A manifest replacement after verification must not change the publication.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"collection_names": {"wiki": "wrong", "template": "wrong"}}))
    monkeypatch.setattr(
        sys,
        "argv",
        ["rag_publish_alias.py", "--workspace", str(tmp_path), "--manifest", str(manifest)],
    )
    rag_publish_alias.main()
    assert [(op.create_alias.alias_name, op.create_alias.collection_name) for op in operations] == [
        ("templates", "verified")
    ]
    assert client.closed
