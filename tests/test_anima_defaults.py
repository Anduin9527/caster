from aigc.anima_defaults import NEGATIVE, POSITIVE
from aigc.prompts import compile_prompt
from aigc.schema import SceneSpec
from aigc.workflows import build

NORMALIZED_FIXED_POSITIVE = (
    "masterpiece, very aesthetic, best quality, score_9, score_8, score_7, year 2025, official art"
)


def test_anima_defaults_and_seed_binding_are_used_by_runtime():
    for kind in ("sprite", "background"):
        p = compile_prompt(
            SceneSpec(asset_type=kind, character_id="a" if kind == "sprite" else None)
        )
        assert p["positive"].startswith(NORMALIZED_FIXED_POSITIVE)
        assert p["negative"].startswith(NEGATIVE)
        if kind == "background":
            assert "no people" in p["positive"] and "human figure" in p["negative"]
        g, outputs, _ = build(kind, p, 1956601075, "test")
        assert g["7"]["class_type"] == "SamplerCustom"
        assert g["7"]["inputs"]["noise_seed"] == 1956601075
        assert g["7"]["inputs"]["cfg"] == 4 and g["7"]["inputs"]["add_noise"]
        assert g["10"]["inputs"]["sampler_name"] == "euler"
        assert g["11"]["inputs"] == dict(model=["12", 0], steps=36, alpha=0.6, beta=0.6)
        assert g["12"]["inputs"]["shift"] == 3
        assert g["4"]["inputs"]["text"] == p["positive"]
        assert g["5"]["inputs"]["text"] == p["negative"]
        assert outputs == {"9": "original"}


def test_quality_changes_do_not_leak_into_qwen_or_character_identity():
    p = compile_prompt(
        SceneSpec(asset_type="expression", character_id="a", outfit_id="coat", expression="a smile")
    )
    assert POSITIVE not in p["positive"] and "score_1" not in p["negative"]
    assert p["compiler_version"] == "1.0"
    for word in (
        "hatsune miku",
        "sheer blouse",
        "sideboob",
        "smartphone",
        "photo background",
        "upper body",
    ):
        assert word not in POSITIVE


def test_template_names_escape_once_and_rella_reaches_runtime():
    from aigc.anima_defaults import escape_template_tags
    from aigc.templates import prompt_tags

    tags = prompt_tags(
        {"trigger": "rem（re:zero）, re:zero", "tags": [r"honkai \(series\)", "(blue eyes:1.2)"]}
    )
    assert tags == [r"rem\(re:zero\), re:zero", r"honkai \(series\)", "(blue eyes:1.2)"]
    assert [escape_template_tags(t) for t in tags] == tags
    assert (
        escape_template_tags("kiana kaslana (honkai series)") == r"kiana kaslana \(honkai series\)"
    )
    assert escape_template_tags("角色名（作品名）") == r"角色名\(作品名\)"
    p = compile_prompt(
        SceneSpec(asset_type="sprite", character_id="a"), {"fixed_tags": tags, "outfits": []}
    )
    g, _, _ = build("sprite", p, 42, "style-test")
    text = g["4"]["inputs"]["text"]
    assert text.startswith(NORMALIZED_FIXED_POSITIVE)
    assert text.count("@rella") == 1
    assert text.index(r"rem\(re:zero\)") < text.index("@rella")
    assert r"rem\(re:zero\)" in text and "(blue eyes:1.2)" in text
    direct, _, _ = build(
        "background", {"positive": "empty landscape", "negative": ""}, 42, "direct"
    )
    assert direct["4"]["inputs"]["text"].startswith(POSITIVE)
    assert direct["5"]["inputs"]["text"].startswith(NEGATIVE)


def test_outfit_uses_anima_reference_with_selected_defaults():
    character = {
        "fixed_tags": ["kiana kaslana", "honkai (series)", "blue eyes"],
        "prompt_sections": {
            "character": ["kiana kaslana"],
            "series": ["honkai (series)"],
            "general": ["blue eyes"],
        },
        "outfits": [{"id": "coat", "tags": ["blue coat"]}],
    }
    p = compile_prompt(
        SceneSpec(asset_type="outfit", character_id="k", outfit_id="coat"), character
    )
    g, outputs, _ = build(
        "outfit", p, 42, "outfit-check", {"reference": "source.png", "width": 1024, "height": 1536}
    )
    assert g["1"]["inputs"]["unet_name"] == "AnimaYume_v15_base.safetensors"
    assert g["6"]["inputs"]["pixels"] == ["13", 0] and g["13"]["inputs"]["image"] == "source.png"
    assert g["7"]["inputs"]["denoise"] == 0.8 and g["7"]["inputs"]["sampler_name"] == "euler"
    assert g["7"]["inputs"]["steps"] == 36 and g["7"]["inputs"]["seed"] == 42
    assert "@rella" in g["4"]["inputs"]["text"] and "official art" in g["4"]["inputs"]["text"]
    assert "blue coat" in g["4"]["inputs"]["text"] and outputs == {"9": "original"}
    text = g["4"]["inputs"]["text"]
    assert text.index("kiana kaslana") < text.index(r"honkai \(series\)") < text.index("@rella")
    assert text.index("@rella") < text.index("blue coat") < text.index("blue eyes")
