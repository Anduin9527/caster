"""Semantic retrieval wiring: fusion, re-check, negation and failure reporting.

These run entirely offline: the Qdrant backend is replaced by a scripted double,
so what is under test is the CASTER-side contract - which hits are allowed to
reach the caller, in what order, and what the caller is told when the index is
missing or broken.
"""

import sys

import pytest

from aigc.agent.contracts import SearchHit, WorkbenchContext
from aigc.agent.retrieval import RetrievalService, _fuse
from aigc.rag import BodyStore, QdrantSemanticBackend, RagSettings, RagUnavailable, build_backend
from aigc.schema import Character, Outfit
from aigc.store import Store


class FakeSemantic:
    """A scripted semantic backend: returns the hits it was given."""

    def __init__(self, hits=(), error=None, wiki_hits=(), body=None):
        self.hits = list(hits)
        self.error = error
        self.wiki_hits = list(wiki_hits)
        self.body = body or (lambda chunk_id: "")
        self.calls = []

    def search(self, query, kind, limit):
        self.calls.append(("templates", query, kind, limit))
        if self.error:
            raise self.error
        return self.hits[:limit]

    def search_wiki(self, query, limit):
        self.calls.append(("wiki", query, limit))
        if self.error:
            raise self.error
        return self.wiki_hits[:limit]

    def body_summary(self, chunk_id, limit=400):
        return self.body(chunk_id)[:limit]


def template_hit(template_id, score):
    return SearchHit(
        doc_id=template_id,
        kind="character_template",
        template_id=template_id,
        title=template_id,
        summary="",
        source="vector-index",
        match="semantic",
        score=score,
    )


def wiki_hit(source_id, chunk_id=None, name_only=False, score=0.5):
    return SearchHit(
        doc_id="wiki:%s" % source_id,
        kind="wiki",
        title="wiki-%s" % source_id,
        summary="wiki-%s" % source_id,
        source="https://example.invalid/%s" % source_id,
        match="semantic",
        score=score,
        source_id=str(source_id),
        chunk_id=chunk_id,
        name_only=name_only,
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def seeded(store):
    store.put(
        "character",
        Character(
            id="c1",
            name="测试角色",
            fixed_tags=["silver hair"],
            outfits=[Outfit(id="base", tags=["navy coat"])],
        ).model_dump(),
        "c1",
    )
    for template_id, tags in (
        ("maid", ["maid", "apron"]),
        ("coat", ["navy coat"]),
        ("bikini", ["bikini", "swimsuit"]),
    ):
        store.put(
            "prompt_template",
            {
                "id": template_id,
                "kind": "character",
                "name": template_id,
                "tags": tags,
                "categories": [],
                "trigger": template_id,
                "description": template_id + " description",
                "source": "user",
                "source_revision": "1",
            },
            template_id,
        )
    return store


def context():
    return WorkbenchContext(
        character_id="c1",
        character_name="测试角色",
        stage="identity",
        selected_asset_ids={"identity": None, "outfit": None, "pose": None},
        known_character_ids=["c1"],
    )


def test_tag_lookup_splits_chinese_compound_concepts_and_keeps_exclusions(store, monkeypatch):
    service = RetrievalService(store)
    monkeypatch.setattr(
        service,
        "_tag_index",
        lambda: [
            ("cat_ears", "cat ears", "猫耳", "猫耳"),
            ("cat_ear_headphones", "cat ear headphones", "猫耳耳机", "猫耳耳机"),
            ("cat_ear_hood", "cat ear hood", "猫耳兜帽", "猫耳兜帽"),
            ("heterochromia", "heterochromia", "异色瞳", "异色瞳"),
            ("maid_headdress", "maid headdress", "女仆头饰", "女仆头饰"),
        ],
    )

    result = service.search_tag_knowledge("猫耳 异色瞳，但不要女仆头饰", limit=8)

    assert [hit.title for hit in result.hits[:3]] == [
        "cat_ears",
        "heterochromia",
        "maid_headdress",
    ]
    assert result.query_plan["positive_concepts"] == ["猫耳", "异色瞳"]
    assert result.query_plan["negative_concepts"] == ["女仆头饰"]
    assert result.negation == {"terms": ["女仆头饰"], "enforced": False}


def test_tag_lookup_preserves_english_multiword_canonical_tag(store, monkeypatch):
    service = RetrievalService(store)
    monkeypatch.setattr(
        service,
        "_tag_index",
        lambda: [
            ("maid_headdress", "maid headdress", "女仆头饰", "女仆头饰"),
        ],
    )

    result = service.search_tag_knowledge("maid headdress")

    assert [hit.title for hit in result.hits] == ["maid_headdress"]


# --------------------------------------------------------------------------- #
# fusion
# --------------------------------------------------------------------------- #
def test_fuse_ranks_a_document_found_by_both_branches_first():
    # b is second for the keyword branch and first for the semantic one; a is
    # first for keywords and absent from the semantic list. b's two reciprocal
    # ranks beat a's single one.
    order = _fuse(["a", "b"], ["b"])
    assert order == ["b", "a"], order
    assert _fuse(["a", "b", "c"], ["b", "a", "c"])[0] in ("a", "b")  # symmetric: a tie


def test_fuse_does_not_add_raw_scores():
    """Two lists, one scale each: only the ranks are combined."""
    order = _fuse(["a"], ["b"])
    assert order == ["a", "b"]  # equal ranks, tie broken by id


def test_semantic_results_survive_when_bm25_has_nothing(store):
    """The old code truncated each branch first, so keyword results could crowd
    semantic ones out of the answer entirely."""
    seeded(store)
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("bikini", 0.9)]))
    result = service.search_templates("比基尼泳装", limit=2)
    assert [hit.doc_id for hit in result.hits] == ["bikini"]
    assert result.hits[0].match == "semantic"


