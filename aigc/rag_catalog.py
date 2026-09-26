"""Local, traceable lookups that complement the Qdrant wiki vectors.

The vector collection deliberately stores no long body text and cannot safely
decide whether a human-readable name is authoritative.  This module keeps both
jobs behind one small interface backed by the versioned SQLite file that ships
with an index build:

* body lookup by chunk or source id;
* whole-query resolution against canonical titles, reviewed translations and
  recall-only Wiki ``other_names`` with provenance preserved.

The exact resolver never treats a colliding name as authoritative.  A unique
canonical title may be pinned; when no canonical title matches, a unique
translated name may be pinned.  Wiki ``other_names`` remain candidates only.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CatalogUnavailable(RuntimeError):
    """The versioned local wiki catalog cannot be read."""


def normalize_name(text: str) -> str:
    """Loose human-name key used for translations and recall aliases."""
    value = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\W_]+", "", value)


def normalize_canonical(text: str) -> str:
    """Danbooru canonical key: case-folded with whitespace as underscores."""
    value = unicodedata.normalize("NFKC", text or "").casefold().strip()
    return re.sub(r"\s+", "_", value)


@dataclass(frozen=True)
class NameMatch:
    source_id: str
    title: str
    matched_text: str
    provenance: str
    category: str = ""
    post_count: int = 0


@dataclass(frozen=True)
class NameResolution:
    canonical: tuple[NameMatch, ...] = ()
    translated_name: tuple[NameMatch, ...] = ()
    wiki_other_name: tuple[NameMatch, ...] = ()
    safe_pin: NameMatch | None = None
    pin_reason: str = ""

    @property
    def candidates(self) -> tuple[NameMatch, ...]:
        """All candidates, de-duplicated by source with strongest provenance."""
        order = {"canonical": 0, "translated_name": 1, "wiki_other_name": 2}
        by_source: dict[str, NameMatch] = {}
        for match in (*self.canonical, *self.translated_name, *self.wiki_other_name):
            current = by_source.get(match.source_id)
            if current is None or order[match.provenance] < order[current.provenance]:
                by_source[match.source_id] = match
        return tuple(
            sorted(
                by_source.values(),
                key=lambda item: (order[item.provenance], -item.post_count, int(item.source_id)),
            )
        )


class WikiCatalog:
    """Read the body and name tables belonging to one published index build."""

    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()

    def _connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            if not self.path.is_file():
                raise CatalogUnavailable("Wiki 本地目录不存在：" + str(self.path))
            connection = sqlite3.connect("file:%s?mode=ro" % self.path, uri=True)
            connection.row_factory = sqlite3.Row
            self._local.connection = connection
        return connection

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        row = (
            self._connection()
            .execute(
                "SELECT chunk_id, source_id, chunk_index, chunk_count, title, text "
                "FROM bodies WHERE chunk_id=?",
                (chunk_id,),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def first_chunk(self, source_id: str) -> dict[str, Any] | None:
        row = (
            self._connection()
            .execute(
                "SELECT chunk_id, source_id, chunk_index, chunk_count, title, text "
                "FROM bodies WHERE source_id=? ORDER BY chunk_index LIMIT 1",
                (int(source_id),),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def summary(self, chunk_id: str, limit: int = 400) -> str:
        record = self.get(chunk_id)
        if not record:
            return ""
        text = (record.get("text") or "").strip()
        title = (record.get("title") or "").strip()
        body = text[len(title) :].strip() if title and text.startswith(title) else text
        return body[:limit]

    def resolve_name(self, query: str) -> NameResolution:
        """Resolve one whole query; missing name tables degrade to no exact hit."""
        try:
            canonical = self._matches("canonical", normalize_canonical(query), "canonical")
            human_key = normalize_name(query)
            translated = self._matches("human", human_key, "translated_name")
            other_names = self._matches("human", human_key, "wiki_other_name")
        except sqlite3.OperationalError as error:
            # Older body stores have no name table.  Deploying new code before
            # rebuilding the versioned catalog must preserve the dense path.
            if "no such table" in str(error).lower():
                return NameResolution()
            raise CatalogUnavailable("Wiki 名称目录不可读：" + str(error)) from error
        except sqlite3.Error as error:
            raise CatalogUnavailable("Wiki 名称目录不可读：" + str(error)) from error
        safe_pin = None
        reason = ""
        if len(canonical) == 1:
            safe_pin, reason = canonical[0], "unique_canonical"
        elif not canonical and len(translated) == 1:
            safe_pin, reason = translated[0], "unique_translation"
        return NameResolution(canonical, translated, other_names, safe_pin, reason)

    def _matches(self, key_kind: str, lookup_key: str, provenance: str) -> tuple[NameMatch, ...]:
        if not lookup_key:
            return ()
        rows = (
            self._connection()
            .execute(
                "SELECT source_id, title, matched_text, provenance, category, post_count "
                "FROM names WHERE key_kind=? AND lookup_key=? AND provenance=? "
                "ORDER BY post_count DESC, source_id",
                (key_kind, lookup_key, provenance),
            )
            .fetchall()
        )
        return tuple(
            NameMatch(
                str(row["source_id"]),
                str(row["title"]),
                str(row["matched_text"]),
                str(row["provenance"]),
                str(row["category"] or ""),
                int(row["post_count"] or 0),
            )
            for row in rows
        )
