"""Verify a built collection without trusting the build script's own report.

Counts are recomputed from the corpus files, not read from the manifest, then
compared against both the manifest and the live service. Sampled points are
recomputed from the corpus (same deterministic point IDs), fetched back from
Qdrant and compared field by field, and their **vectors** are compared against
the embedding cache, so a point whose payload drifted *or* whose vector came from
somewhere else is caught. Every input hash, including the template snapshot, is
re-checked. ``ok: false`` exits non-zero, which is what makes this usable as a
publish gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_build_index import (  # noqa: E402
    Cache,
    cache_key,
    load_templates,
    load_wiki,
    payload_of,
    point_id,
    sha256_file,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_encoder import add_package_root  # noqa: E402

add_package_root()


def verify(
    workspace: Path, manifest_path: Path, url: str, samples: int, cache_path: Path | None = None
) -> dict:
    if samples < 2:
        # Not a CLI nicety: the "every sampled vector was compared against the
        # cache" gate at the end is satisfied by an empty sample set, so 0 or 1
        # would let a refused build report ok.
        raise ValueError("samples must be at least 2, got %r" % samples)
    manifest = json.loads(manifest_path.read_text())
    with closing(QdrantClient(url=url, prefer_grpc=False, timeout=120)) as client:
        return _verify(workspace, manifest, client, samples, cache_path)


def _verify(workspace: Path, manifest: dict, client, samples: int, cache_path: Path | None) -> dict:
    wiki_dir = workspace / "output" / "wiki-v1"
    names = manifest.get("collection_names") or {"wiki": "wiki_v1", "template": "templates_v1"}
    declared = manifest.get("collections", {})
    if not declared or set(declared) - set(names.values()):
        raise ValueError("Manifest must name the collections it actually built")
    collections = {}
    checks = []
    if names.get("wiki") in declared:
        wiki_docs, _ = load_wiki(
            wiki_dir / "wiki-chunks.jsonl.gz",
            wiki_dir / "wiki-names.jsonl.gz",
            wiki_dir / "manifest.json",
        )
        collections[names["wiki"]] = wiki_docs
        checks.extend(
            (
                (wiki_dir / "manifest.json", "wiki_manifest_sha256"),
                (wiki_dir / "wiki-chunks.jsonl.gz", "wiki_chunks_sha256"),
                (wiki_dir / "wiki-names.jsonl.gz", "wiki_names_sha256"),
            )
        )
    if names.get("template") in declared:
        template_path = workspace / "input" / "templates-v1.json"
        template_docs, _ = load_templates(template_path)
        collections[names["template"]] = template_docs
        checks.append((template_path, "templates_sha256"))
    problems: list[str] = []

    service_counts = {}
    available = {item.name for item in client.get_collections().collections}
    for collection, docs in collections.items():
        if collection not in available:
            problems.append("%s: collection does not exist" % collection)
            continue
        info = client.get_collection(collection)
        got = client.count(collection_name=collection, exact=True).count
        service_counts[collection] = got
        recorded = manifest["collections"].get(collection, {}).get("documents")
        if got != len(docs):
            problems.append(
                "%s: service has %s points, corpus has %s" % (collection, got, len(docs))
            )
        if recorded is not None and recorded != len(docs):
            problems.append(
                "%s: manifest says %s documents, corpus has %s" % (collection, recorded, len(docs))
            )
        expected_dim = manifest["model"]["dim"]
        if info.config.params.vectors.size != expected_dim:
            problems.append(
                "%s: vector size %s, manifest says %s"
                % (collection, info.config.params.vectors.size, expected_dim)
            )

    # The alias is reported, not enforced: a build must be verifiable while the
    # alias still points at the previous version, because switching it is the
    # separate publish step this verification gates.
    aliases = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}

    # Deterministic sample: every k-th document of each collection.
    picked: list[tuple[str, dict]] = []
    for collection, docs in collections.items():
        if not docs or collection not in available:
            continue
        step = max(1, len(docs) // max(1, samples // len(collections)))
        picked.extend((collection, doc) for doc in docs[::step][: samples // len(collections)])

    if not picked:
        problems.append("No corpus points were available for verification")
    mismatches, vector_checks = [], []
    for start in range(0, len(picked), 64):
        batch = picked[start : start + 64]
        by_collection: dict[str, list[dict]] = {}
        for collection, document in batch:
            by_collection.setdefault(collection, []).append(document)
        for collection, docs in by_collection.items():
            records = client.retrieve(
                collection_name=collection,
                ids=[point_id(d) for d in docs],
                with_payload=True,
                with_vectors=True,
            )
            by_id = {str(r.id): r for r in records}
            for document in docs:
                record = by_id.get(point_id(document))
                if record is None:
                    mismatches.append({"point": point_id(document), "problem": "missing"})
                    continue
                if record.payload != payload_of(document):
                    mismatches.append(
                        {
                            "point": point_id(document),
                            "problem": "payload drift",
                            "got": record.payload,
                            "want": payload_of(document),
                        }
                    )
                    continue
                vector = np.asarray(record.vector, dtype="<f4")
                if vector.shape != (manifest["model"]["dim"],):
                    mismatches.append(
                        {
                            "point": point_id(document),
                            "problem": "vector shape",
                            "got": list(vector.shape),
                        }
                    )
                    continue
                if not np.all(np.isfinite(vector)):
                    mismatches.append({"point": point_id(document), "problem": "non-finite vector"})
                    continue
                norm = float(np.linalg.norm(vector))
                if not 0.99 <= norm <= 1.01:
                    mismatches.append(
                        {
                            "point": point_id(document),
                            "problem": "not normalised",
                            "norm": round(norm, 6),
                        }
                    )
                    continue
                vector_checks.append(point_id(document))
    if mismatches:
        problems.append("%d sampled points do not match the corpus" % len(mismatches))

    # The sampled vectors must be the ones the cache holds for the same text and
    # the same encoder fingerprint. This is what proves the index content, not
    # just its metadata. Every skip below is a failure: a publish gate that
    # quietly compares nothing is not a gate.
    cache_comparisons = 0
    cache_skipped: list[str] = []
    if cache_path is None or not cache_path.is_file():
        problems.append("embedding cache missing: %s" % cache_path)
        cache_skipped.append("cache file absent")
    else:
        with closing(Cache(cache_path, readonly=True)) as cache:
            fingerprint = manifest["model"]["fingerprint"]
            grouped: dict[str, list[dict]] = {}
            for collection, document in picked:
                grouped.setdefault(collection, []).append(document)
            for collection, docs in grouped.items():
                keys = [cache_key(d, fingerprint) for d in docs]
                found = cache.lookup(keys)
                for document, key in zip(docs, keys):
                    if key not in found:
                        problems.append(
                            "no cached vector for %s (text %s, fingerprint %s)"
                            % (point_id(document), document["text_sha256"][:12], fingerprint[:12])
                        )
                        continue
                    records = client.retrieve(
                        collection_name=collection, ids=[point_id(document)], with_vectors=True
                    )
                    if not records:
                        problems.append(
                            "point %s vanished before the cache comparison" % point_id(document)
                        )
                        continue
                    stored = np.asarray(records[0].vector, dtype="<f4")
                    cached = np.asarray(found[key], dtype="<f4")
                    if stored.shape != cached.shape or stored.shape != (manifest["model"]["dim"],):
                        problems.append("vector shape mismatch for %s" % point_id(document))
                        continue
                    if not (np.all(np.isfinite(stored)) and np.all(np.isfinite(cached))):
                        problems.append("non-finite vector for %s" % point_id(document))
                        continue
                    # The model runs in bf16, so two encodings of the same text differ
                    # in the last bits (measured max 3.6e-4) and Qdrant re-normalises
                    # cosine vectors on write. Compare direction, not bits: a vector
                    # produced from different text or a different model would not be
                    # parallel to the cached one.
                    cosine = float(
                        np.dot(stored, cached) / (np.linalg.norm(stored) * np.linalg.norm(cached))
                    )
                    if not np.isfinite(cosine):
                        problems.append("non-finite cosine for %s" % point_id(document))
                    elif cosine < 0.9999:
                        problems.append(
                            "vector for %s differs from the embedding cache "
                            "(cosine %.6f)" % (point_id(document), cosine)
                        )
                    else:
                        cache_comparisons += 1
    if cache_comparisons < len(picked):
        problems.append(
            "only %d of %d sampled vectors were compared against the cache"
            % (cache_comparisons, len(picked))
        )

    inputs_ok = True
    for path, key in checks:
        if manifest["inputs"].get(key) != sha256_file(path):
            inputs_ok = False
            problems.append("input hash drift: " + str(path))
    return {
        "ok": not problems,
        "collection_names": {kind: name for kind, name in names.items() if name in collections},
        "expected_counts": {k: len(v) for k, v in collections.items()},
        "service_counts": service_counts,
        "aliases": aliases,
        "sampled_points": len(picked),
        "vector_checks": len(vector_checks),
        "cache_comparisons": cache_comparisons,
        "cache_skipped": cache_skipped,
        "sample_mismatches": mismatches[:5],
        "input_hashes_match": inputs_ok,
        "problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    # One sample is not a verification: with 0 or 1 the "every sample must match
    # the cache" gate below is satisfied by an empty sample set, so a refused
    # build would report ok. Each collection is sampled from its own corpus.
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples 至少为 2，否则抽样校验会因空样本而自动通过")
    # The embedding cache is shared by every index version (content addressed),
    # so it lives beside the versioned manifests. Deriving it from a versioned
    # default silently produced zero cache comparisons.
    cache = args.cache or (args.workspace / "output" / "embed-cache.sqlite3")
    result = verify(args.workspace, args.manifest, args.url, args.samples, cache)
    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(data)
    print(data, end="")
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
