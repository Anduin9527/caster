"""Clean and split the pinned Danbooru Wiki Parquet into reproducible JSONL.

Run in an isolated environment with pyarrow. This stage does not embed text or
write to the CASTER business database.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import html
import io
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

SCHEMA_VERSION = 1
CLEANING_VERSION = "wiki-markup-v1"
REQUIRED_COLUMNS = {
    "id",
    "created_at",
    "updated_at",
    "title",
    "body",
    "is_locked",
    "other_names",
    "is_deleted",
}
WIKI_LINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
EXTERNAL_LINK = re.compile(r"\[(https?://[^\s\]]+)(?:\s+([^\]]+))?\]")
HTML_TAG = re.compile(r"<[^>]+>")
HEADING = re.compile(r"^h[1-6]\.\s*", re.IGNORECASE)
SPACE = re.compile(r"[ \t\f\v]+")
SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_aliases(raw: object) -> tuple[list[str], str | None]:
    if raw is None or raw == "":
        return [], None
    if not isinstance(raw, str) or len(raw) > 100_000:
        return [], "invalid_alias_type_or_length"
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
        return [], "invalid_alias_literal"
    if not isinstance(value, (list, tuple)):
        return [], "alias_not_list"
    aliases: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return [], "alias_non_string"
        alias = SPACE.sub(" ", item.strip())
        key = alias.casefold()
        if alias and key not in seen:
            aliases.append(alias)
            seen.add(key)
    return aliases, None


def clean_body(raw: str) -> tuple[str, list[str]]:
    links: list[str] = []

    def replace_wiki(match: re.Match[str]) -> str:
        target, separator, label = match.group(1).partition("|")
        target = target.strip()
        if target and target not in links:
            links.append(target)
        return label.strip() if separator and label.strip() else target

    text = html.unescape(raw.replace("\r\n", "\n").replace("\r", "\n"))
    text = WIKI_LINK.sub(replace_wiki, text)
    text = EXTERNAL_LINK.sub(lambda match: (match.group(2) or match.group(1)).strip(), text)
    text = HTML_TAG.sub(" ", text)
    paragraphs: list[str] = []
    for line in text.split("\n"):
        line = SPACE.sub(" ", HEADING.sub("", line)).strip()
        line = line.strip("*_` ")
        if line:
            paragraphs.append(line)
        elif paragraphs and paragraphs[-1] != "":
            paragraphs.append("")
    return "\n".join(paragraphs).strip(), links


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    rest = paragraph
    while len(rest) > max_chars:
        window = rest[: max_chars + 1]
        boundaries = [match.end() for match in SENTENCE_END.finditer(window)]
        cut = boundaries[-1] if boundaries else window.rfind(" ")
        if cut < max_chars // 2:
            cut = max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def chunk_body(body: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    for paragraph in paragraphs:
        for piece in split_long_paragraph(paragraph, max_chars):
            if current and len(current) + 2 + len(piece) > max_chars:
                chunks.append(current)
                current = ""
            current = piece if not current else current + "\n\n" + piece
    if current:
        chunks.append(current)
    return chunks


def write_jsonl(stream, row: dict) -> None:
    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


@contextmanager
def deterministic_gzip_text(path: Path):
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as packed:
            with io.TextIOWrapper(packed, encoding="utf-8") as text:
                yield text


def process(source: Path, output_dir: Path, expected_sha256: str, max_chars: int) -> dict:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    input_sha256 = sha256_file(source)
    if input_sha256 != expected_sha256:
        raise ValueError(f"input SHA256 mismatch: {input_sha256}")
    parquet = pq.ParquetFile(source)
    missing = REQUIRED_COLUMNS - set(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = output_dir / "wiki-chunks.jsonl.gz"
    names_path = output_dir / "wiki-names.jsonl.gz"
    anomalies_path = output_dir / "wiki-anomalies.jsonl"
    manifest_path = output_dir / "manifest.json"
    temporary = [
        path.with_name(path.name + ".partial")
        for path in (chunks_path, names_path, anomalies_path, manifest_path)
    ]
    for path in temporary:
        if path.exists():
            raise FileExistsError(f"unfinished prior output: {path}")

    counts: Counter[str] = Counter()
    seen_ids: set[int] = set()
    try:
        with (
            deterministic_gzip_text(temporary[0]) as chunks_out,
            deterministic_gzip_text(temporary[1]) as names_out,
            temporary[2].open("w", encoding="utf-8") as anomalies_out,
        ):
            for batch in parquet.iter_batches(batch_size=2048, columns=sorted(REQUIRED_COLUMNS)):
                for row in batch.to_pylist():
                    counts["input_rows"] += 1
                    source_id = row["id"]
                    if not isinstance(source_id, int) or source_id in seen_ids:
                        counts["invalid_or_duplicate_id"] += 1
                        write_jsonl(
                            anomalies_out,
                            {"source_id": source_id, "reason": "invalid_or_duplicate_id"},
                        )
                        continue
                    seen_ids.add(source_id)
                    if row["is_deleted"] is True:
                        counts["deleted_rows"] += 1
                        continue
                    title = row["title"]
                    if not isinstance(title, str) or not title.strip():
                        counts["missing_title"] += 1
                        write_jsonl(
                            anomalies_out, {"source_id": source_id, "reason": "missing_title"}
                        )
                        continue
                    title = title.strip()
                    aliases, alias_error = parse_aliases(row["other_names"])
                    if alias_error:
                        counts[alias_error] += 1
                        write_jsonl(anomalies_out, {"source_id": source_id, "reason": alias_error})
                    raw_body = row["body"] if isinstance(row["body"], str) else ""
                    body, links = clean_body(raw_body)
                    names = {
                        "source_id": source_id,
                        "title": title,
                        "aliases": aliases,
                        "source_url": f"https://danbooru.donmai.us/wiki_pages/{source_id}",
                    }
                    write_jsonl(names_out, names)
                    counts["name_entries"] += 1
                    if not body:
                        counts["empty_body_rows"] += 1
                        continue
                    parts = chunk_body(body, max_chars)
                    if not parts:
                        counts["empty_after_cleaning"] += 1
                        continue
                    counts["semantic_documents"] += 1
                    counts["semantic_chunks"] += len(parts)
                    if len(parts) > 1:
                        counts["split_documents"] += 1
                    for index, part in enumerate(parts):
                        text = title + "\n\n" + part
                        write_jsonl(
                            chunks_out,
                            {
                                "chunk_id": f"wiki:{source_id}:{index:04d}",
                                "source_id": source_id,
                                "source_url": names["source_url"],
                                "title": title,
                                "aliases": aliases,
                                "updated_at": row["updated_at"],
                                "chunk_index": index,
                                "chunk_count": len(parts),
                                "text": text,
                                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                "wiki_links": links,
                            },
                        )
        outputs = {}
        for final, partial in zip((chunks_path, names_path, anomalies_path), temporary[:3]):
            outputs[final.name] = {"sha256": sha256_file(partial), "bytes": partial.stat().st_size}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "cleaning_version": CLEANING_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input": {
                "path": str(source),
                "sha256": input_sha256,
                "rows": parquet.metadata.num_rows,
                "columns": parquet.schema_arrow.names,
            },
            "chunking": {
                "max_body_chars": max_chars,
                "method": "paragraph_then_sentence",
                "overlap_chars": 0,
            },
            "counts": dict(sorted(counts.items())),
            "outputs": outputs,
        }
        temporary[3].write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        for final, partial in zip(
            (chunks_path, names_path, anomalies_path, manifest_path), temporary
        ):
            partial.replace(final)
        return manifest
    except Exception:
        for path in temporary:
            path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()
    print(
        json.dumps(
            process(args.input, args.output_dir, args.expected_sha256, args.max_chars),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
