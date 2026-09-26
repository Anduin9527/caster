"""Validate and promote the approved curated outfit catalog."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .prompt_settings import get_prompt_settings
from .schema import Strict

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "integrations" / "curated-outfits-v1.json"
CURATED_SOURCE = "caster://curated-outfits-v1"
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)]


class PreviewSpec(Strict):
    role: Literal["outfit"]
    canvas_preset: str = Field(pattern=r"^\d+x\d+$", max_length=32)
    identity_tags: list[Text] = Field(min_length=1, max_length=30)
    composition_tags: list[Text] = Field(min_length=1, max_length=30)
    negative_tags: list[Text] = Field(default_factory=list, max_length=100)


class OutfitRecipeDraft(Strict):
    id: Identifier
    name: Text
    description: Text
    caption_en: list[Text] = Field(min_length=2, max_length=2)
    category: Text
    tags: list[Text] = Field(min_length=1, max_length=50)
    excluded_tags: list[Text] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_tags(self):
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("Duplicate recipe tags: " + self.id)
        if set(self.tags) & set(self.excluded_tags):
            raise ValueError("Included and excluded tags overlap: " + self.id)
        if any(not sentence.endswith((".", "!", "?")) for sentence in self.caption_en):
            raise ValueError("English outfit captions must be complete sentences: " + self.id)
        return self


class OutfitABSample(Strict):
    recipe_id: Identifier
    seed: int = Field(ge=0, le=2**63 - 1)


class OutfitBaselineSnapshot(Strict):
    source_schema_version: Literal[1]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["reconstructed_unapproved"]
    prompt_policy: Literal["v1-flat-tag-preview"]


class OutfitCatalog(Strict):
    schema_version: Literal[2]
    catalog_id: Identifier
    baseline_snapshot: OutfitBaselineSnapshot
    status: Literal["draft"]
    character_query: Text
    character_match: Text
    preview: PreviewSpec
    ab_sample: list[OutfitABSample] = Field(min_length=5, max_length=5)
    recipes: list[OutfitRecipeDraft] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_recipes(self):
        if len({recipe.id for recipe in self.recipes}) != len(self.recipes):
            raise ValueError("Duplicate recipe IDs")
        sample_ids = [item.recipe_id for item in self.ab_sample]
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError("Duplicate A/B sample recipe IDs")
        known = {recipe.id for recipe in self.recipes}
        unknown = [recipe_id for recipe_id in sample_ids if recipe_id not in known]
        if unknown:
            raise ValueError("Unknown A/B sample recipe IDs: " + ", ".join(unknown))
        legacy = self.model_dump(exclude={"baseline_snapshot", "ab_sample"})
        legacy["schema_version"] = 1
        for recipe in legacy["recipes"]:
            recipe.pop("caption_en", None)
        canonical = json.dumps(
            legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        actual = hashlib.sha256(canonical).hexdigest()
        if actual != self.baseline_snapshot.content_hash:
            raise ValueError("Catalog v1 baseline snapshot no longer matches")
        return self


def load_catalog(path: Path = CATALOG_PATH) -> tuple[OutfitCatalog, str]:
    raw = path.read_bytes()
    catalog = OutfitCatalog.model_validate_json(raw)
    canonical = json.dumps(
        catalog.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return catalog, hashlib.sha256(canonical).hexdigest()


def promote_catalog(store, path: Path = CATALOG_PATH) -> dict:
    """Atomically replace non-personal outfit templates with this catalog.

    Character templates and user-owned templates are deliberately preserved.
    The new records carry no supported preview source, so the public library
    renders an explicit empty thumbnail until reviewed Miku images are attached
    in a later promotion.
    """
    from .agent.retrieval import TEMPLATE_REVISION_KEY
    from .agent.template_sync import mark_template_batch_in_transaction
    from .templates import PromptTemplate

    catalog, content_hash = load_catalog(path)
    templates = [
        PromptTemplate(
            id=recipe.id,
            kind="outfit",
            name=recipe.name,
            trigger="",
            tags=recipe.tags,
            description=recipe.description,
            caption_en=recipe.caption_en,
            excluded_tags=recipe.excluded_tags,
            categories=[recipe.category],
            source=CURATED_SOURCE,
            source_revision=content_hash,
            source_key=recipe.id,
        ).model_dump()
        for recipe in catalog.recipes
    ]

    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        settings = get_prompt_settings(store)
        review_row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?",
            ("outfit_catalog_review", catalog.catalog_id),
        ).fetchone()
        review = json.loads(review_row["body"]) if review_row else None
        if (
            not review
            or review.get("status") != "approved"
            or review.get("content_hash") != content_hash
            or review.get("prompt_settings_hash") != settings["content_hash"]
        ):
            raise ValueError("当前 catalog 与提示词设置尚未完成内容审批")
        if set(review.get("approved_recipe_ids") or []) != {
            recipe.id for recipe in catalog.recipes
        }:
            raise ValueError("catalog 审批没有覆盖全部服装配方")

        rows = db.execute(
            "SELECT id, body FROM records WHERE kind=?",
            ("prompt_template",),
        ).fetchall()
        records = [(str(row["id"]), json.loads(row["body"])) for row in rows]
        personal_ids = {
            template_id
            for template_id, body in records
            if body.get("kind") == "outfit" and body.get("source") == "user"
        }
        collisions = sorted(personal_ids & {template["id"] for template in templates})
        if collisions:
            raise ValueError("精选服装 ID 与个人模板冲突：" + ", ".join(collisions[:5]))
        removed_ids = [
            template_id
            for template_id, body in records
            if body.get("kind") == "outfit" and body.get("source") != "user"
        ]
        if removed_ids:
            db.executemany(
                "DELETE FROM records WHERE kind=? AND id=?",
                [("prompt_template", template_id) for template_id in removed_ids],
            )
        db.executemany(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            [
                ("prompt_template", template["id"], json.dumps(template, ensure_ascii=False))
                for template in templates
            ],
        )

        counter = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?",
            ("counter", TEMPLATE_REVISION_KEY),
        ).fetchone()
        revision = (int(json.loads(counter["body"])["value"]) if counter else 0) + 1
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            ("counter", TEMPLATE_REVISION_KEY, json.dumps({"value": revision})),
        )
        changes = {template_id: "delete" for template_id in removed_ids}
        changes.update({template["id"]: "upsert" for template in templates})
        mark_template_batch_in_transaction(db, changes, revision)

        promoted_at = time.time()
        record = {
            "catalog_id": catalog.catalog_id,
            "content_hash": content_hash,
            "prompt_settings_hash": settings["content_hash"],
            "promoted_at": promoted_at,
            "removed_non_personal_outfits": len(removed_ids),
            "inserted_curated_outfits": len(templates),
            "preserved_personal_outfits": len(personal_ids),
            "template_revision": revision,
            "preview_status": "empty",
        }
        db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            (
                "outfit_catalog_promotion",
                catalog.catalog_id,
                json.dumps(record, ensure_ascii=False),
            ),
        )
    return record
