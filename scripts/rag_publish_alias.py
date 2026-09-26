"""Publish a built collection behind its stable alias, only if it verifies.

The build never touches the alias, so an interrupted or half-written collection
cannot be served. This step is the gate: it runs the independent verification
first and switches the alias only when that passes, atomically, in one call. A
failed publish leaves the previous collection published and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_verify_index import verify  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument(
        "--cache", type=Path, help="embedding cache; defaults to output/embed-cache.sqlite3"
    )
    parser.add_argument("--wiki-alias", default="wiki")
    parser.add_argument("--template-alias", default="templates")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cache = args.cache or (args.workspace / "output" / "embed-cache.sqlite3")
    result = verify(args.workspace, args.manifest, args.qdrant_url, args.samples, cache)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    if not result["ok"]:
        print(json.dumps({"published": False, "problems": result["problems"]}, ensure_ascii=False))
        raise SystemExit(2)

    names = result["collection_names"]
    operations = []
    for alias, kind in ((args.wiki_alias, "wiki"), (args.template_alias, "template")):
        collection = names.get(kind)
        if collection not in result["expected_counts"]:
            continue
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)
            )
        )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "published": False,
                    "would_point": {
                        op.create_alias.alias_name: op.create_alias.collection_name
                        for op in operations
                    },
                    "currently": result["aliases"],
                },
                ensure_ascii=False,
            )
        )
        return
    with closing(QdrantClient(url=args.qdrant_url, prefer_grpc=False, timeout=120)) as client:
        client.update_collection_aliases(change_aliases_operations=operations)
    print(
        json.dumps(
            {
                "published": True,
                "aliases": {
                    op.create_alias.alias_name: op.create_alias.collection_name for op in operations
                },
                "verification": {
                    "sampled_points": result["sampled_points"],
                    "service_counts": result["service_counts"],
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