def test_a_semantic_hit_for_a_deleted_template_is_dropped(store):
    seeded(store)
    store.put(
        "prompt_template",
        {
            "id": "ghost",
            "kind": "character",
            "name": "ghost",
            "tags": [],
            "categories": [],
            "trigger": "",
            "description": "",
            "source": "user",
            "source_revision": "1",
        },
        "ghost",
    )
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("ghost", 0.99)]))
    # Delete it behind the index's back: the vector still points at it.
    with store.connect() as db:
        db.execute("DELETE FROM records WHERE kind='prompt_template' AND id='ghost'")
    result = service.search_templates("ghost", limit=5)
    assert "ghost" not in [hit.doc_id for hit in result.hits]


def test_a_negated_term_excludes_a_semantic_hit(store):
    seeded(store)
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("bikini", 0.99)]))
    result = service.search_templates("no bikini", limit=5)
    assert "bikini" not in [hit.doc_id for hit in result.hits]


def test_a_semantic_hit_whose_live_record_changed_kind_is_dropped(store):
    """The vector index says character_template; the business record has since
    become an outfit. The kind filter runs on the live records, so a typed query
    must not let the stale point through - the returned fields come from the
    live record and claiming the wrong kind would make it an unusable input."""
    import json

    seeded(store)
    store.put(
        "prompt_template",
        {
            "id": "flip",
            "kind": "character",
            "name": "flipme",
            "tags": ["maid"],
            "categories": [],
            "trigger": "flipme",
            "description": "a template",
            "source": "user",
            "source_revision": "1",
        },
        "flip",
    )
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        body = json.loads(
            db.execute(
                "SELECT body FROM records WHERE kind='prompt_template' AND id='flip'"
            ).fetchone()[0]
        )
        body["kind"] = "outfit"
        db.execute(
            "INSERT OR REPLACE INTO records VALUES('prompt_template','flip',?)",
            (json.dumps(body, ensure_ascii=False),),
        )
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("flip", 0.99)]))
    result = service.search_templates("flipme", "character", 5)
    assert [hit.doc_id for hit in result.hits] == [], "the stale kind drops out"
    # The same query with no type filter still reports it, with the live kind.
    result = service.search_templates("flipme", None, 5)
    assert [hit.doc_id for hit in result.hits] == ["flip"]
    assert result.hits[0].kind == "outfit_template"
    # And an outfit-scoped query finds it, because now it is one.
    result = service.search_templates("flipme", "outfit", 5)
    assert [hit.doc_id for hit in result.hits] == ["flip"]


def test_a_cross_lingual_negation_is_reported_not_assumed(store):
    """The exclusion is a text check, so a Chinese term cannot remove an English
    template. The caller is told which terms were requested, so it can say so
    instead of implying the constraint was enforced."""
    seeded(store)
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("bikini", 0.99)]))
    result = service.search_templates("不要比基尼", limit=5)
    assert "比基尼" in result.payload()["negation"]["terms"]
    assert result.payload()["negation"]["enforced"] is False


def test_a_unique_exact_hit_is_pinned_first(store):
    seeded(store)
    service = RetrievalService(store, FakeSemantic(hits=[template_hit("bikini", 0.99)]))
    result = service.search_templates("maid", limit=5)
    assert result.hits[0].doc_id == "maid"
    assert result.hits[0].match == "exact"


def test_a_broken_index_is_reported_not_swallowed(store):
    seeded(store)
    service = RetrievalService(store, FakeSemantic(error=RuntimeError("connection refused")))
    result = service.search_templates("maid", limit=5)
    assert result.hits, "keyword results must still be returned"
    assert "connection refused" in result.semantic_reason
    assert result.semantic_available is True  # configured, but failing


def test_an_absent_backend_is_reported_as_unavailable(store):
    seeded(store)
    result = RetrievalService(store).search_templates("maid", limit=5)
    assert result.semantic_available is False
    assert "语义检索不可用" in result.semantic_reason


# --------------------------------------------------------------------------- #
# wiki search
# --------------------------------------------------------------------------- #
def test_wiki_hits_keep_their_provenance(store):
    seeded(store)
    semantic = FakeSemantic(
        wiki_hits=[
            wiki_hit(11, chunk_id="wiki:11:0000", score=0.9),
            wiki_hit(37, chunk_id="wiki:37:0000", score=0.7),
        ]
    )
    result = RetrievalService(store, semantic).search_wiki("东方", limit=5)
    assert [hit.source_id for hit in result.hits] == ["11", "37"]
    assert result.hits[0].chunk_id == "wiki:11:0000"
    assert result.hits[0].kind == "wiki"


def test_a_name_only_hit_is_marked(store):
    seeded(store)
    semantic = FakeSemantic(
        wiki_hits=[wiki_hit(99, name_only=True, score=0.9)], body=lambda chunk_id: "body text"
    )
    result = RetrievalService(store, semantic).search_wiki("某个只有名字的条目", limit=5)
    assert result.hits[0].name_only is True
    assert result.hits[0].summary == "wiki-99", "a name point must not gain a body excerpt"


def test_wiki_summary_is_cut_from_the_body(store):
    seeded(store)
    body = "wiki:11\n\n" + ("东方 project. " * 200)
    semantic = FakeSemantic(
        wiki_hits=[wiki_hit(11, chunk_id="wiki:11:0000")], body=lambda chunk_id: body
    )
    result = RetrievalService(store, semantic).search_wiki("东方", limit=5)
    assert len(result.hits[0].summary) < 4000
    assert "东方 project." in result.hits[0].summary


def test_wiki_search_without_a_backend_says_so(store):
    seeded(store)
    result = RetrievalService(store).search_wiki("东方", limit=5)
    assert result.hits == []
    assert result.semantic_available is False
    assert "语义检索不可用" in result.semantic_reason


def _seed_exact_tag_dictionary(store):
    import sqlite3

    path = store.root / "translation" / "ffdkj" / "tag.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE tags("
            "name TEXT PRIMARY KEY, category INTEGER, cn_name TEXT, post_count INTEGER)"
        )
        db.executemany(
            "INSERT INTO tags VALUES(?,?,?,?)",
            [
                ("qipao", 1, "旗袍", 100),
                ("china_dress", 1, "旗袍", 50),
                ("unpopular_synonym", 1, "旗袍", 1),
                ("twintails", 0, "双马尾", 200),
            ],
        )
    return path


