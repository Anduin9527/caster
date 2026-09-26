"""Download the embedding models into the workspace and pin their commits.

The server reaches huggingface.co only through the local proxy, so the proxy
variables are required. The resolved commit of every repository is written to
``models/manifest.json``: a later rebuild must compare against it, because a
silent model update would change every vector in the index.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from huggingface_hub import model_info, snapshot_download

MODELS = {
    "qwen3-embedding-0.6b": "Qwen/Qwen3-Embedding-0.6B",
    "qwen3-embedding-4b": "Qwen/Qwen3-Embedding-4B",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--only", default="", help="comma separated model keys")
    args = parser.parse_args()

    wanted = [k.strip() for k in args.only.split(",") if k.strip()] or list(MODELS)
    cache = args.workspace / "models"
    cache.mkdir(parents=True, exist_ok=True)
    manifest_path = cache / "manifest.json"
    # Merge: an earlier run may have recorded the other model, and losing that
    # record would make the index unreproducible.
    manifest = {
        "models": {},
        "hf_endpoint": os.environ.get("HF_ENDPOINT", "https://huggingface.co"),
    }
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest.setdefault("models", {})
        except ValueError:
            pass

    for key in wanted:
        repo = MODELS[key]
        path = snapshot_download(repo_id=repo, cache_dir=cache)
        info = model_info(repo)
        manifest["models"][key] = {
            "repo": repo,
            "commit": info.sha,
            "local_path": path,
            "last_modified": info.lastModified.isoformat() if info.lastModified else None,
            "license": getattr(info.card_data, "license", None) if info.card_data else None,
        }
        print(json.dumps(manifest["models"][key], ensure_ascii=False))

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print("wrote", manifest_path)


if __name__ == "__main__":
    main()
