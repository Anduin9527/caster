from aigc.anima_defaults import NEGATIVE, POSITIVE
from aigc.anima_prompt import compile_anima_recipe, normalize_tag
from aigc.workflows import build


def test_anima_recipe_preserves_caption_bytes_and_special_tag_syntax():
    caption = "A black dress has a crisp collar, layered cuffs, and a fitted waist."
    prompt = compile_anima_recipe(
        {
            "count": ["1girl", "score_7"],
            "character": ["hatsune_miku", r"honkai \(series\)"],
            "outfit": ["(blue_eyes:1.2)", "maid", "maid"],
            "composition": ["full_body"],
        },
        [caption],
        ["maid_headdress"],
    )

    assert "score_7" in prompt["positive"]
    assert "hatsune miku" in prompt["positive"]
    assert r"honkai \(series\)" in prompt["positive"]
    assert "(blue_eyes:1.2)" in prompt["positive"]
    assert prompt["positive"].endswith(caption)
    assert prompt["positive"].count("maid") == 1
    assert prompt["negative"].startswith(NEGATIVE)
    assert "maid headdress" in prompt["negative"]
    assert prompt["workflow_prompt_mode"] == "exact"


def test_normalization_is_idempotent_and_unknown_sections_are_stable():
    first, _ = normalize_tag("character_name_(series)")
    second, _ = normalize_tag(first)
    assert first == second == r"character name \(series\)"

    prompt = compile_anima_recipe({"future_bucket": ["z_tag", "a_tag"]})
    assert prompt["recipe"]["sections"]["future_bucket"] == ["z tag", "a tag"]
    assert any(item["code"] == "unknown_section" for item in prompt["recipe"]["lint"])


def test_exact_prompt_reaches_anima_clip_nodes_byte_for_byte():
    prompt = compile_anima_recipe(
        {"outfit": ["maid", "white apron"]},
        ["The apron has a crisp edge, two waist ties, and a clean front panel."],
        ["maid headdress"],
    )
    graph, _, _ = build("sprite", prompt, 7, "exact-prompt")
    assert graph["4"]["inputs"]["text"] == prompt["positive"]
    assert graph["5"]["inputs"]["text"] == prompt["negative"]


def test_runtime_settings_follow_official_anima_section_order_without_entering_recipe():
    prompt = compile_anima_recipe(
        {
            "count": ["1girl"],
            "character": ["hatsune miku"],
            "series": ["vocaloid"],
            "outfit": ["maid"],
            "composition": ["full body"],
        },
        ["The white apron lies flat over the black dress."],
        prompt_settings={
            "fixed_positive": "masterpiece, year 2025, safe",
            "artist_style": "@rella",
            "fixed_negative": "worst quality, blurry",
            "content_hash": "settings-hash",
        },
    )

    positive = prompt["positive"]
    ordered = [
        "masterpiece",
        "year 2025",
        "safe",
        "1girl",
        "hatsune miku",
        "vocaloid",
        "@rella",
        "maid",
        "full body",
    ]
    positions = [positive.index(value) for value in ordered]
    assert positions == sorted(positions)
    assert prompt["recipe"]["runtime_settings"]["artist_style"] == ["@rella"]
    assert "@rella" not in sum(prompt["recipe"]["sections"].values(), [])
    assert prompt["recipe"]["assembly_order"][:6] == [
        "fixed_positive",
        "count",
        "character",
        "series",
        "artist_style",
        "artist",
    ]
    assert prompt["negative"] == "worst quality, blurry"


def test_legacy_prompt_keeps_pre_v2_workflow_finalization():
    legacy = {"positive": "maid, white apron", "negative": "blurry"}
    graph, _, _ = build("sprite", legacy, 7, "legacy-prompt")
    frozen_legacy_prefix = (
        "@rella, masterpiece, very aesthetic, best quality, "
        "score_9, score_8, score_7, year 2025, official_art"
    )
    assert POSITIVE == frozen_legacy_prefix
    assert graph["4"]["inputs"]["text"].startswith(frozen_legacy_prefix + ", maid")
    assert graph["5"]["inputs"]["text"].startswith(NEGATIVE + ", blurry")