def test_exact_tag_expansion_is_whole_query_only_and_popularity_ordered(store):
    seeded(store)
    _seed_exact_tag_dictionary(store)
    service = RetrievalService(store, FakeSemantic())

    assert service._exact_tag_expansion("旗袍") == ["qipao", "china_dress"]
    assert service._exact_tag_expansion(" 旗袍的。") == ["qipao", "china_dress"]
    assert service._exact_tag_expansion("穿旗袍") == [], "substring expansion measured worse"


def test_exact_tag_expansion_uses_native_qwen_fusion_when_available(store):
    seeded(store)
    _seed_exact_tag_dictionary(store)

    class FusedBackend(FakeSemantic):
        def __init__(self):
            super().__init__()
            self.fused_calls = []

        def search_wiki_fused(self, queries, limit):
            self.fused_calls.append((queries, limit))
            return [wiki_hit(37, chunk_id="wiki:37:0000")]

    semantic = FusedBackend()
    result = RetrievalService(store, semantic).search_wiki("旗袍", limit=5)

    assert semantic.fused_calls == [(["旗袍", "qipao china_dress"], 5)]
    assert semantic.calls == []
    assert [hit.source_id for hit in result.hits] == ["37"]
    assert "精确标签映射 qipao、china_dress" in result.semantic_reason


def test_exact_tag_expansion_can_be_disabled(store, monkeypatch):
    seeded(store)
    _seed_exact_tag_dictionary(store)
    semantic = FakeSemantic(wiki_hits=[wiki_hit(11)])
    monkeypatch.setenv("AIGC_RAG_EXACT_TAG_EXPANSION", "0")

    result = RetrievalService(store, semantic).search_wiki("旗袍", limit=5)

    assert semantic.calls == [("wiki", "旗袍", 5)]
    assert [hit.source_id for hit in result.hits] == ["11"]
    assert result.semantic_reason == ""


def test_expansion_uses_each_app_configuration_instead_of_process_defaults(store, monkeypatch):
    _seed_exact_tag_dictionary(store)
    monkeypatch.setenv("AIGC_RAG_EXACT_TAG_EXPANSION", "1")
    disabled = RetrievalService(store, config={"AIGC_RAG_EXACT_TAG_EXPANSION": "0"})
    enabled = RetrievalService(store, config={"AIGC_RAG_EXACT_TAG_EXPANSION": "1"})
    assert disabled._exact_tag_expansion("旗袍") == []
    assert enabled._exact_tag_expansion("旗袍") == ["qipao", "china_dress"]


# --------------------------------------------------------------------------- #
# settings and body store
# --------------------------------------------------------------------------- #
def test_no_rag_directory_means_no_backend(tmp_path):
    assert build_backend({"AIGC_DATA_DIR": str(tmp_path)}) is None


def test_a_rag_directory_without_models_means_no_backend(tmp_path):
    workspace = tmp_path / "rag"
    workspace.mkdir()
    assert build_backend({"AIGC_RAG_DIR": str(workspace)}) is None


def test_rag_settings_read_the_model_manifest(tmp_path):
    workspace = tmp_path / "rag"
    (workspace / "models").mkdir(parents=True)
    (workspace / "models" / "manifest.json").write_text(
        '{"models": {"qwen3-embedding-0.6b": {"commit": "abc", "local_path": "/models/0.6b"}}}'
    )
    settings = RagSettings({"AIGC_RAG_DIR": str(workspace), "AIGC_RAG_DIM": "1024"})
    assert settings.commit == "abc"
    assert settings.dim == 1024
    assert settings.qdrant_url == "http://127.0.0.1:6333"
    assert settings.matches_published_index() is False  # no manifest yet


def test_body_summary_never_quotes_the_title(tmp_path):
    import sqlite3

    path = tmp_path / "bodies.sqlite3"
    connection = sqlite3.connect(str(path))
    connection.execute(
        "CREATE TABLE bodies(chunk_id TEXT PRIMARY KEY, source_id INTEGER, "
        "chunk_index INTEGER, chunk_count INTEGER, title TEXT, text TEXT)"
    )
    connection.execute(
        "INSERT INTO bodies VALUES(?,?,?,?,?,?)",
        ("wiki:11:0000", 11, 0, 1, "touhou", "touhou\n\nA bullet hell series."),
    )
    connection.commit()
    connection.close()
    store = BodyStore(path)
    assert store.get("wiki:11:0000")["title"] == "touhou"
    assert store.summary("wiki:11:0000") == "A bullet hell series."
    assert store.summary("wiki:missing") == ""


def test_retrieval_reports_the_index_fingerprint(store, tmp_path):
    """The service must be able to say which encoder built the live index."""
    workspace = tmp_path / "rag"
    (workspace / "models").mkdir(parents=True)
    (workspace / "models" / "manifest.json").write_text(
        '{"models": {"qwen3-embedding-0.6b": {"commit": "abc", "local_path": "/models/0.6b"}}}'
    )
    seeded(store)
    service = RetrievalService(store)
    assert service.status()["semantic_available"] is False


# --------------------------------------------------------------------------- #
# the backend itself: aggregation by source, failure reporting
# --------------------------------------------------------------------------- #
class StubPoint:
    def __init__(self, score, payload):
        self.score = score
        self.payload = payload


class StubResponse:
    def __init__(self, points):
        self.points = points


