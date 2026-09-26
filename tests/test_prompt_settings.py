from aigc.prompt_settings import PromptSettingsUpdate, get_prompt_settings, save_prompt_settings
from aigc.store import Store


def test_prompt_settings_have_defaults_and_persist_as_one_hashed_record(tmp_path):
    store = Store(tmp_path / "state")
    default = get_prompt_settings(store)

    assert default["source"] == "default"
    assert default["artist_style"] == "@rella"
    assert "masterpiece" in default["fixed_positive"]
    assert "score_1" in default["fixed_negative"]

    saved = save_prompt_settings(
        store,
        PromptSettingsUpdate(
            artist_style="@rella, @another",
            fixed_positive="masterpiece, safe",
            fixed_negative="worst quality, blurry",
        ),
    )
    loaded = get_prompt_settings(store)

    assert saved == loaded
    assert loaded["source"] == "saved"
    assert loaded["content_hash"] != default["content_hash"]
    assert len(store.list("prompt_settings")) == 1


def test_prompt_settings_allow_empty_runtime_defaults(tmp_path):
    store = Store(tmp_path / "state")
    saved = save_prompt_settings(
        store, PromptSettingsUpdate(artist_style="", fixed_positive="", fixed_negative="")
    )

    assert saved["artist_style"] == ""
    assert saved["fixed_positive"] == ""
    assert saved["fixed_negative"] == ""
