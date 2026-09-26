import gzip
import json
import sqlite3
from types import SimpleNamespace

from aigc.agent.contracts import SearchHit
from aigc.rag import QdrantSemanticBackend
from aigc.rag_catalog import WikiCatalog
from scripts.rag_build_bodies import build


def _tiny_workspace(tmp_path):
    wiki = tmp_path / "output" / "wiki-v1"
    wiki.mkdir(parents=True)
    chunks = [
        {
            "chunk_id": "wiki:1:0000",
            "source_id": 1,
            "chunk_index": 0,
            "chunk_count": 1,
            "title": "cat_ears",
            "text": "cat_ears\n\nCat ears.",
        },
        {
            "chunk_id": "wiki:2:0000",
            "source_id": 2,
            "chunk_index": 0,
            "chunk_count": 1,
            "title": "fox_ears",
            "text": "fox_ears\n\nFox ears.",
        },
    ]
    names = [
        {"source_id": 1, "title": "cat_ears", "aliases": ["nekomimi"]},
        {"source_id": 2, "title": "fox_ears", "aliases": ["animal ears"]},
    ]
    for path, rows in (
        (wiki / "wiki-chunks.jsonl.gz", chunks),
        (wiki / "wiki-names.jsonl.gz", names),
    ):
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
    (wiki / "manifest.json").write_text(
        json.dumps(
            {
                "outputs": {
                    "wiki-chunks.jsonl.gz": {"sha256": "chunks"},
                    "wiki-names.jsonl.gz": {"sha256": "names"},
                }
            }
        )
    )
    tag_db = tmp_path / "tag.sqlite"
    with sqlite3.connect(tag_db) as connection:
        connection.execute(
            "CREATE TABLE tags(name TEXT PRIMARY KEY, category INTEGER, "
            "cn_name TEXT, post_count INTEGER)"
        )
        connection.executemany(
            "INSERT INTO tags VALUES(?,?,?,?)",
            [
                ("cat_ears", 0, "猫耳", 100),
                ("fox_ears", 0, "兽耳", 50),
            ],
        )
    return tag_db


def test_catalog_builds_bodies_and_provenance_aware_names(tmp_path):
    tag_db = _tiny_workspace(tmp_path)
    path = tmp_path / "output" / "index-v2" / "wiki-bodies.sqlite3"

    result = build(tmp_path, path, tag_db)
    catalog = WikiCatalog(path)

    assert result["chunks"] == 2
    assert result["canonical_names"] == 2
    assert result["translated_names"] == 2
    assert catalog.summary("wiki:1:0000") == "Cat ears."
    canonical = catalog.resolve_name("cat ears")
    assert canonical.safe_pin.source_id == "1"
    assert canonical.pin_reason == "unique_canonical"
    translated = catalog.resolve_name("猫耳")
    assert translated.safe_pin.source_id == "1"
    assert translated.safe_pin.provenance == "translated_name"
    alias = catalog.resolve_name("nekomimi")
    assert alias.safe_pin is None
    assert [item.source_id for item in alias.candidates] == ["1"]


def test_colliding_translation_is_not_a_safe_pin(tmp_path):
    tag_db = _tiny_workspace(tmp_path)
    with sqlite3.connect(tag_db) as connection:
        connection.execute("UPDATE tags SET cn_name='兽耳' WHERE name='cat_ears'")
    path = tmp_path / "catalog.sqlite3"
    build(tmp_path, path, tag_db)

    resolution = WikiCatalog(path).resolve_name("兽耳")

    assert resolution.safe_pin is None
    assert {item.source_id for item in resolution.translated_name} == {"1", "2"}


def test_safe_exact_resolution_pins_an_existing_dense_hit():
    backend = object.__new__(QdrantSemanticBackend)
    match = SimpleNamespace(source_id="2", title="cat_ears", provenance="translated_name")
    backend.settings = SimpleNamespace(
        catalog=SimpleNamespace(resolve_name=lambda _query: SimpleNamespace(safe_pin=match)),
        config={"AIGC_RAG_EXACT_RESOLVER": "1"},
    )
    hits = [
        SearchHit(
            doc_id="wiki:1", kind="wiki", title="one", match="semantic", score=0.9, source_id="1"
        ),
        SearchHit(
            doc_id="wiki:2",
            kind="wiki",
            title="cat_ears",
            match="semantic",
            score=0.8,
            source_id="2",
            matched_fields=["definition"],
        ),
    ]

    result = backend._prepend_safe_name("猫耳", hits, limit=2)

    assert [hit.source_id for hit in result] == ["2", "1"]
    assert result[0].match == "alias"
    assert result[0].name_provenance == "translated_name"
    assert result[0].matched_fields == ["name", "definition"]
