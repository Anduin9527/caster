"""The shape of a point in the Qdrant index: ID, payload, cache key.

This lives in the package because two very different processes write the same
collection. ``scripts/rag_build_index.py`` fills it offline from a snapshot;
``aigc.agent.template_sync`` upserts single templates while the service runs. If
each built its own point IDs or payloads, an incrementally written point would
differ from a built one - a different ID would leave both versions in the
collection, and a different payload would make the next verification report
drift on a point that is actually correct.

Nothing here imports torch, qdrant or the business store: the build script and
the online path must be able to share it without sharing their dependencies.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

# Fixed namespace, so a point ID is stable across processes and versions of
# this file. Changing it would orphan every existing point.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "caster-rag")


def template_text(record: dict[str, Any]) -> str:
    """The same text the deterministic retrieval indexes, so both paths agree."""
    return " | ".join(
        filter(
            None,
            [
                record.get("name") or "",
                record.get("alias") or "",
                record.get("trigger") or "",
                " ".join(record.get("tags") or []),
                " ".join(record.get("categories") or []),
                record.get("description") or "",
            ],
        )
    )


def template_document(record: dict[str, Any], version: str) -> dict[str, Any]:
    """One business template record as an indexable document.

    ``kind`` is the document kind the collection stores, not the business kind
    on the record: retrieval filters on it, so the two vocabularies are mapped
    here and nowhere else.
    """
    text = template_text(record)
    template_id = str(record.get("id") or "")
    return {
        "kind": ("character_template" if record.get("kind") == "character" else "outfit_template"),
        "doc_id": template_id,
        "chunk_id": "",
        "title": record.get("name") or template_id,
        "text": text,
        "text_sha256": sha256_text(text),
        "source_revision": str(record.get("source_revision") or ""),
        "source_url": "/prompt-templates/%s/image" % template_id,
        "chunk_index": 0,
        "chunk_count": 1,
        "template_id": template_id,
        "version": version,
    }


def snapshot_version(records: list[dict[str, Any]]) -> str:
    """Digest of what is actually encoded, not of the file it came from.

    The business SQLite changes whenever a job or an asset changes, so hashing
    that file would invalidate every template vector for an unrelated reason. In
    WAL mode the main-file hash also does not cover rows that only exist in the
    -wal file, so it could not even reproduce the exported content.
    """
    material = "\n".join(template_text(record) for record in records)
    return "templates-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def point_id(document: dict[str, Any]) -> str:
    return str(
        uuid.uuid5(
            NAMESPACE, ":".join([document["kind"], document["doc_id"], document["chunk_id"]])
        )
    )


def cache_key(document: dict[str, Any], encoder_fingerprint: str) -> str:
    """Text, corpus version and encoder identity; stable across interrupted builds."""
    material = json_dumps(
        {
            "text_sha256": document["text_sha256"],
            "corpus_version": document["version"],
            "encoder": encoder_fingerprint,
        }
    )
    return hashlib.sha256(material.encode()).hexdigest()


def payload_of(document: dict[str, Any]) -> dict[str, Any]:
    """The stored payload: the minimum needed to filter and to trace a hit.

    Long text is deliberately absent - it stays in the corpus file and the body
    store, and a hit is traced back through ``doc_id``/``source_id`` instead of
    being trusted from the vector.
    """
    payload = {
        "kind": document["kind"],
        "doc_id": document["doc_id"],
        "title": document["title"],
        "text_sha256": document["text_sha256"],
        "source_revision": document["source_revision"],
        "source_url": document["source_url"],
    }
    if document["kind"] in ("chunk", "name"):
        payload["source_id"] = document["doc_id"]
    if document["kind"] == "chunk":
        payload.update(
            {
                "chunk_id": document["chunk_id"],
                "chunk_index": document["chunk_index"],
                "chunk_count": document["chunk_count"],
            }
        )
    if document.get("template_id"):
        payload["template_id"] = document["template_id"]
    return payload


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True)
