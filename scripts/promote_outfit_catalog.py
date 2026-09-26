"""Promote the approved 50-outfit catalog into the live template library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aigc.config import load
from aigc.outfit_catalog import CATALOG_PATH, load_catalog, promote_catalog
from aigc.store import Store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the atomic replacement; omission is a read-only preview",
    )
    args = parser.parse_args()
    config = load()
    store = Store(config["AIGC_DATA_DIR"])
    catalog, content_hash = load_catalog(CATALOG_PATH)
    current = store.list("prompt_template")
    preview = {
        "catalog_id": catalog.catalog_id,
        "content_hash": content_hash,
        "new_outfits": len(catalog.recipes),
        "remove_non_personal_outfits": sum(
            row.get("kind") == "outfit" and row.get("source") != "user" for row in current
        ),
        "preserve_personal_outfits": sum(
            row.get("kind") == "outfit" and row.get("source") == "user" for row in current
        ),
        "preserve_character_templates": sum(row.get("kind") == "character" for row in current),
        "apply": args.apply,
    }
    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False))
        return 0
    result = promote_catalog(store, CATALOG_PATH)
    print(json.dumps({**preview, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
