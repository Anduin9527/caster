"""Shared runtime defaults and local config.env loading (no shell execution)."""

import json
import os
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def flag(values, key, default=False):
    """Read an AIGC_* boolean. Config values are strings, so '0' and 'false' are
    false -- bool('0') would silently enable a feature the user turned off."""
    raw = str(values.get(key, "")).strip().casefold()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    if not raw:
        return default
    raise ValueError(key + " expects 1/0 or true/false")


def load(path=None):
    values = {
        "AIGC_API_URL": "http://127.0.0.1:8189",
        "AIGC_COMFY_URL": "http://127.0.0.1:8188",
        "AIGC_UI_URL": "http://127.0.0.1:4173",
        "AIGC_DATA_DIR": str(ROOT / "data"),
        # Semantic (vector) retrieval. Empty AIGC_RAG_DIR means the index is not
        # deployed and retrieval reports semantic search as unavailable instead
        # of silently returning fewer hits.
        "AIGC_RAG_DIR": "",
        "AIGC_RAG_QDRANT_URL": "http://127.0.0.1:6333",
        "AIGC_RAG_WIKI_ALIAS": "wiki",
        "AIGC_RAG_TEMPLATE_ALIAS": "templates",
        "AIGC_RAG_MODEL_KEY": "qwen3-embedding-0.6b",
        "AIGC_RAG_DIM": "1024",
        "AIGC_RAG_MAX_LENGTH": "2048",
        "AIGC_RAG_CPU_THREADS": "16",
        # How many points the wiki branch asks Qdrant for, per hit it will
        # return, before aggregating them by source. Wiki points are one per
        # chunk, so an entry occupies several slots and a narrow pool loses the
        # entry's best chunk. Tune against a frozen evaluation set when changing
        # the corpus or encoder; individual experiment results stay in data/.
        "AIGC_RAG_WIKI_OVERFETCH": "50",
        # Exact Chinese tag names can be translated through the shipped ffdkj
        # vocabulary and searched as a second Qwen query. Only a whole-query
        # match is eligible; broader substring expansion measured worse.
        "AIGC_RAG_EXACT_TAG_EXPANSION": "1",
        # Whole-query resolver backed by the versioned local catalog. Keep it
        # off in fresh environments until that build contains the names table.
        "AIGC_RAG_EXACT_RESOLVER": "0",
        # GPU encoding is an explicit deployment choice on shared GPU hosts.
        "AIGC_RAG_DEVICE": "cpu",
        # Empty means the model card's default instruction.
        "AIGC_RAG_INSTRUCTION": "",
        "AIGC_RAG_INDEX_VERSION": "index-v2",
    }
    source = Path(
        path if path is not None else os.environ.get("AIGC_CONFIG_FILE", ROOT / "config.env")
    ).expanduser()
    if source.exists():
        for line in source.read_text().splitlines():
            tokens = shlex.split(line, comments=True)
            if not tokens:
                continue
            if tokens[0] == "export":
                tokens = tokens[1:]
            key, sep, value = " ".join(tokens).partition("=")
            if not sep or not key.startswith("AIGC_"):
                raise ValueError("config.env expects AIGC_NAME=value assignments")
            values[key] = value
    # Explicit process overrides support isolated tests and deployed services.
    values.update({k: v for k, v in os.environ.items() if k.startswith("AIGC_")})
    data = Path(values["AIGC_DATA_DIR"]).expanduser()
    values["AIGC_DATA_DIR"] = str(data if data.is_absolute() else ROOT / data)
    return values


if __name__ == "__main__":
    config = load()
    print(json.dumps({k: config[k] for k in ("AIGC_API_URL", "AIGC_UI_URL")}))
