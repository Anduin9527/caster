"""Local retrieval that produces :class:`~aigc.agent.contracts.SearchHit`.

Local lookup is dependency-free and deterministic: exact
name/trigger/alias matching first, then a BM25 rank over the live template
records, then type filtering and de-duplication. Semantic recall is
an explicit, swappable seam: :class:`SemanticBackend` is ``None`` until a RAG
collection is built, and callers are told that semantic search is unavailable
instead of being silently downgraded.

Retrieval never returns business state: jobs, selections and approvals are read
from the business store by the tools, not from here.
"""

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ..config import flag as config_flag
from ..config import load as load_config
from ..rag import RagUnavailable
from .contracts import SearchHit

NEGATION_MARKERS = (
    "不要",
    "不能",
    "不可以",
    "不想",
    "不用",
    "不带",
    "不戴",
    "排除",
    "避免",
    "去掉",
    "去除",
    "禁止",
    "别戴",
    "别带",
    "勿用",
    "without",
    "no",
    "not",
)
_NEGATION_MARKER = re.compile(
    r"(?:不要|不能|不可以|不想|不用|不带|不戴|排除|避免|去掉|去除|禁止|别戴|别带|勿用|"
    r"without\b|(?<![A-Za-z])no\b|(?<![A-Za-z])not\b)",
    re.I,
)
_COMPOSITION_SEPARATOR = re.compile(r"(?:加上?|搭配|并且|同时|以及|和(?!服))", re.I)
_NEGATIVE_CLAUSE = re.compile(
    r"(?:但(?:是)?|并且|同时)?(?:不要|不带|不戴|排除|避免|去掉|去除|禁止|without|no\s+)", re.I
)
_FRAGMENT_PREFIX = re.compile(r"^(?:穿着?|戴着?|做出|把)")
_LEADING_PARTICLES = (
    "的",
    "了",
    "着",
    "任何",
    "一个",
    "一些",
    "要",
    "有",
    "也",
    "还",
    "并且",
    "而且",
)
_TRAILING_PARTICLES = ("的", "了", "着", "也", "还")
# CJK ideographs. The basic block (U+4E00-U+9FFF, 一-鿿) is the one that matters
# for Chinese queries; Extension A, compatibility ideographs, kana and hangul are
# included so mixed-script names tokenize too.
_CJK_RUN = re.compile(r"[一-鿿㐀-䶿豈-﫿぀-ヿ가-힯]{2,}")
_CJK_ANY = re.compile(r"[一-鿿㐀-䶿豈-﫿぀-ヿ가-힯]")
_WORD = re.compile(r"[a-z0-9]+")


def _clean_term(text: str) -> str:
    text = text.strip(" .。!！?？,，、;；:：")
    changed = True
    while changed and text:
        changed = False
        for particle in _LEADING_PARTICLES:
            if text.startswith(particle) and len(text) > len(particle):
                text = text[len(particle) :].strip()
                changed = True
        for particle in _TRAILING_PARTICLES:
            if text.endswith(particle) and len(text) > len(particle):
                text = text[: -len(particle)].strip()
                changed = True
    return text


