"""Semantic retrieval over the Qdrant collections built by the RAG workspace.

This module is the only place the CASTER backend talks to the vector index, and
it is deliberately narrow:

* the encoder is lazy, defaults to CPU, and is reused across queries;
* a query returns hits aggregated by ``source_id`` - one wiki entry can be several
  points (one per chunk plus a name point) and would otherwise fill the whole
  candidate list on its own;
* name/alias points are marked ``name_only``: they can support a name match but
  they are not evidence about the entry's body, and callers must not quote them
  as one;
* a failure raises :class:`RagUnavailable`. It is never swallowed into an empty
  result, so the caller can say that semantic search is down instead of quietly
  returning fewer hits.

The vector index is never a source of business truth: template hits are re-read
from the business store by the retrieval service before they can be used.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .agent.contracts import SearchHit
from .config import flag
from .config import load as load_config
from .rag_catalog import CatalogUnavailable, WikiCatalog


class RagUnavailable(RuntimeError):
    """The semantic index cannot be queried right now."""


class BodyStore(WikiCatalog):
    """Compatibility name for the versioned local wiki catalog."""

    def _connection(self):
        try:
            return super()._connection()
        except CatalogUnavailable as error:
            raise RagUnavailable(str(error)) from error


class RagSettings:
    """Where the index lives and which encoder produced it."""

    def __init__(self, config: dict[str, Any] | None = None):
        config = config if config is not None else load_config()
        self.config = dict(config)
        workspace = Path(str(config.get("AIGC_RAG_DIR") or "").strip())
        if not workspace.is_dir():
            raise RagUnavailable("未配置 AIGC_RAG_DIR，或该目录不存在：" + str(workspace))
        self.workspace = workspace
        self.qdrant_url = str(config.get("AIGC_RAG_QDRANT_URL") or "http://127.0.0.1:6333")
        self.wiki_alias = str(config.get("AIGC_RAG_WIKI_ALIAS") or "wiki")
        self.template_alias = str(config.get("AIGC_RAG_TEMPLATE_ALIAS") or "templates")
        manifest_path = workspace / "models" / "manifest.json"
        if not manifest_path.is_file():
            raise RagUnavailable("模型清单不存在：" + str(manifest_path))
        models = json.loads(manifest_path.read_text()).get("models", {})
        key = str(config.get("AIGC_RAG_MODEL_KEY") or "qwen3-embedding-0.6b")
        if key not in models:
            raise RagUnavailable("模型清单里没有 " + key)
        entry = models[key]
        self.model_key = key
        self.model_path = Path(entry["local_path"])
        self.commit = str(entry.get("commit") or "")
        self.dim = int(config.get("AIGC_RAG_DIM") or 1024)
        self.max_length = int(config.get("AIGC_RAG_MAX_LENGTH") or 2048)
        # The query instruction is part of the encoder identity: the published
        # index was built with one, and querying with another mixes vector spaces.
        from .rag_encoder import DEFAULT_INSTRUCTION

        self.instruction = str(config.get("AIGC_RAG_INSTRUCTION") or DEFAULT_INSTRUCTION)
        # The published manifest is the single source for where this build's
        # artefacts live: switching the published index switches the body store
        # with it, instead of leaving a hardcoded path behind.
        self.manifest_path = (
            workspace
            / "output"
            / str(config.get("AIGC_RAG_INDEX_VERSION") or "index-v2")
            / "manifest.json"
        )
        self.catalog = BodyStore(self.manifest_path.parent / "wiki-bodies.sqlite3")
        # Older callers use this name for the same versioned catalog.
        self.bodies = self.catalog

    def index_manifest(self) -> dict[str, Any]:
        """The manifest of the published index build, if it is present.

        The fingerprint in it was computed by the build script, which owns the
        encoder; this side compares the recorded *fields* against its own
        settings instead of recomputing the hash, so the two can never disagree
        about the formula while still disagreeing about the configuration.
        """
        if not self.manifest_path.is_file():
            return {}
        try:
            return json.loads(self.manifest_path.read_text())
        except ValueError:
            return {}

    def matches_published_index(self) -> bool:
        return not self.mismatch_reason()

    def published_encoders(self) -> list[str]:
        """Every encoder fingerprint this manifest records anywhere.

        Diagnostic: a manifest can carry several if a collection was rebuilt with
        another model. What the query side may actually use is decided by
        :meth:`mismatch_reason`, which holds each collection to the build's own
        encoder - a single query encoder cannot answer for two vector spaces.
        """
        manifest = self.index_manifest()
        sources = [manifest.get("model") or {}]
        sources.extend((manifest.get("collections") or {}).values())
        found = []
        for source in sources:
            # The model block calls it 'fingerprint' and each collection block
            # 'encoder_fingerprint'; both are the value the build recorded.
            for key in ("encoder_fingerprint", "fingerprint"):
                value = (source or {}).get(key)
                if value:
                    found.append(value)
        return list(dict.fromkeys(found))

    def published_collections(self, manifest: dict | None = None) -> dict[str, str]:
        """Alias name -> physical collection, as recorded by this manifest.

        The manifest keys the roles it built; which alias answers for a role is
        configuration, so a manifest written before an alias was renamed still
        resolves. An empty mapping means this manifest cannot tell the process
        which collections are its own, and the caller must refuse rather than
        guess a name.
        """
        manifest = self.index_manifest() if manifest is None else manifest
        names = manifest.get("collection_names") or {}
        roles = {
            "wiki": self.wiki_alias,
            "template": self.template_alias,
            "templates": self.template_alias,
        }
        return {roles.get(role, role): collection for role, collection in names.items()}

    def mismatch_reason(self, manifest: dict | None = None) -> str:
        """Why the local encoder cannot be used against the published index.

        Three things have to agree: the encoder fields, the encoder fingerprint
        (which also covers the query instruction and the pooling version), and
        the physical collections the manifest built. A fingerprint-only check
        would miss an instruction change; a fields-only check would miss a
        republished index built by a different encoder with the same fields.
        """
        manifest = self.index_manifest() if manifest is None else manifest
        model = manifest.get("model") or {}
        if not model:
            return "找不到已发布索引的 manifest：" + str(self.manifest_path)
        for field, mine, theirs in (
            ("commit", self.commit, model.get("commit")),
            ("dim", self.dim, model.get("dim")),
            ("max_length", self.max_length, model.get("max_length")),
            ("instruction", self.instruction, model.get("task")),
            ("fingerprint", self._fingerprint(), model.get("fingerprint")),
        ):
            if theirs in (None, ""):
                continue
            if str(mine) != str(theirs):
                return (
                    "编码器配置与已发布索引不一致：%s 本地 %s、索引 %s；换模型/维度/截断长度"
                    "/instruction 必须重新建库并切换 alias" % (field, mine, theirs)
                )
        # Every collection this build wrote must have been written by the encoder
        # this process is about to query with. Comparing against the set of
        # recorded fingerprints would let a collection's own claim satisfy the
        # check, so the comparison is against the build's encoder directly.
        for name, info in (manifest.get("collections") or {}).items():
            recorded = (info or {}).get("encoder_fingerprint")
            if recorded and recorded != model.get("fingerprint"):
                return (
                    "collection %s 的编码器指纹 %s 与本次构建的 %s 不一致；"
                    "混合编码器的索引无法用单一查询编码器查询"
                    % (name, recorded, model.get("fingerprint"))
                )
        return ""

    def _fingerprint(self) -> str:
        """The fingerprint of the encoder this process would use.

        Computed from the same fields the build script records, so the two cannot
        disagree about the formula while disagreeing about the configuration.
        """
        from .rag_encoder import fingerprint

        return fingerprint(self.commit, self.dim, self.max_length, self.instruction)

    def verify_alias_targets(self, live: dict[str, str], manifest: dict | None = None) -> str:
        """Why the live alias does not point where this manifest says it should.

        Publishing switches the alias; the application picks the manifest through
        configuration. If the two disagree, the query would run against a
        collection this manifest never verified.
        """
        expected = self.published_collections(manifest)
        if not expected:
            return "manifest 没有记录 collection 名称，无法校验 alias：" + str(self.manifest_path)
        missing = [alias for alias, name in expected.items() if alias not in live]
        if missing:
            return "Qdrant 上没有这些 alias：" + "、".join(missing)
        drifted = [
            "%s -> %s（manifest 说 %s）" % (alias, live[alias], name)
            for alias, name in expected.items()
            if live[alias] != name
        ]
        if drifted:
            return "alias 指向与 manifest 不一致：" + "；".join(drifted)
        return ""


class _PublishedIndex:
    """Guards shared by everything that touches the published index.

    Reading and writing are the same risk: both would happily work against a
    collection built by another encoder, or against an alias that no longer
    points at what this manifest built. A write is worse - it would inject
    vectors from a different space into a collection that looks consistent.
    """

    def __init__(self, settings: RagSettings):
        self.settings = settings
        self._client = None
        self._encoder = None
        self._lock = threading.Lock()
        self._closed = False
        # Filled in when the encoder is first built; reported so an operator can
        # see which device answered instead of inferring it from the latency.
        self.encoder_device = "not loaded"
        self.encoder_device_reason = ""

    # -- lazy resources ----------------------------------------------------- #
    @property
    def client(self):
        if self._closed:
            raise RagUnavailable("检索资源已关闭")
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as error:  # pragma: no cover - dependency is optional
                raise RagUnavailable("未安装 qdrant-client：" + str(error))
            self._client = QdrantClient(url=self.settings.qdrant_url, prefer_grpc=False, timeout=30)
        return self._client

    @property
    def encoder(self):
        """Reader and writer use the same configuration and pooling implementation."""
        if self._closed:
            raise RagUnavailable("检索资源已关闭")
        if self._encoder is None:
            with self._lock:
                if self._encoder is None:
                    import torch

                    from .rag_encoder import Encoder

                    torch.set_num_threads(
                        _config_value(self.settings.config, "AIGC_RAG_CPU_THREADS", 16)
                    )
                    device, reason = encoder_device(
                        self.settings.config.get("AIGC_RAG_DEVICE") or "cpu"
                    )
                    self.encoder_device = device
                    self.encoder_device_reason = reason
                    self._encoder = Encoder(
                        self.settings.model_path,
                        self.settings.dim,
                        self.settings.max_length,
                        device=device,
                        batch_size=1,
                        commit=self.settings.commit,
                        instruction=self.settings.instruction,
                    )
        return self._encoder

    def close(self) -> None:
        """Release a loaded HTTP client and model without initializing either."""
        self._closed = True
        client, self._client = self._client, None
        self._encoder = None
        if client is not None:
            client.close()

    def _refusal(self, alias: str) -> str:
        """Why ``alias`` may not be used, or '' when it may."""
        try:
            self._checked_collection(alias)
        except RagUnavailable as error:
            return str(error)
        return ""

    def _checked_collection(self, alias: str) -> str:
        """Pin one operation to a physical collection from one verified manifest."""
        manifest = self.settings.index_manifest()
        reason = self.settings.mismatch_reason(manifest)
        if reason:
            raise RagUnavailable(reason)
        expected = self.settings.published_collections(manifest)
        if not expected:
            raise RagUnavailable(
                "manifest 没有记录 collection 名称，无法校验 alias："
                + str(self.settings.manifest_path)
            )
        if alias not in expected:
            raise RagUnavailable(
                "alias %s 不是本次构建发布的名称（已发布：%s）"
                % (
                    alias,
                    "、".join("%s->%s" % item for item in expected.items()),
                )
            )
        # Objects live as long as the application. A successful earlier query
        # cannot authorize a later query after a deployment switched the alias.
        live = {a.alias_name: a.collection_name for a in self.client.get_aliases().aliases}
        drift = self.settings.verify_alias_targets(live, manifest)
        if drift:
            raise RagUnavailable(drift)
        return expected[alias]

    def _client_or_unavailable(self):
        try:
            return self.client
        except RagUnavailable:
            raise
        except Exception as error:  # pragma: no cover - connection setup
            raise RagUnavailable(
                "语义检索不可用：" + type(error).__name__ + "：" + str(error)[:200]
            )


class QdrantSemanticBackend(_PublishedIndex):
    """The :class:`~aigc.agent.retrieval.SemanticBackend` seam, implemented."""

    def __init__(
        self, settings: RagSettings, overfetch: int = 4, wiki_overfetch: int | None = None
    ):
        super().__init__(settings)
        self.overfetch = overfetch
        # Wiki points are per chunk, so an entry can occupy several slots. A
        # wider pool keeps the chunks of the best-matching entries in play,
        # which is what makes a hit body evidence instead of a name match.
        #
        # Tune the pool against a frozen evaluation set when changing corpora.
        self.wiki_overfetch = (
            wiki_overfetch
            if wiki_overfetch is not None
            else max(1, _config_value(settings.config, "AIGC_RAG_WIKI_OVERFETCH", 50))
        )

    # -- search ------------------------------------------------------------- #
    def status(self) -> dict[str, Any]:
        try:
            collections = {c.name for c in self.client.get_collections().collections}
            aliases = {a.alias_name: a.collection_name for a in self.client.get_aliases().aliases}
            manifest = self.settings.index_manifest()
            index_model = manifest.get("model") or {}
            return {
                "semantic_available": True,
                "model_key": self.settings.model_key,
                "commit": self.settings.commit,
                "dim": self.settings.dim,
                "index_fingerprint": index_model.get("fingerprint"),
                "index_matches_settings": self.settings.matches_published_index(),
                "wiki_alias_target": aliases.get(self.settings.wiki_alias),
                "template_alias_target": aliases.get(self.settings.template_alias),
                "collections": sorted(collections),
            }
        except Exception as error:  # a dead service is a state, not a crash
            return {
                "semantic_available": False,
                "semantic_reason": type(error).__name__ + "：" + str(error)[:200],
            }

    # The retrieval service speaks in document kinds ('character_template'), the
    # tools speak in short forms ('character'). Both are accepted here, so a
    # caller cannot fail the whole semantic branch over a vocabulary difference.
    TEMPLATE_KINDS = {
        "character": "character_template",
        "outfit": "outfit_template",
        "character_template": "character_template",
        "outfit_template": "outfit_template",
    }

    def search(self, query: str, kind: str | None, limit: int) -> list[SearchHit]:
        """Template-scoped semantic search, aggregated by template id."""
        wanted = self.TEMPLATE_KINDS.get(kind or "")
        if kind and not wanted:
            raise ValueError(
                "kind must be character, outfit, character_template or "
                "outfit_template, got " + str(kind)
            )
        points = self._query(self.settings.template_alias, query, max(limit, 1) * self.overfetch)
        best: dict[str, dict[str, Any]] = {}
        for point in points:
            payload = point.payload or {}
            point_kind = payload.get("kind")
            if wanted and point_kind != wanted:
                continue
            template_id = payload.get("template_id") or payload.get("doc_id")
            if not template_id:
                continue
            current = best.get(template_id)
            if current is None or point.score > current["score"]:
                best[template_id] = {"score": point.score, "payload": payload}
        return [
            self._hit(template_id, entry)
            for template_id, entry in sorted(best.items(), key=lambda item: -item[1]["score"])
        ][:limit]

    def search_wiki(self, query: str, limit: int) -> list[SearchHit]:
        """Wiki-scoped semantic search, aggregated by wiki source id.

        Aggregate the complete candidate pool before selecting representatives,
        so several chunks from one source cannot fill the final result list.
        The pool size is configurable independently of the displayed hit count.
        """
        raw_limit = max(limit, 1) * self.wiki_overfetch
        entries = self._wiki_entries(self._query(self.settings.wiki_alias, query, raw_limit))
        hits = self._wiki_hits(entries, limit)
        hits = self._prepend_safe_name(query, hits, limit)
        self._attach_first_body(hits)
        return hits

    def search_wiki_fused(self, queries: list[str], limit: int) -> list[SearchHit]:
        """Fuse several Qwen query rankings by source-level reciprocal rank.

        Fusion happens before the final source limit. Calling ``search_wiki``
        once per query would truncate each branch first and lose a source that
        is moderately strong in both rankings. Each branch keeps the same raw
        point budget as the measured dense baseline.
        """
        queries = list(dict.fromkeys(query.strip() for query in queries if query.strip()))
        if not queries:
            return []
        rankings: list[list[str]] = []
        entries_by_query: list[dict[str, dict[str, Any]]] = []
        raw_limit = max(limit, 1) * self.wiki_overfetch
        for query in queries:
            entries = self._wiki_entries(self._query(self.settings.wiki_alias, query, raw_limit))
            entries_by_query.append(entries)
            rankings.append(
                [
                    source_id
                    for source_id, _entry in sorted(
                        entries.items(), key=lambda item: -item[1]["score"]
                    )
                ]
            )
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        for ranking in rankings:
            for position, source_id in enumerate(ranking):
                scores[source_id] = scores.get(source_id, 0.0) + 1.0 / (60 + position + 1)
                best_rank[source_id] = min(best_rank.get(source_id, position), position)

        def source_key(source_id: str):
            try:
                return 0, int(source_id)
            except (TypeError, ValueError):
                return 1, str(source_id)

        order = sorted(
            scores,
            key=lambda source_id: (-scores[source_id], best_rank[source_id], source_key(source_id)),
        )
        fused: dict[str, dict[str, Any]] = {}
        for source_id in order[: max(1, limit)]:
            # Prefer the untouched user-query payload when it found the source;
            # its chunk is the closest evidence to what the user actually wrote.
            entry = next(entries[source_id] for entries in entries_by_query if source_id in entries)
            fused[source_id] = dict(entry, score=scores[source_id])
        hits = self._wiki_hits(fused, limit, presorted=True)
        hits = self._prepend_safe_name(queries[0], hits, limit)
        self._attach_first_body(hits)
        return hits

    def _prepend_safe_name(self, query: str, hits: list[SearchHit], limit: int) -> list[SearchHit]:
        """Pin only a unique canonical or unique reviewed translation match."""
        if not flag(self.settings.config, "AIGC_RAG_EXACT_RESOLVER"):
            return hits
        try:
            resolution = self.settings.catalog.resolve_name(query)
        except (CatalogUnavailable, RagUnavailable, ValueError):
            return hits
        match = resolution.safe_pin
        if match is None:
            return hits
        existing = next((hit for hit in hits if hit.source_id == match.source_id), None)
        if existing is None:
            existing = SearchHit(
                doc_id="wiki:%s" % match.source_id,
                kind="wiki",
                title=match.title,
                summary=match.title,
                source="https://danbooru.donmai.us/wiki_pages/%s" % match.source_id,
                match=("exact" if match.provenance == "canonical" else "alias"),
                score=1.0,
                source_id=match.source_id,
                name_only=True,
                matched_fields=["name"],
                name_provenance=match.provenance,
            )
        else:
            existing.match = "exact" if match.provenance == "canonical" else "alias"
            existing.name_provenance = match.provenance
            if "name" not in existing.matched_fields:
                existing.matched_fields.insert(0, "name")
        return [existing, *(hit for hit in hits if hit.source_id != match.source_id)][
            : max(1, limit)
        ]

    @staticmethod
    def _wiki_entries(points) -> dict[str, dict[str, Any]]:
        """Best payload per source, preserving a body chunk when one surfaced."""
        best: dict[str, dict[str, Any]] = {}
        for point in points:
            payload = point.payload or {}
            source_id = payload.get("source_id") or payload.get("doc_id")
            if not source_id:
                continue
            source_id = str(source_id)
            current = best.get(source_id)
            if current is None or point.score > current["score"]:
                best[source_id] = {"score": point.score, "payload": payload}
            # A name point can outscore the entry's own chunks for a name-like
            # query, but a chunk carries the body. When both are in the pool the
            # hit is body evidence; the ranking keeps the better score.
            if (
                current is not None
                and payload.get("kind") == "chunk"
                and current["payload"].get("kind") == "name"
            ):
                best[source_id]["chunk_payload"] = payload
        for entry in best.values():
            if entry.get("chunk_payload"):
                entry["payload"] = entry["chunk_payload"]
        return best

    def _wiki_hits(
        self, entries: dict[str, dict[str, Any]], limit: int, presorted: bool = False
    ) -> list[SearchHit]:
        items = list(entries.items())
        if not presorted:
            items.sort(key=lambda item: -item[1]["score"])
        return [self._wiki_hit(source_id, entry) for source_id, entry in items[: max(1, limit)]]

    def _attach_first_body(self, hits: list[SearchHit]) -> None:
        # A query about a name often surfaces only the entry's name point. The
        # body is still attached when the body store has it, and the hit keeps
        # saying the ranking signal came from the name.
        for hit in hits:
            if hit.name_only and not hit.chunk_id:
                try:
                    record = self.settings.bodies.first_chunk(hit.source_id or "")
                except RagUnavailable:
                    # Without the body store the hit can still support a name
                    # match; it just cannot carry the body evidence.
                    record = None
                if record:
                    hit.chunk_id = record["chunk_id"]

    # -- internals ---------------------------------------------------------- #
    def body_summary(self, chunk_id: str, limit: int = 400) -> str:
        """A traceable excerpt of a chunk body, for wiki hits.

        The excerpt is cut from the stored body, never paraphrased, so what the
        agent quotes can be checked against the corpus. A name point has no body
        and is never passed here. A body store that is missing or unreadable
        costs the excerpt, not the hit.
        """
        try:
            return self.settings.bodies.summary(chunk_id, limit)
        except RagUnavailable:
            return ""

    def _query(self, alias: str, query: str, limit: int):
        try:
            # A same-dimension model swap would otherwise return a plausible
            # looking ranking built from a different vector space. Refuse and let
            # the caller fall back to the deterministic path. The alias is
            # resolved against the live service too: publishing switches the
            # alias, so an unswitched or republished alias must not be queried as
            # if it were this build.
            collection = self._checked_collection(alias)
            vector = self.encoder.encode_query(query)
            response = self.client.query_points(
                collection_name=collection, query=vector.tolist(), limit=limit, with_payload=True
            )
            return list(response.points)
        except RagUnavailable:
            raise
        except Exception as error:
            raise RagUnavailable(
                "语义检索不可用：" + type(error).__name__ + "：" + str(error)[:200]
            )

    @staticmethod
    def _hit(template_id: str, entry: dict[str, Any]) -> SearchHit:
        payload = entry["payload"]
        return SearchHit(
            doc_id=template_id,
            kind=payload.get("kind") or "character_template",
            template_id=template_id,
            title=payload.get("title") or template_id,
            summary=payload.get("title") or "",
            source="vector-index",
            source_revision=payload.get("source_revision") or "",
            match="semantic",
            score=round(float(entry["score"]), 4),
            preview_url=payload.get("source_url") or None,
        )

    @staticmethod
    def _wiki_hit(source_id: str, entry: dict[str, Any]) -> SearchHit:
        payload = entry["payload"]
        score = entry["score"]
        name_only = payload.get("kind") == "name"
        chunk_id = payload.get("chunk_id")
        summary_bits = [payload.get("title") or ""]
        if chunk_id:
            summary_bits.append(
                "chunk %s/%s" % (payload.get("chunk_index"), payload.get("chunk_count"))
            )
        return SearchHit(
            doc_id="wiki:%s" % source_id,
            kind="wiki",
            template_id=None,
            title=payload.get("title") or str(source_id),
            summary="；".join(b for b in summary_bits if b)[:2000],
            source=payload.get("source_url") or "",
            source_revision=payload.get("source_revision") or "",
            match="semantic",
            score=round(float(score), 4),
            preview_url=payload.get("source_url") or None,
            source_id=str(source_id),
            chunk_id=chunk_id,
            name_only=name_only,
            matched_fields=(entry.get("matched_fields") or ["name" if name_only else "definition"]),
        )


def _config_value(values, key: str, default: int) -> int:
    try:
        return int(values.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def encoder_device(configured: str = "") -> tuple[str, str]:
    """The device the online encoder should run on, and why.

    ``AIGC_RAG_DEVICE`` decides it. Measured on the deployment machine for this
    model: a single short query is p50 26.5 ms on a 4090 versus 147.1 ms on CPU,
    so a GPU is the better default *here* - but a GPU is only used when one is
    actually present and has room, because the encoder is not more important
    than the ComfyUI job that shares the card. The reason is returned so the
    caller can say which device answered instead of leaving it implied.
    """
    wanted = str(configured or load_config().get("AIGC_RAG_DEVICE") or "cpu").strip()
    if not wanted.lower().startswith(("cuda", "gpu")):
        return "cpu", "配置为 CPU"
    try:
        import torch

        if not torch.cuda.is_available():
            return "cpu", "没有可用的 CUDA 设备，退回 CPU"
        free, _total = torch.cuda.mem_get_info()
        # bf16 0.6B is ~1.2 GB of weights; leave headroom for activations.
        if free < 2 * 1024**3:
            return "cpu", "GPU 显存不足（空闲 %.1f GB），退回 CPU" % (free / 1e9)
    except Exception as error:  # no torch, or no driver
        return "cpu", "GPU 不可用（%s），退回 CPU" % type(error).__name__
    if wanted.lower() in ("gpu", "cuda"):
        return "cuda:0", "使用第一个 GPU"
    return wanted, "按配置使用 " + wanted


def build_backend(config: dict[str, Any] | None = None) -> QdrantSemanticBackend | None:
    """Return a backend, or ``None`` with a reason when the index is not configured.

    ``None`` means "semantic search is unavailable", which the retrieval service
    reports to the caller; a broken service raises :class:`RagUnavailable` at
    query time so the failure is visible per request instead of being cached.
    """
    try:
        return QdrantSemanticBackend(RagSettings(config))
    except RagUnavailable:
        return None


class TemplateIndexWriter(_PublishedIndex):
    """Incremental writes to the published template collection.

    The offline build fills this collection from a read-only snapshot; this class
    is what keeps it current while the service runs, one template at a time. It
    reuses :mod:`aigc.rag_index` for the point ID, the payload and the document
    text, so a point written here is indistinguishable from a built one and the
    next verification cannot report drift on it.

    Every operation is idempotent: the point ID is a function of the document,
    so re-delivering the same template replaces its own point, and deleting an
    absent point is not an error. That is what makes a retry after a crash safe.

    The guards are the reader's guards: a writer that refused to check would
    inject vectors from a different encoder into a collection that still looks
    internally consistent.
    """

    def __init__(self, settings: RagSettings):
        super().__init__(settings)
        # Version marker for the corpus of a single incrementally written
        # document. It never reaches the payload; it exists so the document can
        # carry a ``version`` field like a built one. The build's snapshot
        # version covers every template at once, so it cannot be computed here.
        self.version = "templates-live"

    @property
    def collection(self) -> str:
        """The physical collection the template alias points at right now."""
        return self.settings.published_collections().get(self.settings.template_alias, "")

    def upsert(self, record: dict[str, Any]) -> str:
        """Encode one business template record and write its point.

        Returns the point ID, which is a function of the document - never of the
        delivery - so the caller can log what it wrote without trusting it.
        """
        alias = self.settings.template_alias
        collection = self._checked_collection(alias)
        from qdrant_client import models as qdrant_models

        from .rag_index import payload_of, point_id, template_document

        document = template_document(record, self.version)
        vector = self.encoder.encode_documents([document["text"]])[0]
        identifier = point_id(document)
        self.client.upsert(
            collection_name=collection,
            points=[
                qdrant_models.PointStruct(
                    id=identifier, vector=vector.tolist(), payload=payload_of(document)
                )
            ],
            wait=True,
        )
        return identifier

    def delete(self, template_id: str) -> int:
        """Remove every point of one template. Deleting an absent point is a no-op.

        By payload filter rather than by point ID: the point ID contains the
        document kind, and by the time a template is deleted the record that
        would have said which kind it was is already gone.
        """
        alias = self.settings.template_alias
        collection = self._checked_collection(alias)
        from qdrant_client import models as qdrant_models

        selector = qdrant_models.FilterSelector(
            filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="doc_id", match=qdrant_models.MatchValue(value=str(template_id))
                    )
                ]
            )
        )
        return self.client.delete(collection_name=collection, points_selector=selector, wait=True)

    def status(self) -> dict[str, Any]:
        try:
            alias = self.settings.template_alias
            target = self.collection
            count = self.client.count(collection_name=target, exact=True).count if target else None
            return {
                "write_available": True,
                "collection": target,
                "alias": alias,
                "points": count,
                "encoder_matches_index": self.settings.matches_published_index(),
                "alias_points_at_manifest": not self._refusal(alias),
                "encoder_device": self.encoder_device,
                "encoder_device_reason": self.encoder_device_reason,
                # The encoder is lazy, so "which device answered" stays empty
                # until something has queried. The planned device answers the
                # operator's actual question without loading a model.
                "encoder_device_planned": list(
                    encoder_device(self.settings.config.get("AIGC_RAG_DEVICE") or "cpu")
                ),
            }
        except Exception as error:  # a dead service is a state, not a crash
            return {
                "write_available": False,
                "reason": type(error).__name__ + "：" + str(error)[:200],
                "encoder_device": self.encoder_device,
                "encoder_device_reason": self.encoder_device_reason,
                "encoder_device_planned": list(encoder_device()),
            }


def build_writer(config: dict[str, Any] | None = None) -> TemplateIndexWriter | None:
    """A writer, or ``None`` when no index is configured.

    ``None`` means "there is nothing to sync into", which the sync loop reports
    as unavailable rather than treating as an empty queue.
    """
    try:
        return TemplateIndexWriter(RagSettings(config))
    except RagUnavailable:
        return None
