"""Build the versioned local Wiki catalog used beside the vector index.

The vector index deliberately stores no long text: a point carries the title, the
source IDs and the text hash, and the body is looked up when a hit is actually
used.  It also cannot decide whether a human-readable name is authoritative, so
canonical titles, reviewed translations and recall-only Wiki other_names are
stored with separate provenance.  Both lookups live in one SQLite file belonging
to the published index build; no process scans the gzip at query time.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aigc.rag_catalog import normalize_canonical, normalize_name  # noqa: E402

CATEGORY_NAMES = {0: "general", 1: "artist", 3: "copyright", 4: "character", 5: "meta"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(workspace: Path, out: Path, tag_db: Path | None = None) -> dict:
    wiki_dir = workspace / "output" / "wiki-v1"
    manifest = json.loads((wiki_dir / "manifest.json").read_text())
    corpus_hash = manifest["outputs"]["wiki-chunks.jsonl.gz"]["sha256"]
    names_hash = manifest["outputs"]["wiki-names.jsonl.gz"]["sha256"]
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + ".partial")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(str(temporary))
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute(
        "CREATE TABLE bodies(chunk_id TEXT PRIMARY KEY, source_id INTEGER, "
        "chunk_index INTEGER, chunk_count INTEGER, title TEXT, text TEXT)"
    )
    count = 0
    started = time.perf_counter()
    batch = []
    with gzip.open(wiki_dir / "wiki-chunks.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            batch.append(
                (
                    row["chunk_id"],
                    row["source_id"],
                    row["chunk_index"],
                    row["chunk_count"],
                    row["title"],
                    row["text"],
                )
            )
            if len(batch) >= 5000:
                connection.executemany("INSERT OR REPLACE INTO bodies VALUES(?,?,?,?,?,?)", batch)
                count += len(batch)
                batch = []
    if batch:
        connection.executemany("INSERT OR REPLACE INTO bodies VALUES(?,?,?,?,?,?)", batch)
        count += len(batch)
    connection.execute("CREATE INDEX bodies_source ON bodies(source_id, chunk_index)")
    connection.execute(
        "CREATE TABLE names(key_kind TEXT NOT NULL, lookup_key TEXT NOT NULL, "
        "source_id INTEGER NOT NULL, title TEXT NOT NULL, matched_text TEXT NOT NULL, "
        "provenance TEXT NOT NULL, category TEXT NOT NULL DEFAULT '', "
        "post_count INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY(key_kind, lookup_key, source_id, provenance))"
    )
    canonical_sources: dict[str, list[tuple[int, str]]] = {}
    canonical_count = alias_count = 0
    name_batch = []
    with gzip.open(wiki_dir / "wiki-names.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            source_id = int(row["source_id"])
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            canonical_key = normalize_canonical(title)
            canonical_sources.setdefault(canonical_key, []).append((source_id, title))
            name_batch.append(
                ("canonical", canonical_key, source_id, title, title, "canonical", "", 0)
            )
            canonical_count += 1
            for alias in row.get("aliases") or []:
                alias = str(alias).strip()
                key = normalize_name(alias)
                if key:
                    name_batch.append(
                        ("human", key, source_id, title, alias, "wiki_other_name", "", 0)
                    )
                    alias_count += 1
            if len(name_batch) >= 5000:
                connection.executemany(
                    "INSERT OR REPLACE INTO names VALUES(?,?,?,?,?,?,?,?)", name_batch
                )
                name_batch = []
    if name_batch:
        connection.executemany("INSERT OR REPLACE INTO names VALUES(?,?,?,?,?,?,?,?)", name_batch)

    translated_count = 0
    if tag_db is not None:
        source = sqlite3.connect("file:%s?mode=ro" % tag_db.resolve(), uri=True)
        try:
            translated_batch = []
            for name, category, chinese, post_count in source.execute(
                "SELECT name, category, cn_name, post_count FROM tags "
                "WHERE name <> '' AND cn_name <> '' ORDER BY name"
            ):
                matches = canonical_sources.get(normalize_canonical(str(name)), ())
                key = normalize_name(str(chinese))
                if not key:
                    continue
                for source_id, title in matches:
                    translated_batch.append(
                        (
                            "human",
                            key,
                            source_id,
                            title,
                            str(chinese),
                            "translated_name",
                            CATEGORY_NAMES.get(int(category), str(category)),
                            int(post_count or 0),
                        )
                    )
                    translated_count += 1
                if len(translated_batch) >= 5000:
                    connection.executemany(
                        "INSERT OR REPLACE INTO names VALUES(?,?,?,?,?,?,?,?)", translated_batch
                    )
                    translated_batch = []
            if translated_batch:
                connection.executemany(
                    "INSERT OR REPLACE INTO names VALUES(?,?,?,?,?,?,?,?)", translated_batch
                )
        finally:
            source.close()
    connection.execute("CREATE INDEX names_lookup ON names(key_kind, lookup_key, provenance)")
    connection.commit()
    name_rows = connection.execute("SELECT COUNT(*) FROM names").fetchone()[0]
    connection.execute("VACUUM")
    connection.close()
    temporary.replace(out)
    return {
        "chunks": count,
        "canonical_names": canonical_count,
        "wiki_other_names": alias_count,
        "translated_names": translated_count,
        "stored_name_rows": name_rows,
        "corpus_hash": corpus_hash,
        "names_hash": names_hash,
        "tag_db_hash": sha256_file(tag_db) if tag_db is not None else None,
        "bytes": out.stat().st_size,
        "seconds": round(time.perf_counter() - started, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--tag-db", type=Path, help="optional ffdkj tag.sqlite for provenance-aware translations"
    )
    args = parser.parse_args()
    print(json.dumps(build(args.workspace, args.out, args.tag_db), ensure_ascii=False))


if __name__ == "__main__":
    main()