def normalize(text: str) -> str:
    """Case, width, underscore/hyphen and escape-insensitive normalisation."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\\+([()])", r"\1", text)
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def strip_negation(query: str) -> tuple[list[str], list[str]]:
    """Split a query into positive terms and structurally excluded terms.

    ``女仆装 不要帽子`` keeps ``女仆装`` as a positive term and ``帽子`` as an
    excluded term, so a negated requirement is checked against candidate text
    explicitly instead of being left to vector distance.
    """
    positive: list[str] = []
    excluded: list[str] = []

    def split_chunk(chunk: str, negated: bool = False) -> None:
        chunk = chunk.strip()
        if not chunk:
            return
        match = _NEGATION_MARKER.search(chunk)
        if match is None:
            term = _clean_term(chunk)
            if term:
                (excluded if negated else positive).append(term)
            return
        head, tail = chunk[: match.start()], chunk[match.end() :]
        term = _clean_term(head)
        if term:
            (excluded if negated else positive).append(term)
        # Everything after a negation marker is itself a negated requirement, but
        # the tail may contain further negations.
        split_chunk(tail, negated=True)

    for chunk in re.split(r"[,，;；/、]| and |并且|而且", normalize(query)):
        split_chunk(chunk)
    return positive, list(dict.fromkeys(term for term in excluded if term))


def plan_wiki_query(query: str) -> dict[str, Any]:
    """Build the deterministic part of the Wiki query plan.

    Only explicit conjunctions are split. In particular a bare 配 is not a
    separator: phrases such as 传统日式长袖衣服配腰带 describe one visual
    concept and the pilot showed that splitting them manufactures false
    requirements. Negated concepts are kept out of positive vector recall and
    are resolved separately as exclusion constraints.
    """
    raw = (query or "").strip()

    def fragments(text: str) -> list[str]:
        result = []
        for part in _COMPOSITION_SEPARATOR.split(text):
            part = _FRAGMENT_PREFIX.sub("", part.strip(" ，。、")).strip()
            part = re.sub(r"(?:但(?:是)?)$", "", part).strip()
            part = _clean_term(part)
            if part:
                result.append(part)
        return list(dict.fromkeys(result))

    positive_terms, negative_terms = strip_negation(raw)
    positive = list(
        dict.fromkeys(fragment for term in positive_terms for fragment in fragments(term))
    )
    negative = list(
        dict.fromkeys(fragment for term in negative_terms for fragment in fragments(term))
    )
    # The raw request is retained above for provenance only. The vector branch
    # must not include explicit negative clauses, because distance is not a
    # reliable Boolean exclusion operator.
    executable_anchor = "，".join(positive)
    route = (
        "composition"
        if negative or len(positive) > 1
        else (
            "wiki_question"
            if re.search(r"(?:什么|意思|区别|为什么|怎么|how|what|why)", raw, re.I)
            else "visual_concept"
        )
    )
    variants = list(dict.fromkeys(value for value in [executable_anchor, *positive] if value))
    return {
        "raw_query": raw,
        "executable_anchor": executable_anchor,
        "intent": route,
        "positive_concepts": positive,
        "negative_concepts": negative,
        "query_variants": variants,
        "executed_queries": variants,
        # Category routing is intentionally not guessed yet. The current index
        # does not carry a calibrated category route, so claiming one here would
        # turn a future design into a fake present capability.
        "category_routes": [],
    }


def tokenize(text: str) -> list[str]:
    """Latin words plus CJK bigrams, so Chinese queries match without a segmenter."""
    text = normalize(text)
    tokens = [t for t in _WORD.findall(text) if len(t) > 1 or t.isdigit()]
    for match in _CJK_RUN.finditer(text):
        run = match.group()
        # Bigrams for partial overlap, plus the whole run for an exact phrase.
        # A two-character run would otherwise appear twice.
        candidates = [run[i : i + 2] for i in range(len(run) - 1)] + [run]
        tokens.extend(dict.fromkeys(candidates))
    # A lone CJK character forms no bigram; keep it so single-character tags
    # such as "妹" or "娘" are still searchable.
    for match in _CJK_ANY.finditer(text):
        token = match.group()
        if token not in tokens:
            tokens.append(token)
    return tokens


class Document:
    __slots__ = (
        "doc_id",
        "kind",
        "template_id",
        "title",
        "summary",
        "source",
        "source_revision",
        "preview_url",
        "text",
        "tokens",
        "frequency",
        "length",
        "body",
        "norm_text",
        "exact_keys",
    )

    def __init__(
        self,
        doc_id,
        kind,
        template_id,
        title,
        summary,
        source,
        source_revision,
        preview_url,
        text,
        body,
        alias="",
    ):
        self.doc_id = doc_id
        self.kind = kind
        self.template_id = template_id
        self.title = title
        self.summary = summary
        self.source = source
        self.source_revision = source_revision
        self.preview_url = preview_url
        self.text = text
        self.tokens = tokenize(text)
        self.frequency = Counter(self.tokens)
        self.length = max(1, len(self.tokens))
        self.body = body
        # Normalised once at build time: a query must not re-normalise the corpus.
        self.norm_text = normalize(text)
        keys = {normalize(title)}
        if alias:
            keys.add(normalize(alias))
        trigger = str(body.get("trigger") or "")
        if trigger.strip():
            keys.add(normalize(trigger))
        self.exact_keys = {key for key in keys if key}
        self.exact_keys.update(normalize(tag) for tag in (body.get("tags") or []) if tag)


def _template_document(
    row: dict[str, Any], aliases: dict[str, str], words: dict
) -> Document | None:
    template_id = row.get("id")
    if not template_id or row.get("kind") not in ("character", "outfit"):
        return None
    alias = aliases.get(template_id, "")
    tags = row.get("tags") or []
    categories = row.get("categories") or []
    trigger = row.get("trigger") or ""
    description = row.get("description") or ""
    text = " | ".join(
        filter(
            None,
            [
                row.get("name") or "",
                alias,
                trigger,
                " ".join(tags),
                " ".join(categories),
                description,
            ],
        )
    )
    if not normalize(text):
        return None
    kind = "character_template" if row["kind"] == "character" else "outfit_template"
    summary_parts = [alias] if alias else []
    summary_parts.append("触发词：" + trigger if trigger.strip() else "")
    summary_parts.append("标签：" + "、".join(tags[:12]) if tags else "")
    summary_parts.append("分类：" + "、".join(categories[:6]) if categories else "")
    if description.strip():
        summary_parts.append(description.strip()[:400])
    return Document(
        template_id,
        kind,
        template_id,
        (row.get("name") or template_id),
        "；".join(p for p in summary_parts if p)[:2000],
        row.get("source") or "user",
        str(row.get("source_revision") or ""),
        "/prompt-templates/" + template_id + "/image",
        text,
        row,
        alias,
    )


class LocalIndex:
    """An in-memory BM25 index over the live template records.

    Rebuilt from the business store on demand. A semantic backend is attached
    separately; this index always works offline.
    """

    def __init__(self, documents: Iterable[Document], aliases: dict[str, str]):
        self.documents = [d for d in documents if d is not None]
        self.aliases = aliases
        self.document_frequency: Counter = Counter()
        self.average_length = 1.0
        for document in self.documents:
            self.document_frequency.update(document.frequency.keys())
        if self.documents:
            self.average_length = sum(d.length for d in self.documents) / len(self.documents)
        self.fingerprint = hashlib.sha256(
            json.dumps([d.doc_id for d in self.documents], separators=(",", ":")).encode()
        ).hexdigest()[:16]

    def bm25(
        self, document: Document, terms: list[list[str]], k1: float = 1.5, b: float = 0.75
    ) -> float:
        total = len(self.documents) or 1
        score = 0.0
        for term_tokens in terms:
            idf = (
                math.log(
                    1
                    + (total - self.document_frequency[term_tokens[0]] + 0.5)
                    / (self.document_frequency[term_tokens[0]] + 0.5)
                )
                if term_tokens[0] in self.document_frequency
                else 0.0
            )
            for token in term_tokens:
                tf = document.frequency.get(token, 0)
                if not tf:
                    continue
                score += (
                    idf
                    * (tf * (k1 + 1))
                    / (tf + k1 * (1 - b + b * document.length / self.average_length))
                )
        return score

    def exact(self, term: str) -> list[Document]:
        """Exact name/trigger/tag/alias matches; >1 means an ambiguous query."""
        target = normalize(term)
        if not target:
            return []
        return [d for d in self.documents if target in d.exact_keys]

    def alias_matches(self, terms: set[str]) -> set[str]:
        """Template IDs whose Chinese alias is one of the query terms."""
        if not terms:
            return set()
        return {
            d.template_id
            for d in self.documents
            if d.template_id and normalize(self.aliases.get(d.template_id, "")) in terms
        }


def load_aliases(store) -> dict[str, str]:
    """Chinese aliases for character templates, from the fixed mapping version."""
    path = Path(store.root) / "translation" / "ffdkj-mapped" / "caster-names-mapped.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    aliases: dict[str, str] = {}
    for key in ("characters", "works"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("id") and item.get("translated_name"):
                aliases[item["id"]] = str(item["translated_name"]).strip()
    return aliases


TEMPLATE_REVISION_KEY = "agent_template_revision"


def bump_template_revision(store) -> int:
    """Mark the template collection as changed so cached indexes rebuild.

    Call this from every path that writes a template. Cheap, and it makes an
    equal-length edit visible even though row count and body length are unchanged.
    """
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", ("counter", TEMPLATE_REVISION_KEY)
        ).fetchone()
        value = (int(json.loads(row["body"])["value"]) if row else 0) + 1
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            ("counter", TEMPLATE_REVISION_KEY, json.dumps({"value": value})),
        )
    return value


class RetrievalResult:
    def __init__(
        self,
        hits: list[SearchHit],
        semantic_available: bool,
        semantic_reason: str = "",
        ambiguity: list[SearchHit] | None = None,
        negation: dict[str, Any] | None = None,
        query_plan: dict[str, Any] | None = None,
        strategy: str = "deterministic",
        warnings: list[dict[str, str]] | None = None,
    ):
        self.hits = hits
        self.semantic_available = semantic_available
        self.semantic_reason = semantic_reason
        self.ambiguity = ambiguity or []
        # Which negation terms the query asked for, and whether the exclusion
        # could actually be applied to the candidate text. Reported so the agent
        # can say "this constraint was requested" instead of implying it was
        # enforced when the term and the candidate are in different languages.
        self.negation = negation or {"terms": [], "enforced": True}
        self.query_plan = query_plan
        self.strategy = strategy
        self.warnings = warnings or []

    def payload(self) -> dict[str, Any]:
        state = (
            "unavailable"
            if not self.semantic_available and not self.hits
            else "candidates"
            if self.hits
            else "empty"
        )
        return {
            "schema_version": 1,
            "result_state": state,
            "strategy": self.strategy,
            "retrieval_role": "candidate_evidence_only",
            "decision_owner": "llm",
            "query_plan": self.query_plan,
            "score_semantics": "ranking_signal_only_not_probability",
            "abstention": {
                "supported": False,
                "reason": (
                    "当前没有经过校准的 no-match 阈值；空结果可以报告，"
                    "非空结果不能据相似度断言一定有答案"
                ),
            },
            "warnings": self.warnings,
            "semantic_available": self.semantic_available,
            "semantic_reason": self.semantic_reason,
            "negation": self.negation,
            "hits": [h.model_dump() for h in self.hits],
            "ambiguous": [h.model_dump() for h in self.ambiguity],
        }


# Keyed by store root -> (template signature, index). The signature is recomputed
# per query, so template edits and deletes are visible without a manual rebuild.
_INDEX_CACHE: dict[str, tuple[tuple, "LocalIndex"]] = {}
_TAG_CACHE: dict[str, tuple[float, list[tuple[str, str, str, str]]]] = {}
_EXACT_TAG_CACHE: dict[str, tuple[int, dict[str, list[str]]]] = {}


# Reciprocal rank fusion. Both retrieval branches over-fetch, the lists are
# merged by document id, and each document's fused score is the sum of
# 1/(k + rank) over the lists that returned it. That keeps the two orderings
# comparable without adding their raw scores, which are not on the same scale.
RRF_K = 60


def _fuse_scores(*rankings: list[str]) -> dict[str, float]:
    """Reciprocal-rank score per document, summed over the lists that returned it."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + position + 1)
    return scores