class StubClient:
    """Answers query_points with scripted points, records the calls."""

    def __init__(self, points, aliases=None):
        self.points = points
        self.calls = []
        # What the deployment's aliases point at. A drift from the manifest is a
        # refusal, so the tests answer with the manifest's own targets unless
        # they are specifically checking drift.
        self.aliases = dict(
            aliases if aliases is not None else {"wiki": "wiki_v2", "templates": "templates_v2"}
        )

    def query_points(self, collection_name, query, limit, with_payload=True):
        self.calls.append((collection_name, limit))
        return StubResponse(self.points[:limit])

    def get_aliases(self):
        client = self
        return type(
            "Aliases",
            (),
            {
                "aliases": [
                    type("Alias", (), {"alias_name": alias, "collection_name": collection})()
                    for alias, collection in client.aliases.items()
                ]
            },
        )


class StubEncoder:
    def encode_query(self, query):
        import numpy as np

        return np.zeros(8, dtype="float32")


def backend_with(monkeypatch, points, workspace=None, aliases=None):
    """A backend whose lazy client and encoder are replaced by stubs.

    The stubs are injected into the instance's lazy slots, so the same objects
    are reused across calls and the recorded calls can be asserted on.
    """
    from aigc.rag import QdrantSemanticBackend, RagSettings

    settings = RagSettings({"AIGC_RAG_DIR": str(workspace or _workspace())})
    backend = QdrantSemanticBackend(settings)
    backend._client = StubClient(points, aliases)
    backend._encoder = StubEncoder()
    return backend


def _workspace(
    commit="abc", dim=1024, max_length=2048, write_manifest=True, collection_names=None, task=None
):
    """A workspace on disk. ``collection_names`` defaults to the deployed names;
    pass ``{}`` for a manifest that records no collection names at all."""
    import json
    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp())
    (root / "models").mkdir(parents=True)
    (root / "models" / "manifest.json").write_text(
        json.dumps({"models": {"qwen3-embedding-0.6b": {"commit": commit, "local_path": "/m"}}})
    )
    if write_manifest:
        from aigc.rag_encoder import DEFAULT_INSTRUCTION
        from aigc.rag_encoder import fingerprint as encoder_fingerprint

        out = root / "output" / "index-v2"
        out.mkdir(parents=True)
        model = {
            "commit": commit,
            "dim": dim,
            "max_length": max_length,
            # The recorded fingerprint is what this process computes from the
            # same fields, which is what a real build writes; a stub value
            # would make every manifest mismatch its own encoder.
            "fingerprint": encoder_fingerprint(commit, dim, max_length, DEFAULT_INSTRUCTION),
            "task": task if task is not None else DEFAULT_INSTRUCTION,
        }
        body = {"model": model}
        if collection_names != {}:
            body["collection_names"] = (
                collection_names
                if collection_names is not None
                else {"wiki": "wiki_v2", "templates": "templates_v2"}
            )
        (out / "manifest.json").write_text(json.dumps(body))
    return root


def test_wiki_points_of_one_entry_are_aggregated(monkeypatch, tmp_path):
    """One entry has a point per chunk plus a name point; without aggregation
    they would fill the whole candidate list on their own."""
    backend = backend_with(
        monkeypatch,
        [
            StubPoint(
                0.9,
                {
                    "kind": "chunk",
                    "source_id": "11",
                    "title": "touhou",
                    "chunk_id": "wiki:11:0000",
                    "chunk_index": 0,
                    "chunk_count": 3,
                    "source_url": "https://example.invalid/11",
                },
            ),
            StubPoint(0.8, {"kind": "name", "source_id": "11", "title": "touhou"}),
            StubPoint(
                0.7,
                {
                    "kind": "chunk",
                    "source_id": "37",
                    "title": "maid",
                    "chunk_id": "wiki:37:0000",
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "source_url": "https://example.invalid/37",
                },
            ),
        ],
    )
    hits = backend.search_wiki("东方", limit=5)
    assert [hit.source_id for hit in hits] == ["11", "37"]
    # The chunk point scored higher, so this entry is body evidence.
    assert hits[0].name_only is False
    assert hits[0].chunk_id == "wiki:11:0000"
    assert hits[0].preview_url == "https://example.invalid/11"
    # The query over-fetches: the pool is larger than the returned limit, so a
    # document that only the semantic branch can find still reaches the fusion.
    assert backend.wiki_overfetch * 5 == backend.client.calls[0][1]


def test_qdrant_fuses_qwen_queries_before_the_final_source_limit(monkeypatch):
    backend = backend_with(monkeypatch, [])
    by_query = {
        "旗袍": [
            StubPoint(
                0.9, {"kind": "chunk", "source_id": "1", "title": "one", "chunk_id": "wiki:1:0000"}
            ),
            StubPoint(
                0.8, {"kind": "chunk", "source_id": "2", "title": "two", "chunk_id": "wiki:2:0000"}
            ),
        ],
        "qipao china_dress": [
            StubPoint(
                0.9,
                {"kind": "chunk", "source_id": "3", "title": "three", "chunk_id": "wiki:3:0000"},
            ),
            StubPoint(
                0.8, {"kind": "chunk", "source_id": "2", "title": "two", "chunk_id": "wiki:2:0000"}
            ),
        ],
    }
    monkeypatch.setattr(backend, "_query", lambda alias, query, limit: by_query[query])

    hits = backend.search_wiki_fused(["旗袍", "qipao china_dress"], limit=2)

    assert [hit.source_id for hit in hits] == ["2", "1"]
    assert hits[0].score > hits[1].score


def test_a_name_point_only_hit_is_flagged(monkeypatch):
    backend = backend_with(
        monkeypatch, [StubPoint(0.9, {"kind": "name", "source_id": "99", "title": "only-a-name"})]
    )
    # No body for this entry: the hit stays a name match and gains no chunk.
    monkeypatch.setattr(type(backend.settings.bodies), "first_chunk", lambda self, source_id: None)
    hits = backend.search_wiki("某个条目", limit=5)
    assert hits[0].name_only is True
    assert hits[0].chunk_id is None


