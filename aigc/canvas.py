"""Curated Anima canvas presets and immutable downstream size inheritance."""

import json
from pathlib import Path

PRESETS = json.loads(
    (Path(__file__).resolve().parents[1] / "integrations/canvas-presets.json").read_text()
)
SIZES = {p["id"]: (p["width"], p["height"]) for p in PRESETS}
DEFAULT = "1024x1536"


def preset_size(key):
    if key not in SIZES:
        raise ValueError("Unsupported canvas preset")
    return SIZES[key]


def source_size(asset):
    w, h = asset["width"], asset["height"]
    if w % 8 or h % 8 or not (64 <= w <= 4096 and 64 <= h <= 4096):
        raise ValueError("Source canvas is not supported")
    return w, h
