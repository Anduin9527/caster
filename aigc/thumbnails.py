"""Bounded thumbnail cache for immutable asset files; original files stay untouched."""

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps


@lru_cache(maxsize=128)
def thumbnail(path: str, version: str) -> bytes:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((384, 384), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=82)
        return output.getvalue()