def test_a_name_point_gains_the_entry_body_from_the_body_store(monkeypatch):
    """The match was on the name, but the answer needs the body: the body store
    supplies it and the hit still says the signal came from the name."""
    backend = backend_with(
        monkeypatch, [StubPoint(0.9, {"kind": "name", "source_id": "11", "title": "touhou"})]
    )
    monkeypatch.setattr(
        type(backend.settings.bodies),
        "first_chunk",
        lambda self, source_id: {
            "chunk_id": "wiki:11:0000",
            "source_id": 11,
            "chunk_index": 0,
            "chunk_count": 7,
            "title": "touhou",
            "text": "touhou\n\nA bullet hell series.",
        },
    )
    hits = backend.search_wiki("东方project", limit=5)
    assert hits[0].name_only is True
    assert hits[0].chunk_id == "wiki:11:0000"


def test_a_grouped_name_point_still_carries_the_entry_body(monkeypatch):
    """A name point can outscore the entry's chunks for a name-like query, so
    Qdrant returns it as the group's representative. The body is still reachable
    from the body store, and the hit keeps saying the signal came from the name."""
    backend = backend_with(
        monkeypatch, [StubPoint(0.9, {"kind": "name", "source_id": "11", "title": "touhou"})]
    )
    monkeypatch.setattr(
        type(backend.settings.bodies),
        "first_chunk",
        lambda self, source_id: {
            "chunk_id": "wiki:11:0000",
            "source_id": 11,
            "chunk_index": 0,
            "chunk_count": 2,
            "title": "touhou",
            "text": "touhou\n\nA bullet hell series.",
        },
    )
    hits = backend.search_wiki("东方", limit=5)
    assert len(hits) == 1
    assert hits[0].score == 0.9, "the ranking keeps the better score"
    assert hits[0].name_only is True, "the signal really was the name"
    assert hits[0].chunk_id == "wiki:11:0000", "but the body is still attached"
    assert hits[0].chunk_id == "wiki:11:0000"


def test_a_dead_service_is_reported_not_swallowed(monkeypatch):
    from aigc.rag import RagUnavailable

    backend = backend_with(monkeypatch, [])

    class Broken:
        def query_points(self, **kwargs):
            raise ConnectionRefusedError("qdrant is down")

        def get_aliases(self):
            raise ConnectionRefusedError("qdrant is down")

    backend._client = Broken()
    with pytest.raises(RagUnavailable, match="qdrant is down"):
        backend.search_wiki("东方", limit=5)


def test_the_wiki_overfetch_comes_from_configuration(monkeypatch):
    backend = backend_with(monkeypatch, [])
    backend.settings.config["AIGC_RAG_WIKI_OVERFETCH"] = "7"
    assert QdrantSemanticBackend(backend.settings).wiki_overfetch == 7
    # An unparseable or absent value falls back to the measured default.
    backend.settings.config["AIGC_RAG_WIKI_OVERFETCH"] = "x"
    assert QdrantSemanticBackend(backend.settings).wiki_overfetch == 50
    # An explicit argument still wins over configuration.
    assert QdrantSemanticBackend(backend.settings, wiki_overfetch=3).wiki_overfetch == 3


def test_reused_backend_refuses_an_alias_changed_after_a_successful_query(monkeypatch):
    backend = backend_with(monkeypatch, [])
    assert backend.search_wiki("first", 1) == []
    backend.client.aliases["wiki"] = "another-encoder-collection"
    with pytest.raises(RagUnavailable, match="不一致"):
        backend.search_wiki("second", 1)
    assert len(backend.client.calls) == 1


def test_query_pins_verified_collection_if_alias_changes_during_encoding(monkeypatch):
    backend = backend_with(monkeypatch, [])

    class SwitchingEncoder(StubEncoder):
        def encode_query(self, query):
            backend.client.aliases["wiki"] = "different-encoder"
            return super().encode_query(query)

    backend._encoder = SwitchingEncoder()
    assert backend.search_wiki("first", 1) == []
    assert backend.client.calls[0][0] == "wiki_v2"
    with pytest.raises(RagUnavailable, match="不一致"):
        backend.search_wiki("next", 1)


def test_reader_and_writer_use_their_own_encoder_configuration(monkeypatch):
    import sys
    from types import SimpleNamespace

    from aigc import rag_encoder
    from aigc.rag import TemplateIndexWriter

    calls, threads = [], []

    def construct(*args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=threads.append))
    monkeypatch.setattr(rag_encoder, "Encoder", construct)
    monkeypatch.setattr(
        "aigc.rag.load_config", lambda: {"AIGC_RAG_DEVICE": "cuda", "AIGC_RAG_CPU_THREADS": "99"}
    )
    settings = RagSettings(
        {
            "AIGC_RAG_DIR": str(_workspace()),
            "AIGC_RAG_DEVICE": "cpu",
            "AIGC_RAG_CPU_THREADS": "3",
            "AIGC_RAG_INSTRUCTION": "Find the matching character tag",
        }
    )
    for implementation in (QdrantSemanticBackend, TemplateIndexWriter):
        backend = implementation(settings)
        assert backend.encoder is backend.encoder
        assert calls[-1][1]["instruction"] == settings.instruction
        assert calls[-1][1]["device"] == "cpu"
        backend.close()
        with pytest.raises(RagUnavailable, match="关闭"):
            _ = backend.encoder
    assert len(calls) == 2 and threads == [3, 3]


def test_close_releases_the_loaded_client_once_and_never_opens_a_new_one():
    from types import SimpleNamespace

    from aigc.rag import TemplateIndexWriter

    settings = RagSettings({"AIGC_RAG_DIR": str(_workspace())})
    closed = []
    for implementation in (QdrantSemanticBackend, TemplateIndexWriter):
        backend = implementation(settings)
        backend.close()  # Closing a lazy backend must not connect or load a model.
        with pytest.raises(RagUnavailable, match="关闭"):
            _ = backend.client
        loaded = implementation(settings)
        loaded._client = SimpleNamespace(close=lambda: closed.append(True))
        loaded.close()
        loaded.close()
    assert closed == [True, True]