def _fuse(*rankings: list[str]) -> list[str]:
    """Merge rankings by reciprocal rank, best first."""
    scores = _fuse_scores(*rankings)
    return sorted(scores, key=lambda doc_id: (-scores[doc_id], doc_id))


class RetrievalService:
    """Template and tag search for the agent, backed by the live business store."""

    def __init__(self, store, semantic_backend=None, overfetch: int = 4, *, config=None):
        self.config = dict(load_config() if config is None else config)
        self.store = store
        self.semantic_backend = semantic_backend
        self.overfetch = overfetch

    # -- index lifecycle ---------------------------------------------------- #
    def _stamp(self) -> float:
        """A monotonic version for the template collection.

        Row count and total body length miss an equal-length edit (``maid`` ->
        ``coat``), so the template writers also bump a counter record. The three
        together make "a template edit is visible on the next query" true without
        re-reading and re-tokenising the corpus every time.
        """
        with self.store.connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(body)),0) AS total "
                "FROM records WHERE kind='prompt_template'"
            ).fetchone()
            revision = db.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", ("counter", TEMPLATE_REVISION_KEY)
            ).fetchone()
        return (
            row["n"],
            row["total"],
            int(json.loads(revision["body"])["value"]) if revision else 0,
        )

    def invalidate(self) -> None:
        """Drop the cached index and bump the revision so other processes see it."""
        bump_template_revision(self.store)
        _INDEX_CACHE.pop(str(self.store.root), None)

    def build(self, refresh: bool = False) -> LocalIndex:
        """Return the BM25 index, rebuilding only when the templates changed."""
        key = str(self.store.root)
        stamp = self._stamp()
        cached = _INDEX_CACHE.get(key)
        if cached and not refresh and cached[0] == stamp:
            return cached[1]
        index = self._build_index()
        _INDEX_CACHE[key] = (stamp, index)
        return index

    def _build_index(self) -> LocalIndex:
        from ..template_translation import dictionary

        aliases = load_aliases(self.store)
        words = dictionary(self.store)
        documents = []
        for row in self.store.list("prompt_template"):
            document = _template_document(row, aliases, words)
            if document is not None:
                documents.append(document)
        return LocalIndex(documents, aliases)

    def status(self) -> dict[str, Any]:
        index = self.build()
        return {
            "documents": len(index.documents),
            "fingerprint": index.fingerprint,
            "semantic_available": self.semantic_backend is not None,
            "semantic_reason": ""
            if self.semantic_backend is not None
            else "语义检索尚未建立索引，当前使用精确与 BM25 检索",
        }

    # -- search ------------------------------------------------------------- #
    def _rank(
        self, query: str, kind: str | None, limit: int, excluded: list[str]
    ) -> RetrievalResult:
        index = self.build()
        positive, excluded_terms = strip_negation(query)
        excluded_terms = list(dict.fromkeys(excluded_terms + [normalize(t) for t in excluded]))
        query_terms = {normalize(term) for term in positive if normalize(term)}
        alias_ids = index.alias_matches(query_terms)
        candidates = index.documents
        if kind:
            candidates = [d for d in candidates if d.kind == kind]
        by_id = {d.doc_id: d for d in index.documents}
        # Type and negation filtering happen *before* exact matching, so the
        # pinned hit and the ambiguity list can never contain a document the
        # caller asked to exclude. Doing it after the fact made the pin drop a
        # filtered document into the result set.
        candidates = [
            d
            for d in candidates
            if not any(term and term in d.norm_text for term in excluded_terms)
        ]
        allowed = {d.doc_id for d in candidates}
        exact_documents = [d for d in index.exact(query) if d.doc_id in allowed]
        exact_ids = {d.doc_id for d in exact_documents}
        scored: list[tuple[float, str, Document]] = []
        query_tokens = [tokenize(term) for term in positive if tokenize(term)]
        for document in candidates:
            score = 0.0
            match = "none"
            if document.doc_id in exact_ids:
                score += 100.0
                match = "exact"
            elif document.template_id in alias_ids:
                score += 60.0
                match = "alias"
            bm25 = index.bm25(document, query_tokens)
            score += bm25
            if bm25 > 0 and match == "none":
                match = "token"
            if score > 0:
                scored.append((score, match, document))
        scored.sort(key=lambda item: (-item[0], item[2].doc_id))
        # Both branches over-fetch and the two lists are fused *before* the final
        # limit is applied. Truncating each branch first is what let keyword
        # results crowd semantic ones out of the answer entirely.
        pool = max(limit, 1) * self.overfetch
        semantic_reason = (
            "" if self.semantic_backend is not None else "语义检索不可用，仅返回精确与关键词结果"
        )
        semantic_ranked: dict[str, float] = {}
        if self.semantic_backend is not None:
            try:
                for hit in self.semantic_backend.search(query, kind, pool):
                    # A vector hit contributes a ranking signal only: the fields
                    # returned to the caller come from the live business record,
                    # so a template deleted or edited since the index was built
                    # can never be used as an execution input.
                    document = by_id.get(hit.doc_id)
                    # ``allowed`` is the kind-filtered set, recomputed from the
                    # live records. A point indexed as a character template and
                    # since changed to an outfit in the business store is not a
                    # character template, so it drops out here instead of riding
                    # in on the vector ranking.
                    if document is None or document.doc_id not in allowed:
                        continue
                    if any(term and term in document.norm_text for term in excluded_terms):
                        continue
                    semantic_ranked[document.doc_id] = hit.score
            except Exception as error:
                # A failed index has to be visible, not an empty result set.
                semantic_reason = "语义检索失败：" + type(error).__name__ + "：" + str(error)[:200]

        fused_scores = _fuse_scores([d.doc_id for _, _, d in scored], list(semantic_ranked))
        fused = sorted(fused_scores, key=lambda doc_id: (-fused_scores[doc_id], doc_id))
        matches = {d.doc_id: match for _, match, d in scored}
        # A single exact hit outranks everything; several are reported as an
        # ambiguity for the user to resolve instead of being silently ordered.
        pinned = [d.doc_id for d in exact_documents] if len(exact_documents) == 1 else []
        order = list(dict.fromkeys(pinned + fused))[:limit]
        hits = []
        for doc_id in order:
            document = by_id[doc_id]
            if doc_id in semantic_ranked:
                # The fused score is what put this hit in this position; showing
                # the raw semantic score would make the ordering unexplainable.
                score = fused_scores[doc_id]
                match = (
                    matches.get(doc_id) if matches.get(doc_id) in ("exact", "alias") else "semantic"
                )
            else:
                score, match = next((s, m) for s, m, d in scored if d.doc_id == doc_id)
            hits.append(
                SearchHit(
                    doc_id=document.doc_id,
                    kind=document.kind,
                    template_id=document.template_id,
                    title=document.title,
                    summary=document.summary,
                    source=document.source,
                    source_revision=document.source_revision,
                    match=match,
                    score=round(float(score), 4),
                    preview_url=document.preview_url,
                )
            )
        exact_hits = exact_documents
        ambiguity = []
        if len(exact_hits) > 1:
            ambiguity = [
                SearchHit(
                    doc_id=d.doc_id,
                    kind=d.kind,
                    template_id=d.template_id,
                    title=d.title,
                    summary=d.summary,
                    source=d.source,
                    source_revision=d.source_revision,
                    match="exact",
                    score=100.0,
                    preview_url=d.preview_url,
                )
                for d in exact_hits[:limit]
            ]
        negation = {"terms": [t for t in excluded_terms if t], "enforced": True}
        if negation["terms"] and not all(
            any(t in d.norm_text for _, _, d in scored) or t in " ".join(semantic_ranked)
            for t in negation["terms"]
        ):
            # A requested exclusion that matched no candidate text cannot be
            # claimed as enforced; the caller has to say it was only requested.
            negation["enforced"] = False
        return RetrievalResult(
            hits, self.semantic_backend is not None, semantic_reason, ambiguity, negation
        )

    def search_wiki(self, query: str, limit: int = 8) -> RetrievalResult:
        """Search the wiki corpus through the vector index.

        The index holds one point per chunk plus a name point per entry, so the
        results are aggregated by ``source_id`` and a name-only hit is marked as
        such: it can support a name match but it is not evidence about the body.
        """
        query_plan = plan_wiki_query(query)
        if self.semantic_backend is None:
            return RetrievalResult(
                [],
                False,
                "语义检索不可用，无法查询 Wiki 资料",
                query_plan=query_plan,
                strategy="wiki-tool-evidence-v2",
            )
        if not hasattr(self.semantic_backend, "search_wiki"):
            return RetrievalResult(
                [],
                False,
                "当前语义后端不支持 Wiki 检索",
                query_plan=query_plan,
                strategy="wiki-tool-evidence-v2",
            )
        requested = max(1, limit)
        anchor = query_plan["executable_anchor"]
        if not anchor:
            return RetrievalResult(
                [],
                True,
                "查询只包含排除条件，没有可执行的正向 Wiki 查询",
                query_plan=query_plan,
                strategy="wiki-tool-evidence-v2",
                warnings=[{"code": "negative_only_query", "message": "请先提供要查找的正向概念"}],
            )
        try:
            hits, expansion_reasons = self._search_wiki_branch(anchor, requested)
            positive = query_plan["positive_concepts"]
            if query_plan["intent"] == "composition":
                branches = []
                for concept in positive:
                    if concept == anchor:
                        continue
                    branch, reasons = self._search_wiki_branch(concept, requested)
                    branches.append(branch)
                    expansion_reasons.extend(reasons)
                hits = self._round_robin_wiki_hits(hits, *branches, limit=requested)

        except Exception as error:
            return RetrievalResult(
                [],
                False,
                "语义检索失败：" + type(error).__name__ + "：" + str(error)[:200],
                query_plan=query_plan,
                strategy="wiki-tool-evidence-v2",
            )
        summary_of = getattr(self.semantic_backend, "body_summary", None)
        for hit in hits:
            if not hit.chunk_id or summary_of is None:
                continue
            # A name-only hit keeps its flag - the ranking signal came from the
            # name - but the body is still attached when it is available, so the
            # agent can answer instead of only naming an entry.
            try:
                excerpt = summary_of(hit.chunk_id)
            except RagUnavailable:
                # A body store that is missing or unreadable costs the excerpt,
                # not the hit: the answer can still cite the entry.
                excerpt = ""
            if excerpt:
                hit.summary = (hit.summary + "；" + excerpt)[:4000]
        resolver_reason = ""
        resolved = next((hit for hit in hits if hit.name_provenance), None)
        if resolved is not None:
            resolver_reason = "安全名称解析已置顶 %s（%s）" % (
                resolved.title,
                resolved.name_provenance,
            )
        composition_reason = (
            ("整句锚点与 %d 个正向概念按轮询合并" % len(query_plan["positive_concepts"]))
            if query_plan["intent"] == "composition"
            else ""
        )
        reason = "；".join(
            dict.fromkeys(
                part for part in (*expansion_reasons, composition_reason, resolver_reason) if part
            )
        )
        negation = {
            "terms": query_plan["negative_concepts"],
            "enforced": not query_plan["negative_concepts"],
        }
        warnings = []
        if query_plan["negative_concepts"]:
            warnings.append(
                {
                    "code": "negation_delegated_to_llm",
                    "message": "RAG 仅召回候选；排除条件由 LLM 根据候选证据判断",
                }
            )
        if any(hit.name_only and not hit.chunk_id for hit in hits):
            warnings.append(
                {
                    "code": "name_only_evidence",
                    "message": "部分候选只有名称证据，不可引用为正文事实",
                }
            )
        return RetrievalResult(
            hits[: max(1, limit)],
            True,
            reason,
            negation=negation,
            query_plan=query_plan,
            strategy="wiki-tool-evidence-v2",
            warnings=warnings,
        )

    def _search_wiki_branch(self, query: str, limit: int) -> tuple[list[SearchHit], list[str]]:
        """One whole or concept query, including collision-safe tag expansion."""
        expansion = self._exact_tag_expansion(query)
        reasons: list[str] = []
        if expansion and hasattr(self.semantic_backend, "search_wiki_fused"):
            hits = self.semantic_backend.search_wiki_fused([query, " ".join(expansion)], limit)
            reasons.append(
                "精确标签映射 %s 以第二条 Qwen 查询做 source-level RRF" % "、".join(expansion)
            )
        elif expansion:
            original = self.semantic_backend.search_wiki(query, limit)
            translated = self.semantic_backend.search_wiki(" ".join(expansion), limit)
            hits = self._fuse_wiki_hits(original, translated, limit)
            reasons.append("精确标签映射 %s 以兼容路径做 source-level RRF" % "、".join(expansion))
        else:
            hits = self.semantic_backend.search_wiki(query, limit)
        return hits, reasons

    @staticmethod
    def _round_robin_wiki_hits(*rankings: list[SearchHit], limit: int) -> list[SearchHit]:
        """Interleave whole-query and concept rankings at the canonical source seam."""
        result: list[SearchHit] = []
        seen: set[str] = set()
        width = max((len(ranking) for ranking in rankings), default=0)
        for position in range(width):
            for ranking in rankings:
                if position >= len(ranking):
                    continue
                hit = ranking[position]
                identity = str(hit.source_id or hit.doc_id)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(hit)
                if len(result) >= max(1, limit):
                    return result
        return result

    def _exact_tag_expansion(self, query: str, max_tags: int = 2) -> list[str]:
        """English tags for one exact Chinese query, or no expansion.

        This intentionally does not segment or look for contained phrases. The
        labelled evaluation found that broad dictionary matches increase deep
        recall but damage the top ranks; a whole-query match improved both dev
        and test. A trailing ``的`` is accepted because it is a grammatical
        particle, not a second retrieval concept.
        """
        if not config_flag(self.config, "AIGC_RAG_EXACT_TAG_EXPANSION", True):
            return []
        normalized = re.sub(r"[\s，。！？、,.!?]+", "", query or "").strip()
        if normalized.endswith("的"):
            normalized = normalized[:-1]
        if not normalized:
            return []
        return self._exact_tag_index().get(normalized, [])[:max_tags]

    def _exact_tag_index(self) -> dict[str, list[str]]:
        """Chinese label -> popular English tags, cached by dictionary mtime."""
        path = self.store.root / "translation" / "ffdkj" / "tag.sqlite"
        if not path.is_file():
            return {}
        stamp = path.stat().st_mtime_ns
        key = str(path.resolve())
        cached = _EXACT_TAG_CACHE.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        reverse: dict[str, list[str]] = {}
        try:
            connection = sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True)
            try:
                rows = connection.execute(
                    "SELECT cn_name, name FROM tags "
                    "WHERE cn_name <> '' AND name <> '' "
                    "ORDER BY cn_name, post_count DESC, name"
                )
                for chinese, name in rows:
                    names = reverse.setdefault(str(chinese).strip(), [])
                    name = str(name).strip()
                    if name and name not in names and len(names) < 2:
                        names.append(name)
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            # Tag translation is an optional recall aid. A damaged vocabulary
            # must not take down the original Qwen query.
            return {}
        _EXACT_TAG_CACHE[key] = (stamp, reverse)
        return reverse

    @staticmethod
    def _fuse_wiki_hits(original: list, translated: list, limit: int) -> list:
        """Source-level RRF for adapters without native pre-truncation fusion."""
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        hits_by_id = {}
        for ranking in (original, translated):
            for position, hit in enumerate(ranking):
                source_id = str(hit.source_id or hit.doc_id)
                scores[source_id] = scores.get(source_id, 0.0) + 1.0 / (RRF_K + position + 1)
                best_rank[source_id] = min(best_rank.get(source_id, position), position)
                hits_by_id.setdefault(source_id, hit)
        order = sorted(
            scores, key=lambda source_id: (-scores[source_id], best_rank[source_id], source_id)
        )
        fused = []
        for source_id in order[: max(1, limit)]:
            hit = hits_by_id[source_id]
            hit.score = scores[source_id]
            fused.append(hit)
        return fused

    def search_templates(
        self, query: str, kind: str | None = None, limit: int = 8
    ) -> RetrievalResult:
        if kind not in (None, "character", "outfit"):
            raise ValueError("kind must be character, outfit or empty")
        wanted = (
            "character_template"
            if kind == "character"
            else "outfit_template"
            if kind == "outfit"
            else None
        )
        return self._rank(query, wanted, max(1, min(limit, 20)), [])

    def search_tag_knowledge(self, query: str, limit: int = 8) -> RetrievalResult:
        """Tag vocabulary search over the local translation dictionary.

        Chinese users naturally write several short concepts separated only by
        spaces (``猫耳 异色瞳``).  Those are independent vocabulary
        lookups, while an English canonical tag such as ``maid headdress`` must
        remain one phrase.  The query plan makes that distinction explicit and
        also returns vocabulary evidence for exclusions; the LLM, not this
        lookup, owns the final inclusion/exclusion decision.
        """
        plan = plan_wiki_query(query)

        def expand(concepts: list[str]) -> list[str]:
            expanded: list[str] = []
            for concept in concepts:
                normal = normalize(concept)
                parts = normal.split()
                if len(parts) > 1 and all(_CJK_ANY.search(part) for part in parts):
                    expanded.extend(parts)
                elif normal:
                    expanded.append(normal)
            return list(dict.fromkeys(expanded))

        positive_terms = expand(plan["positive_concepts"])
        negative_terms = expand(plan["negative_concepts"])
        plan["positive_concepts"] = positive_terms
        plan["negative_concepts"] = negative_terms
        # Vocabulary lookup deliberately resolves excluded terms too, but each
        # is an independent branch rather than a negative phrase embedded in a
        # positive dense query.
        plan["query_variants"] = list(dict.fromkeys([*positive_terms, *negative_terms]))
        plan["executed_queries"] = list(plan["query_variants"])
        # Rank each concept independently, then round-robin the branches. Without
        # this quota a broad concept such as “猫耳” can fill the whole limit and
        # hide exact evidence for the other requested constraints.
        terms = [*positive_terms, *negative_terms]
        branches: list[list[tuple[float, bool, str, str]]] = []
        rows = self._tag_index()
        for term in terms:
            branch: list[tuple[float, bool, str, str]] = []
            for name, name_key, chinese, chinese_key in rows:
                exact = name_key == term or bool(chinese_key and chinese_key == term)
                score = 0.0
                if name_key == term:
                    score = max(score, 100)
                elif term in name_key:
                    score = max(score, 35)
                if chinese_key == term:
                    score = max(score, 90)
                elif chinese_key and term in chinese_key:
                    score = max(score, 30)
                if score:
                    branch.append((score, exact, name, chinese))
            branch.sort(key=lambda item: (-item[0], item[2]))
            branches.append(branch)

        wanted = max(1, min(limit, 20))
        results: list[tuple[float, bool, str, str]] = []
        seen: set[str] = set()
        depth = 0
        while len(results) < wanted and any(depth < len(branch) for branch in branches):
            for branch in branches:
                if depth >= len(branch):
                    continue
                item = branch[depth]
                if item[2] not in seen:
                    results.append(item)
                    seen.add(item[2])
                    if len(results) >= wanted:
                        break
            depth += 1
        hits = [
            SearchHit(
                doc_id="tag:" + name,
                kind="tag",
                title=name,
                summary=("中文：" + chinese) if chinese else "暂无中文映射",
                source="ffdkj-tag-vocabulary",
                source_revision="local",
                match="exact" if exact else "token",
                score=round(score, 4),
            )
            for score, exact, name, chinese in results
        ]
        return RetrievalResult(
            hits,
            False,
            "标签查询使用本地词表，不做语义扩展",
            negation={"terms": plan["negative_concepts"], "enforced": False},
            query_plan=plan,
            strategy="tag_vocabulary_compound",
        )

    def _tag_index(self) -> list[tuple[str, str, str, str]]:
        """Normalised (name, name_key, chinese, chinese_key) rows, cached by mtime.

        Normalising 328k Chinese labels per query would dominate the cost, so the
        keys are computed once and reused.
        """
        from ..template_translation import dictionary

        words = dictionary(self.store)
        path = self.store.root / "translation" / "ffdkj" / "tag.sqlite"
        stamp = path.stat().st_mtime_ns if path.is_file() else 0.0
        key = str(self.store.root) + ":tags"
        cached = _TAG_CACHE.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        rows = [
            (name, normalize(name), chinese, normalize(chinese) if chinese else "")
            for name, (_, chinese) in words.items()
        ]
        _TAG_CACHE[key] = (stamp, rows)
        return rows
