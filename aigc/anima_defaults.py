"""Default *runtime preferences* for Anima prompt assembly.

These values are not template content.  They are editable through the prompt
settings API and are injected only when the final generation prompt is built.
The aliases at the bottom remain for old callers and migration tests.
"""

DEFAULT_ARTIST_STYLE = "@rella"
DEFAULT_FIXED_POSITIVE = (
    "masterpiece, very aesthetic, best quality, score_9, score_8, score_7, year 2025, official_art"
)
DEFAULT_FIXED_NEGATIVE = (
    "score_1, score_2, score_3, blurry, worst quality, low quality, jpeg artifacts, "
    "signature, watermark, username, error, deformed hands, bad anatomy, extra limbs, "
    "poorly drawn hands, poorly drawn face, mutation, deformed, extra eyes, extra arms, "
    "extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed, "
    "bad proportions, missing arms, missing legs, extra digit, fewer digits, cropped, "
    "normal quality, monochrome, greyscale, lineart"
)

# Backwards-compatible names.  Historical non-exact workflows used artist
# first.  Keep that byte order frozen; only the structured exact compiler uses
# the official Anima section order.
ARTIST = DEFAULT_ARTIST_STYLE
QUALITY = DEFAULT_FIXED_POSITIVE
POSITIVE = DEFAULT_ARTIST_STYLE + ", " + DEFAULT_FIXED_POSITIVE
NEGATIVE = DEFAULT_FIXED_NEGATIVE


def runtime_defaults(settings=None):
    value = settings or {}
    return {
        "artist_style": str(value.get("artist_style", DEFAULT_ARTIST_STYLE)),
        "fixed_positive": str(value.get("fixed_positive", DEFAULT_FIXED_POSITIVE)),
        "fixed_negative": str(value.get("fixed_negative", DEFAULT_FIXED_NEGATIVE)),
        "content_hash": str(value.get("content_hash", "")),
    }


def positive_prompt(text, settings=None):
    """Legacy flat-prompt compatibility helper.

    Production Anima prompts use :func:`compile_anima_recipe`, which can place
    the artist section precisely.  This helper only prevents older direct
    workflow callers from losing the configured defaults.
    """
    configured = runtime_defaults(settings)
    prefix = ", ".join(
        value for value in (configured["artist_style"], configured["fixed_positive"]) if value
    )
    defaults = {tag.strip().casefold() for tag in prefix.split(",") if tag.strip()}
    body = ", ".join(
        tag.strip()
        for tag in text.split(",")
        if tag.strip() and tag.strip().casefold() not in defaults
    )
    return prefix + (", " + body if prefix and body else body)


def escape_template_tags(text):
    """Escape literal name qualifiers without rewriting explicit attention groups."""
    import re

    parts = text.replace("（", "(").replace("）", ")").split(",")
    for i, part in enumerate(parts):
        stripped = part.strip()
        if stripped.startswith("(") and stripped.endswith(")"):
            continue
        parts[i] = re.sub(r"(?<!\\)([()])", r"\\\1", part)
    return ",".join(parts)