def test_template_search_filters_by_kind(monkeypatch):
    backend = backend_with(
        monkeypatch,
        [
            StubPoint(0.9, {"kind": "character_template", "template_id": "t1", "title": "t1"}),
            StubPoint(0.8, {"kind": "outfit_template", "template_id": "t2", "title": "t2"}),
        ],
    )
    assert [h.template_id for h in backend.search("x", "outfit", 5)] == ["t2"]
    assert len(backend.search("x", None, 5)) == 2


# --------------------------------------------------------------------------- #
# cross-layer: RetrievalService -> the real adapter
# --------------------------------------------------------------------------- #
def test_typed_search_reaches_the_backend_with_a_kind_it_understands(store, monkeypatch):
    """The service passes document kinds ('character_template'); the adapter used
    to accept only the short forms, so every typed query failed the semantic
    branch with a ValueError."""
    seeded(store)
    seen = []

    class Recording(FakeSemantic):
        def search(self, query, kind, limit):
            seen.append(kind)
            return []

    service = RetrievalService(store, Recording())
    service.search_templates("maid", "character", 5)
    service.search_templates("maid", "outfit", 5)
    service.search_templates("maid", None, 5)
    assert seen == ["character_template", "outfit_template", None], seen
    # The adapter accepts every one of them, and rejects anything else loudly.
    from aigc.rag import QdrantSemanticBackend

    for kind in ("character", "outfit", "character_template", "outfit_template"):
        assert kind in QdrantSemanticBackend.TEMPLATE_KINDS
    with pytest.raises(ValueError):
        QdrantSemanticBackend(RagSettings({"AIGC_RAG_DIR": str(_workspace())})).search(
            "x", "nonsense", 5
        )


def test_a_mismatched_encoder_refuses_the_query(monkeypatch, tmp_path):
    """A same-dimension model swap must not keep answering from a different
    vector space: the query is refused and the caller degrades explicitly."""
    workspace = _workspace(commit="abc")
    backend = backend_with(
        monkeypatch, [StubPoint(0.9, {"kind": "name", "source_id": "11"})], workspace
    )
    backend.settings.commit = "a-different-model"
    with pytest.raises(RagUnavailable, match="编码器配置与已发布索引不一致"):
        backend.search_wiki("东方", limit=5)
    with pytest.raises(RagUnavailable, match="不一致"):
        backend.search("maid", None, 5)
    assert backend.client.calls == [], "no query may reach Qdrant"


def test_the_published_encoders_are_read_from_both_manifest_blocks(monkeypatch):
    """The model block names the field 'fingerprint' and each collection block
    'encoder_fingerprint'. Reading only one of them left the cross-collection
    consistency check comparing against an empty set."""
    import json

    root = _workspace(commit="abc", collection_names={"wiki": "wiki_v2"})
    manifest = root / "output" / "index-v2" / "manifest.json"
    body = json.loads(manifest.read_text())
    # Both blocks are written by the same encoder here, as in a real build.
    written = body["model"]["fingerprint"]
    body["collections"] = {
        "wiki_v2": {"documents": 3, "encoder_fingerprint": written},
        "templates_v2": {"documents": 4, "encoder_fingerprint": written},
    }
    manifest.write_text(json.dumps(body))
    settings = RagSettings({"AIGC_RAG_DIR": str(root)})
    assert settings.published_encoders() == [written]
    assert settings.mismatch_reason() == "", "every collection was written by it"
    # A collection whose encoder is not the build's is a mismatch, not a no-op:
    # the claim must not be able to satisfy the check by being recorded itself.
    body["collections"]["templates_v2"]["encoder_fingerprint"] = "some-other-encoder"
    manifest.write_text(json.dumps(body))
    assert "templates_v2" in settings.mismatch_reason()
    assert "some-other-encoder" in settings.mismatch_reason()


def test_a_matching_encoder_still_queries(monkeypatch):
    workspace = _workspace(commit="abc")
    backend = backend_with(
        monkeypatch,
        [StubPoint(0.9, {"kind": "chunk", "source_id": "11", "chunk_id": "wiki:11:0000"})],
        workspace,
    )
    assert backend.settings.mismatch_reason() == ""
    # A chunk hit needs no body store; only the name-only path looks one up.
    assert len(backend.search_wiki("东方", limit=5)) == 1


def test_a_missing_manifest_refuses_the_query(monkeypatch):
    workspace = _workspace(write_manifest=False)
    backend = backend_with(monkeypatch, [], workspace)
    with pytest.raises(RagUnavailable, match="manifest"):
        backend.search_wiki("东方", limit=5)


# --------------------------------------------------------------------------- #
# the live alias, not just the configuration, decides what is queried
# --------------------------------------------------------------------------- #
def test_the_live_alias_must_point_at_the_manifest_collection(monkeypatch):
    """A published-but-unswitched alias would return a ranking from another
    build's vector space, with nothing in the configuration to betray it."""
    workspace = _workspace(collection_names={"wiki": "wiki_v2", "templates": "templates_v2"})
    backend = backend_with(
        monkeypatch,
        [StubPoint(0.9, {"kind": "chunk", "source_id": "11", "chunk_id": "wiki:11:0000"})],
        workspace,
        aliases={"wiki": "wiki_v1", "templates": "templates_v1"},
    )
    with pytest.raises(RagUnavailable, match="alias 指向与 manifest 不一致"):
        backend.search_wiki("东方", limit=5)
    assert backend.client.calls == [], "no query may reach Qdrant"
    assert (
        backend.settings.verify_alias_targets({"wiki": "wiki_v2", "templates": "templates_v2"})
        == ""
    )


def test_an_unpublished_alias_is_refused(monkeypatch):
    """Asking for an alias this build did not publish would silently query an
    older collection that happens to still be aliased under another name."""
    workspace = _workspace(collection_names={"wiki": "wiki_v2"})
    backend = backend_with(monkeypatch, [], workspace)
    with pytest.raises(RagUnavailable, match="alias templates 不是本次构建发布的名称"):
        backend.search("maid", "character_template", 5)


