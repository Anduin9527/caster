from .anima_defaults import escape_template_tags
from .anima_prompt import compile_anima_recipe
from .schema import SceneSpec

# Routes that share the Anima quality/style prefix.
ANIMA_TYPES = ("sprite", "background", "outfit", "free")
# The free route must not force framing or background: the user's own action,
# scene and composition are the point of the route.
FREE_PREFIX = ["solo"]


def framing_prefix(spec):
    if spec.asset_type == "background":
        return ["no people", "empty scene"]
    if spec.asset_type == "free":
        return list(FREE_PREFIX)
    return ["solo", "full body"]


def compile_prompt(spec: SceneSpec, character=None, prompt_settings=None):
    fixed = []
    identity_sections = None
    outfit_tags = []
    outfit_captions = []
    outfit_excluded = []
    prose = []
    if character:
        fixed.extend(character["fixed_tags"])
        prose.append(character.get("description", ""))
        identity_sections = character.get("prompt_sections")
        if spec.outfit_id:
            outfits = {o["id"]: o for o in character["outfits"]}
            if spec.outfit_id not in outfits:
                raise ValueError("Unknown outfit")
            outfit = outfits[spec.outfit_id]
            outfit_tags.extend(outfit["tags"])
            outfit_captions.extend(outfit.get("caption_en") or [])
            outfit_excluded.extend(outfit.get("excluded_tags") or [])
            if not outfit_captions:
                prose.append(outfit.get("description", ""))
    prefix = framing_prefix(spec)
    seen = set()
    tags = []
    for tag in prefix + fixed + outfit_tags + spec.visual_tags:
        tag = escape_template_tags(tag.strip())
        key = tag.casefold()
        if tag and key not in seen:
            tags.append(tag)
            seen.add(key)
    prose.extend(outfit_captions)
    prose.extend(spec.prompt_captions)
    prose.extend([spec.action, spec.expression, spec.scene, spec.composition, spec.description])
    # The same sentence can be picked up by two fields ("在夜晚的街道上跳起来" is
    # both an action and a scene). Repeating it verbatim adds nothing, but a
    # repeat inside one field is the author's choice and stays.
    seen_prose = set()
    unique = []
    for text in prose:
        text = text.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen_prose:
            continue
        seen_prose.add(key)
        unique.append(text)
    positive = ", ".join(tags) + ". " + " ".join(unique)
    negative = "low quality, blurry, text, watermark" + (
        ", people, person, human figure"
        if spec.asset_type == "background"
        else ", malformed hands, cropped feet"
    )
    if spec.asset_type in ANIMA_TYPES:
        count = [tag for tag in prefix if tag == "solo"]
        composition = [tag for tag in prefix if tag != "solo"]
        if identity_sections:
            character_tags = list(identity_sections.get("character") or [])
            series_tags = list(identity_sections.get("series") or [])
            identity_general = list(identity_sections.get("general") or [])
        else:
            # Legacy characters only stored one flat fixed_tags list. Preserve
            # their contents while placing the first identity anchor before the
            # artist and all unclassified appearance tags after it. New records
            # use prompt_sections and need no inference.
            flat = [part.strip() for value in fixed for part in value.split(",") if part.strip()]
            character_tags = flat[:1]
            series_tags = []
            identity_general = flat[1:]
        result = compile_anima_recipe(
            {
                "count": count,
                "character": character_tags,
                "series": series_tags,
                "outfit": outfit_tags,
                "general": [*identity_general, *spec.visual_tags],
                "composition": composition,
            },
            unique,
            [*outfit_excluded, *spec.excluded_tags],
            (
                ["people", "person", "human figure"]
                if spec.asset_type == "background"
                else ([] if spec.asset_type == "free" else ["cropped feet"])
            ),
            compiler_version=(
                "2.0-anima-hybrid-free" if spec.asset_type == "free" else "2.0-anima-hybrid"
            ),
            prompt_settings=prompt_settings,
        )
        return result
    return {"positive": positive, "negative": negative, "compiler_version": "1.0"}
