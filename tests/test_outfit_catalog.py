import pytest

from aigc.outfit_catalog import load_catalog, promote_catalog
from aigc.prompt_settings import get_prompt_settings
from aigc.store import Store
from aigc.template_previews import source_url


def approve_current_catalog(store):
    catalog, content_hash = load_catalog()
    store.put(
        "outfit_catalog_review",
        {
            "catalog_id": catalog.catalog_id,
            "content_hash": content_hash,
            "prompt_settings_hash": get_prompt_settings(store)["content_hash"],
            "status": "approved",
            "approved_recipe_ids": [recipe.id for recipe in catalog.recipes],
        },
        catalog.catalog_id,
        replace=True,
    )
    return catalog


def test_catalog_has_fifty_valid_unique_recipes():
    catalog, content_hash = load_catalog()

    assert len(content_hash) == 64
    assert len(catalog.recipes) == 50
    assert len({recipe.id for recipe in catalog.recipes}) == 50
    assert all(recipe.tags and len(recipe.caption_en) == 2 for recipe in catalog.recipes)


def test_promotion_replaces_only_non_personal_outfits_and_marks_index(tmp_path):
    store = Store(tmp_path / "state")
    records = {
        "old-character": {
            "kind": "character",
            "name": "角色",
            "source": "upstream",
        },
        "old-outfit": {
            "kind": "outfit",
            "name": "旧服装",
            "source": "upstream",
        },
        "personal-outfit": {
            "kind": "outfit",
            "name": "个人服装",
            "source": "user",
        },
    }
    for template_id, body in records.items():
        store.put(
            "prompt_template",
            {
                "trigger": "",
                "tags": [],
                "description": "",
                "caption_en": [],
                "excluded_tags": [],
                "categories": [],
                "source_revision": "",
                "source_key": template_id,
                **body,
            },
            template_id,
        )
    approve_current_catalog(store)

    result = promote_catalog(store)

    assert result["removed_non_personal_outfits"] == 1
    assert result["inserted_curated_outfits"] == 50
    assert store.get("prompt_template", "old-character") is not None
    assert store.get("prompt_template", "old-outfit") is None
    assert store.get("prompt_template", "personal-outfit") is not None
    curated = store.get("prompt_template", "curated-outfit-01-classic-maid")
    assert curated["excluded_tags"] == ["maid headdress"]
    assert len(curated["caption_en"]) == 2
    assert source_url(curated) is None
    with store.connect() as db:
        markers = {
            row["id"]: row["op"] for row in db.execute("SELECT id, op FROM rag_template_dirty")
        }
    assert markers["old-outfit"] == "delete"
    assert markers["curated-outfit-01-classic-maid"] == "upsert"
    assert "personal-outfit" not in markers


def test_promotion_requires_current_full_approval(tmp_path):
    store = Store(tmp_path / "state")
    with pytest.raises(ValueError, match="尚未完成内容审批"):
        promote_catalog(store)

    catalog = approve_current_catalog(store)
    review = store.get("outfit_catalog_review", catalog.catalog_id)
    review["approved_recipe_ids"] = review["approved_recipe_ids"][:-1]
    store.put("outfit_catalog_review", review, catalog.catalog_id, replace=True)
    with pytest.raises(ValueError, match="没有覆盖全部"):
        promote_catalog(store)