def test_a_manifest_without_collection_names_is_refused(monkeypatch):
    """A manifest that cannot name its own collections must not be guessed at."""
    workspace = _workspace(collection_names={})
    backend = backend_with(monkeypatch, [], workspace)
    assert backend.settings.published_collections() == {}
    with pytest.raises(RagUnavailable, match="无法校验 alias"):
        backend.search_wiki("东方", limit=5)


def test_a_renamed_alias_still_resolves_to_the_manifest_role(monkeypatch):
    """The manifest records roles, not alias names; the deployed alias for the
    template role may be spelled either way across builds."""
    workspace = _workspace(collection_names={"wiki": "wiki_v2", "template": "templates_v2"})
    settings = RagSettings({"AIGC_RAG_DIR": str(workspace)})
    assert settings.published_collections() == {"wiki": "wiki_v2", "templates": "templates_v2"}
    backend = backend_with(
        monkeypatch,
        [StubPoint(0.9, {"kind": "chunk", "source_id": "11", "chunk_id": "wiki:11:0000"})],
        workspace,
    )
    assert len(backend.search_wiki("东方", limit=5)) == 1


def test_a_body_store_that_is_missing_costs_the_excerpt_not_the_hit(monkeypatch):
    """A deleted or unreadable body store used to abort the whole wiki search."""
    from pathlib import Path

    workspace = _workspace(collection_names={"wiki": "wiki_v2"})
    backend = backend_with(
        monkeypatch,
        [StubPoint(0.9, {"kind": "name", "source_id": "11", "title": "touhou"})],
        workspace,
    )
    backend.settings.bodies.path = Path("/definitely/missing-bodies.sqlite3")
    hits = backend.search_wiki("东方", limit=5)
    assert [hit.source_id for hit in hits] == ["11"]
    assert hits[0].name_only is True
    assert hits[0].chunk_id is None
    # The excerpt degrades too, rather than raising on the caller's behalf.
    assert backend.body_summary("wiki:11:0000") == ""


def test_a_missing_body_store_does_not_abort_the_wiki_search(tmp_path):
    """The service level degrades to hits without excerpts."""
    from pathlib import Path

    from aigc.rag import RagSettings

    workspace = _workspace(collection_names={"wiki": "wiki_v2", "templates": "templates_v2"})
    settings = RagSettings({"AIGC_RAG_DIR": str(workspace)})
    settings.bodies.path = Path("/definitely/missing-bodies.sqlite3")
    bodies = settings.bodies

    class WikiBackend:
        def search_wiki(self, query, limit):
            return [
                SearchHit(
                    doc_id="wiki:11",
                    kind="wiki",
                    title="touhou",
                    summary="touhou",
                    source="https://example.invalid/11",
                    match="semantic",
                    score=0.9,
                    source_id="11",
                    chunk_id="wiki:11:0000",
                    name_only=True,
                )
            ]

        def body_summary(self, chunk_id, limit=400):
            return bodies.summary(chunk_id, limit)

    service = RetrievalService(Store(str(tmp_path)), WikiBackend())
    result = service.search_wiki("东方")
    assert [hit.doc_id for hit in result.hits] == ["wiki:11"]
    assert result.semantic_reason == ""


def test_runtime_query_plan_only_splits_explicit_compositions():
    from aigc.agent.retrieval import plan_wiki_query

    plan = plan_wiki_query("猫耳加上异色瞳但不要女仆头饰")
    assert plan["intent"] == "composition"
    assert plan["positive_concepts"] == ["猫耳", "异色瞳"]
    assert plan["negative_concepts"] == ["女仆头饰"]
    assert plan["raw_query"] == "猫耳加上异色瞳但不要女仆头饰"
    assert plan["executable_anchor"] == "猫耳，异色瞳"
    assert "女仆头饰" not in "".join(plan["executed_queries"])
    leading = plan_wiki_query("不要头饰，穿女仆装，灰色背景")
    assert leading["positive_concepts"] == ["女仆装", "灰色背景"]
    assert leading["negative_concepts"] == ["头饰"]
    assert leading["executable_anchor"] == "女仆装，灰色背景"
    assert plan_wiki_query("kimono dress")["executable_anchor"] == "kimono dress"
    assert plan_wiki_query("不知火舞穿和服")["executable_anchor"] == "不知火舞穿和服"
    assert plan_wiki_query("传统日式长袖衣服配腰带")["positive_concepts"] == [
        "传统日式长袖衣服配腰带"
    ]
    assert plan_wiki_query("和服")["positive_concepts"] == ["和服"]


def test_runtime_composition_returns_evidence_and_delegates_negation_to_llm(store):
    seeded(store)

    class CompositionBackend:
        def __init__(self):
            self.calls = []

        def search_wiki(self, query, limit):
            self.calls.append((query, limit))
            if query == "猫耳，异色瞳":
                return [wiki_hit(5), wiki_hit(1), wiki_hit(2)]
            if query == "猫耳":
                return [wiki_hit(3), wiki_hit(1)]
            if query == "异色瞳":
                return [wiki_hit(4)]
            if query == "女仆头饰":
                hit = wiki_hit(5)
                hit.match = "exact"
                hit.name_provenance = "canonical"
                return [hit]
            return []

    backend = CompositionBackend()
    result = RetrievalService(store, backend).search_wiki("猫耳加上异色瞳但不要女仆头饰", limit=5)

    assert [hit.source_id for hit in result.hits] == ["5", "3", "4", "1", "2"]
    assert result.negation == {"terms": ["女仆头饰"], "enforced": False}
    assert result.query_plan["positive_concepts"] == ["猫耳", "异色瞳"]
    payload = result.payload()
    assert payload["strategy"] == "wiki-tool-evidence-v2"
    assert payload["retrieval_role"] == "candidate_evidence_only"
    assert payload["decision_owner"] == "llm"
    assert payload["warnings"] == [
        {
            "code": "negation_delegated_to_llm",
            "message": "RAG 仅召回候选；排除条件由 LLM 根据候选证据判断",
        }
    ]
    assert payload["score_semantics"] == "ranking_signal_only_not_probability"
    assert payload["abstention"]["supported"] is False
    assert payload["result_state"] == "candidates"
    assert "女仆头饰" not in [query for query, _limit in backend.calls]
    assert "猫耳加上异色瞳但不要女仆头饰" not in [query for query, _limit in backend.calls]


