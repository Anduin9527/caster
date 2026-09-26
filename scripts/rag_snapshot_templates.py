"""Snapshot the CASTER prompt templates into the RAG workspace, read-only.

The business SQLite is the source of truth for templates, so it is never written
to: it is opened with ``mode=ro`` and the records are exported with a hash of the
file that produced them. The index build consumes this snapshot; live search re-checks the store
before any template is used as an execution input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1
ALIAS_PATH = "translation/ffdkj-mapped/caster-names-mapped.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_aliases(root: Path) -> dict[str, str]:
    path = root / ALIAS_PATH
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    aliases: dict[str, str] = {}
    for key in ("characters", "works"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("id") and item.get("translated_name"):
                aliases[item["id"]] = str(item["translated_name"]).strip()
    return aliases


def snapshot(store_path: Path, out_path: Path) -> dict:
    if not store_path.is_file():
        raise FileNotFoundError("business store not found: %s" % store_path)
    # Read-only URI: a snapshot must never be able to modify the live store.
    connection = sqlite3.connect("file:%s?mode=ro" % store_path, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = [
            dict(r)
            for r in connection.execute("SELECT body FROM records WHERE kind='prompt_template'")
        ]
    finally:
        connection.close()
    aliases = load_aliases(store_path.parent)
    templates = []
    for row in rows:
        body = json.loads(row["body"])
        if body.get("kind") not in ("character", "outfit"):
            continue
        body["alias"] = aliases.get(body.get("id") or "", "")
        templates.append(body)
    templates.sort(key=lambda t: str(t.get("id")))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at": time.time(),
        "source": {
            "path": str(store_path),
            "sha256": sha256_file(store_path),
            "opened": "read-only",
        },
        "counts": {
            "templates": len(templates),
            "character": sum(1 for t in templates if t.get("kind") == "character"),
            "outfit": sum(1 for t in templates if t.get("kind") == "outfit"),
            "with_alias": sum(1 for t in templates if t.get("alias")),
        },
        "templates": templates,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(out_path.name + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    temporary.replace(out_path)
    return {
        "templates": len(templates),
        "sha256": sha256_file(out_path),
        "bytes": out_path.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.store, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
