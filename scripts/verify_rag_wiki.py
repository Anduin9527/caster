"""Verify the integrity of a prepared Wiki corpus without reading source Parquet."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(output_dir: Path) -> dict:
    manifest = json.loads((output_dir / "manifest.json").read_text())
    for name, expected in manifest["outputs"].items():
        path = output_dir / name
        if path.stat().st_size != expected["bytes"] or sha256_file(path) != expected["sha256"]:
            raise ValueError(f"output hash or size mismatch: {name}")

    name_ids: set[int] = set()
    with gzip.open(output_dir / "wiki-names.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            source_id = record["source_id"]
            if source_id in name_ids:
                raise ValueError(f"duplicate name source ID: {source_id}")
            name_ids.add(source_id)
    if len(name_ids) != manifest["counts"]["name_entries"]:
        raise ValueError("name count mismatch")

    chunk_ids: set[str] = set()
    semantic_ids: set[int] = set()
    max_body_chars = manifest["chunking"]["max_body_chars"]
    with gzip.open(output_dir / "wiki-chunks.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            chunk_id = record["chunk_id"]
            source_id = record["source_id"]
            text = record["text"]
            title = record["title"]
            if chunk_id in chunk_ids:
                raise ValueError(f"duplicate chunk ID: {chunk_id}")
            if source_id not in name_ids:
                raise ValueError(f"chunk without name entry: {chunk_id}")
            if not text.startswith(title + "\n\n") or len(text) - len(title) - 2 > max_body_chars:
                raise ValueError(f"invalid chunk text or length: {chunk_id}")
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != record["text_sha256"]:
                raise ValueError(f"chunk text hash mismatch: {chunk_id}")
            if record["chunk_index"] >= record["chunk_count"]:
                raise ValueError(f"invalid chunk index: {chunk_id}")
            chunk_ids.add(chunk_id)
            semantic_ids.add(source_id)
    if len(chunk_ids) != manifest["counts"]["semantic_chunks"]:
        raise ValueError("chunk count mismatch")
    if len(semantic_ids) != manifest["counts"]["semantic_documents"]:
        raise ValueError("semantic document count mismatch")
    counts = manifest["counts"]
    if counts["input_rows"] != counts["deleted_rows"] + counts["missing_title"] + counts[
        "empty_body_rows"
    ] + counts["semantic_documents"] + counts.get("empty_after_cleaning", 0) + counts.get(
        "invalid_or_duplicate_id", 0
    ):
        raise ValueError("input accounting mismatch")
    return {
        "ok": True,
        "input_sha256": manifest["input"]["sha256"],
        "name_entries": len(name_ids),
        "semantic_documents": len(semantic_ids),
        "semantic_chunks": len(chunk_ids),
        "output_hashes_verified": len(manifest["outputs"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.output_dir)
    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(data)
    print(data, end="")


if __name__ == "__main__":
    main()