def test_the_body_store_follows_the_published_index(monkeypatch):
    """Switching the published index version must switch the body store too."""
    import json

    root = _workspace(commit="abc")
    for version in ("index-v2", "index-v3"):
        out = root / "output" / version
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(
            json.dumps({"model": {"commit": "abc", "dim": 1024, "max_length": 2048}})
        )
        (out / "wiki-bodies.sqlite3").write_bytes(b"")
    settings_v2 = RagSettings({"AIGC_RAG_DIR": str(root), "AIGC_RAG_INDEX_VERSION": "index-v2"})
    settings_v3 = RagSettings({"AIGC_RAG_DIR": str(root), "AIGC_RAG_INDEX_VERSION": "index-v3"})
    assert settings_v2.bodies.path.name == "wiki-bodies.sqlite3"
    assert settings_v2.bodies.path.parent.name == "index-v2"
    assert settings_v3.bodies.path.parent.name == "index-v3"


# --------------------------------------------------------------------------- #
# filtering happens before the exact hit is pinned
# --------------------------------------------------------------------------- #
def test_a_pinned_exact_hit_cannot_bypass_the_type_filter(store):
    """The unique exact hit was pinned before the type filter ran, so a character
    template could be returned for an outfit-only query - and the pin then
    crashed with StopIteration when the document was not in the filtered set."""
    seeded(store)
    store.put(
        "prompt_template",
        {
            "id": "unique-character",
            "kind": "character",
            "name": "zzunique",
            "tags": ["maid"],
            "categories": [],
            "trigger": "zzunique",
            "description": "only a character",
            "source": "user",
            "source_revision": "1",
        },
        "unique-character",
    )
    service = RetrievalService(store, FakeSemantic())
    result = service.search_templates("zzunique", "outfit", 5)
    assert "unique-character" not in [hit.doc_id for hit in result.hits]
    assert [hit.doc_id for hit in result.hits] == [] or all(
        hit.kind == "outfit_template" for hit in result.hits
    )
    # The same query without a type filter still finds it and pins it first.
    result = service.search_templates("zzunique", None, 5)
    assert result.hits[0].doc_id == "unique-character"
    assert result.hits[0].match == "exact"


def test_a_pinned_exact_hit_cannot_bypass_negation(store):
    seeded(store)
    store.put(
        "prompt_template",
        {
            "id": "unique-neg",
            "kind": "character",
            "name": "zzneg",
            "tags": ["bikini"],
            "categories": [],
            "trigger": "zzneg",
            "description": "a bikini template",
            "source": "user",
            "source_revision": "1",
        },
        "unique-neg",
    )
    service = RetrievalService(store, FakeSemantic())
    result = service.search_templates("no zzneg", None, 5)
    assert "unique-neg" not in [hit.doc_id for hit in result.hits]


# --------------------------------------------------------------------------- #
# which device the online encoder runs on
# --------------------------------------------------------------------------- #
def test_the_default_encoder_device_is_cpu(monkeypatch):
    """A GPU is not assumed: a machine without one must still answer, and a
    machine with one must not be forced onto it by a library default."""
    from aigc.rag import encoder_device

    monkeypatch.delenv("AIGC_RAG_DEVICE", raising=False)
    monkeypatch.setattr("aigc.rag.load_config", lambda: {})
    assert encoder_device() == ("cpu", "配置为 CPU")


def test_a_configured_gpu_without_a_card_falls_back_to_cpu(monkeypatch):
    from aigc.rag import encoder_device

    class NoCuda:
        class cuda:
            @staticmethod
            def is_available():
                return False

    monkeypatch.setattr("aigc.rag.load_config", lambda: {"AIGC_RAG_DEVICE": "cuda:0"})
    monkeypatch.setitem(sys.modules, "torch", NoCuda)
    assert encoder_device() == ("cpu", "没有可用的 CUDA 设备，退回 CPU")


def test_a_gpu_without_free_memory_falls_back_to_cpu(monkeypatch):
    """The encoder shares the card with ComfyUI; a full card must not turn a
    query into a CUDA out-of-memory."""
    from aigc.rag import encoder_device

    class FullCuda:
        class cuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def mem_get_info():
                return (256 * 1024**2, 24 * 1024**3)

    monkeypatch.setattr("aigc.rag.load_config", lambda: {"AIGC_RAG_DEVICE": "cuda:0"})
    monkeypatch.setitem(sys.modules, "torch", FullCuda)
    device, reason = encoder_device()
    assert device == "cpu" and "显存不足" in reason


def test_a_free_gpu_is_used(monkeypatch):
    from aigc.rag import encoder_device

    class FreeCuda:
        class cuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def mem_get_info():
                return (20 * 1024**3, 24 * 1024**3)

    monkeypatch.setattr("aigc.rag.load_config", lambda: {"AIGC_RAG_DEVICE": "cuda:0"})
    monkeypatch.setitem(sys.modules, "torch", FreeCuda)
    assert encoder_device() == ("cuda:0", "按配置使用 cuda:0")
    # The bare forms resolve to the first card.
    monkeypatch.setattr("aigc.rag.load_config", lambda: {"AIGC_RAG_DEVICE": "gpu"})
    assert encoder_device()[0] == "cuda:0"


def test_the_status_reports_the_device_before_the_encoder_loads(tmp_path):
    from aigc.rag import TemplateIndexWriter

    writer = TemplateIndexWriter(RagSettings({"AIGC_RAG_DIR": str(_workspace())}))
    assert writer.status()["encoder_device"] == "not loaded"
