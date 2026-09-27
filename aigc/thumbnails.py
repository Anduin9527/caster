"""Bounded thumbnail cache for immutable asset files; original files stay untouched."""

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps


@lru_cache(maxsize=128)
def thumbnail(path: str, version: str, size: int = 384) -> bytes:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=92)
        return output.getvalue()
