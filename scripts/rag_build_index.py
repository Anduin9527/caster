"""Build an unpublished Qdrant collection from the prepared corpus.

A build never publishes anything. It fills one physical collection and records a
fingerprint of everything that determines a vector - model commit, dimension,
truncation length, pooling code version, query instruction and corpus version -
in ``collections.json``. Writing into a collection whose recorded fingerprint
differs is refused, because that is how a same-dimension model swap would leave a
collection holding vectors from two models. Switching the stable alias is a
separate step (``rag_publish_alias.py``) that only happens after an independent
verification, so an interrupted build can never be served.

Resumable and idempotent by construction:

* point IDs are deterministic UUIDv5 over ``(kind, doc id, chunk id)``, so a
  re-delivered batch replaces its own points instead of adding new ones;
* embedding vectors live in a content-addressed cache keyed by text hash plus
  the encoder fingerprint, so a rerun embeds only what changed or previously
  failed.

The business SQLite is never opened here: templates come from the read-only
snapshot produced by ``rag_snapshot_templates.py``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_encoder import add_package_root  # noqa: E402

add_package_root()
from rag_encoder import DEFAULT_INSTRUCTION, Encoder

# The point shape is shared with the online incremental writer, so a template
# upserted by the running service is byte-identical to a built one.
from aigc.rag_index import (  # noqa: E402
    cache_key,
    payload_of,
    point_id,
    sha256_text,
    snapshot_version,
    template_document,
)

REGISTRY_NAME = "collections.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Cache:
    """Content-addressed vector cache. Survives interruption and reruns."""

    def __init__(self, path: Path, *, readonly: bool = False):
        if readonly:
            self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors("
            "cache_key TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL)"
        )
        self.db.commit()

    def lookup(self, keys: list[str]) -> dict[str, np.ndarray]:
        found = {}
        for start in range(0, len(keys), 500):
            chunk = keys[start : start + 500]
            marks = ",".join("?" * len(chunk))
            rows = self.db.execute(
                "SELECT cache_key, dim, vector FROM vectors WHERE cache_key IN (%s)" % marks, chunk
            ).fetchall()
            for key, dim, blob in rows:
                if dim <= 0 or len(blob) != dim * 4:
                    continue
                vector = np.frombuffer(blob, dtype="<f4")
                if np.all(np.isfinite(vector)) and np.linalg.norm(vector) > 0:
                    found[key] = vector
        return found

    def store(self, keys: list[str], vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype="<f4")
        if (
            vectors.ndim != 2
            or vectors.shape[0] != len(keys)
            or vectors.shape[1] == 0
            or not np.all(np.isfinite(vectors))
            or np.any(np.linalg.norm(vectors, axis=1) == 0)
        ):
            raise ValueError(
                "Cache vectors must be finite, nonzero rows matching the supplied keys"
            )
        rows = [
            (
                key,
                int(vectors.shape[1]),
                np.ascontiguousarray(vectors[index], dtype="<f4").tobytes(),
            )
            for index, key in enumerate(keys)
        ]
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO vectors VALUES(?,?,?)", rows)

    def close(self) -> None:
        self.db.close()


def load_wiki(chunks: Path, names: Path, wiki_manifest: Path) -> tuple[list[dict], dict]:
    manifest = json.loads(wiki_manifest.read_text())
    version = (
        "wiki-"
        + hashlib.sha256(
            json.dumps(
                {"cleaning": manifest["cleaning_version"], "chunking": manifest["chunking"]},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
    )
    documents: list[dict[str, Any]] = []
    with gzip.open(chunks, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            documents.append(
                {
                    "kind": "chunk",
                    "doc_id": str(row["source_id"]),
                    "chunk_id": row["chunk_id"],
                    "title": row["title"],
                    "text": row["text"],
                    "text_sha256": row["text_sha256"],
                    "source_revision": str(row.get("updated_at") or ""),
                    "source_url": row.get("source_url") or "",
                    "chunk_index": row["chunk_index"],
                    "chunk_count": row["chunk_count"],
                    "version": version,
                }
            )
    with gzip.open(names, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            text = row["title"] + (("\n" + ", ".join(row["aliases"])) if row["aliases"] else "")
            documents.append(
                {
                    "kind": "name",
                    "doc_id": str(row["source_id"]),
                    "chunk_id": "",
                    "title": row["title"],
                    "text": text,
                    "text_sha256": sha256_text(text),
                    "source_revision": "",
                    "source_url": row.get("source_url") or "",
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "version": version,
                }
            )
    return documents, manifest


def load_templates(snapshot_path: Path) -> tuple[list[dict], str]:
    payload = json.loads(snapshot_path.read_text())
    version = snapshot_version(payload["templates"])
    documents = [template_document(record, version) for record in payload["templates"]]
    return documents, version


class Registry:
    """Which encoder fingerprint each physical collection was built with."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        if path.is_file():
            try:
                self.data = json.loads(path.read_text()).get("collections", {})
            except ValueError:
                self.data = {}

    def fingerprint_of(self, name: str) -> str | None:
        return self.data.get(name, {}).get("encoder_fingerprint")

    def record(
        self, name: str, fingerprint: str, corpus_versions: dict[str, str], documents: int
    ) -> None:
        self.data[name] = {
            "encoder_fingerprint": fingerprint,
            "corpus_versions": corpus_versions,
            "documents": documents,
            "recorded_at": time.time(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"collections": self.data}, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )


def ensure_unpublished(client, names: list[str]) -> None:
    if not names or len(names) != len(set(names)):
        raise ValueError("Build needs distinct nonempty target collections")
    published = {alias.collection_name for alias in client.get_aliases().aliases}
    conflicts = published.intersection(names)
    if conflicts:
        raise ValueError(
            "Refusing to rebuild published collections: " + ", ".join(sorted(conflicts))
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--dim", type=int, default=1024)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--wiki-collection", default="wiki_v1")
    parser.add_argument("--template-collection", default="templates_v1")
    parser.add_argument("--embed-batch", type=int, default=64)
    parser.add_argument("--upsert-batch", type=int, default=512)
    parser.add_argument(
        "--window", type=int, default=4096, help="documents per lookup/embed/upsert cycle"
    )
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--limit", type=int, default=0, help="smoke-test: index only N docs")
    parser.add_argument("--skip-templates", action="store_true")
    parser.add_argument(
        "--skip-wiki",
        action="store_true",
        help="build only the template collection, without reading or changing wiki",
    )
    parser.add_argument("--skip-names", action="store_true")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--task", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--package-root",
        type=Path,
        default=None,
        help="deployment root that holds the aigc package",
    )
    args = parser.parse_args()
    if args.package_root is not None:
        add_package_root(args.package_root)

    wiki_dir = args.workspace / "output" / "wiki-v1"
    # Loading the wiki corpus means reading 461k documents out of the gzip
    # files, so a template-only run skips it instead of paying for what it will
    # not write.
    wiki_docs, wiki_manifest = ([], {})
    if not args.skip_wiki:
        wiki_docs, wiki_manifest = load_wiki(
            wiki_dir / "wiki-chunks.jsonl.gz",
            wiki_dir / "wiki-names.jsonl.gz",
            wiki_dir / "manifest.json",
        )
    template_docs, template_version = ([], "")
    if not args.skip_templates:
        template_docs, template_version = load_templates(
            args.workspace / "input" / "templates-v1.json"
        )
    if args.skip_names:
        wiki_docs = [d for d in wiki_docs if d["kind"] != "name"]
    wiki_docs.sort(key=lambda d: (d["kind"], d["doc_id"], d["chunk_id"]))
    template_docs.sort(key=lambda d: d["doc_id"])
    if args.limit:
        wiki_docs = wiki_docs[: args.limit]
        template_docs = template_docs[: args.limit]

    with closing(QdrantClient(url=args.qdrant_url, prefer_grpc=False, timeout=300)) as client:
        registry = Registry(args.workspace / "output" / "index-v1" / REGISTRY_NAME)

        corpus_versions = {
            "wiki": wiki_docs[0]["version"] if wiki_docs else "",
            "templates": template_version,
        }
        targets = [(args.template_collection, template_docs)]
        if not args.skip_wiki:
            targets.insert(0, (args.wiki_collection, wiki_docs))
        ensure_unpublished(client, [name for name, documents in targets if documents])
        encoder = Encoder(
            args.model_path,
            args.dim,
            args.max_length,
            args.device,
            batch_size=args.embed_batch,
            instruction=args.task,
            commit=args.commit,
        )
        for name, documents in targets:
            if not documents:
                continue
            recorded = registry.fingerprint_of(name)
            exists = any(c.name == name for c in client.get_collections().collections)
            if exists and recorded is None:
                raise SystemExit(
                    "collection %s exists but has no recorded encoder fingerprint; "
                    "refusing to write into a collection of unknown provenance. "
                    "Build a new collection instead." % name
                )
            if recorded and recorded != encoder.fingerprint:
                raise SystemExit(
                    "collection %s was built with encoder fingerprint %s, this run "
                    "is %s; a model, dimension or truncation change needs a new "
                    "collection, never an overwrite." % (name, recorded, encoder.fingerprint)
                )
            if not exists:
                client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=args.dim, distance=models.Distance.COSINE
                    ),
                    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                )
                registry.record(name, encoder.fingerprint, corpus_versions, 0)

        # The cache is content addressed (text hash + corpus version + encoder
        # fingerprint), so it is deliberately *not* per index version: a rebuild of
        # another version reuses every vector that is still valid. It lives beside
        # the versioned manifests, not inside one of them.
        with closing(Cache(args.out.parent.parent / "embed-cache.sqlite3")) as cache:
            started = time.perf_counter()
            summary = {}
            for collection, documents in targets:
                if not documents:
                    continue
                embedded = 0
                for window_start in range(0, len(documents), args.window):
                    window = documents[window_start : window_start + args.window]
                    keys = [cache_key(d, encoder.fingerprint) for d in window]
                    cached = cache.lookup(keys)
                    missing = [(d, k) for d, k in zip(window, keys) if k not in cached]
                    for start in range(0, len(missing), args.embed_batch):
                        batch = missing[start : start + args.embed_batch]
                        matrix = encoder.encode_documents([d["text"] for d, _ in batch])
                        cache.store([k for _, k in batch], matrix)
                        cached.update({k: matrix[i] for i, (_, k) in enumerate(batch)})
                        embedded += len(batch)
                    for start in range(0, len(window), args.upsert_batch):
                        batch = window[start : start + args.upsert_batch]
                        points = [
                            models.PointStruct(
                                id=point_id(d), vector=cached[k].tolist(), payload=payload_of(d)
                            )
                            for d, k in zip(batch, keys[start : start + args.upsert_batch])
                        ]
                        client.upsert(collection_name=collection, points=points, wait=True)
                summary[collection] = {
                    "documents": len(documents),
                    "embedded_now": embedded,
                    "reused_from_cache": len(documents) - embedded,
                    "encoder_fingerprint": encoder.fingerprint,
                    "points": client.count(collection_name=collection, exact=True).count,
                }
                registry.record(collection, encoder.fingerprint, corpus_versions, len(documents))
            # No alias is created here. Publishing is a separate, verified step.

            manifest = {
                "schema_version": 2,
                "created_at": time.time(),
                "seconds": round(time.perf_counter() - started, 2),
                "model": {
                    "key": args.model_key,
                    "path": str(args.model_path),
                    "commit": args.commit,
                    "dim": args.dim,
                    "max_length": args.max_length,
                    "fingerprint": encoder.fingerprint,
                    "task": args.task,
                    "embed_batch": args.embed_batch,
                },
                # A skipped corpus records no input hash, so the manifest never claims
                # to have verified a file it did not read.
                "inputs": {
                    "wiki_manifest_sha256": (
                        None if args.skip_wiki else sha256_file(wiki_dir / "manifest.json")
                    ),
                    "wiki_chunks_sha256": (
                        None if args.skip_wiki else sha256_file(wiki_dir / "wiki-chunks.jsonl.gz")
                    ),
                    "wiki_names_sha256": (
                        None if args.skip_wiki else sha256_file(wiki_dir / "wiki-names.jsonl.gz")
                    ),
                    "templates_sha256": (
                        sha256_file(args.workspace / "input" / "templates-v1.json")
                        if not args.skip_templates
                        else None
                    ),
                },
                "corpus_versions": corpus_versions,
                "collection_names": {
                    "wiki": args.wiki_collection,
                    "template": args.template_collection,
                },
                "collections": summary,
                "aliases": {
                    "published": False,
                    "note": "build does not publish; run rag_publish_alias.py after verification",
                },
                "qdrant": {
                    "url": args.qdrant_url,
                    "vector": "cosine",
                    "hnsw": {"m": 16, "ef_construct": 100},
                    "vectors_in_ram": True,
                },
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            print(
                json.dumps(
                    {
                        "seconds": manifest["seconds"],
                        "collections": summary,
                        "fingerprint": encoder.fingerprint,
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
