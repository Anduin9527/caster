"""Deterministic Anima prompt compilation.

Semantic decisions happen before this module: RAG supplies evidence, the Agent
chooses tags/captions, and approval freezes the result.  This module only makes
that approved recipe reproducible.  It never calls a model and never invents a
tag or sentence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .anima_defaults import escape_template_tags, runtime_defaults

# Official Anima order:
# [quality/meta/year/safety] [count] [character] [series] [artist] [general]
# Outfit and composition are CASTER-owned subdivisions of general tags.
SECTION_ORDER = ("count", "character", "series", "artist", "outfit", "general", "composition")
_SCORE_TAG = re.compile(r"^score_[0-9]+$", re.I)
_WEIGHTED_GROUP = re.compile(r"^\(.+:[-+]?[0-9]+(?:\.[0-9]+)?\)$")


def _key(value: str) -> str:
    return re.sub(
        r"\s+", " ", value.replace(r"\(", "(").replace(r"\)", ")").replace("_", " ").casefold()
    ).strip()


def normalize_tag(value: str) -> tuple[str, list[dict[str, str]]]:
    """Apply only Anima-safe syntax normalization and report every change.

    Explicit attention groups are opaque.  Literal name qualifiers are escaped
    idempotently by ``escape_template_tags``.  Underscores become spaces except
    for score tags, matching the Anima model-card convention.
    """
    original = str(value or "").strip()
    if not original:
        return "", []
    if _WEIGHTED_GROUP.fullmatch(original):
        return original, []
    normalized = original if _SCORE_TAG.fullmatch(original) else original.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = escape_template_tags(normalized)
    lint = []
    if normalized != original:
        lint.append(
            {"code": "tag_normalized", "value": original, "message": "规范化为 " + normalized}
        )
    return normalized, lint


def _unique_tags(values: Iterable[str]) -> tuple[list[str], list[dict[str, str]]]:
    result: list[str] = []
    lint: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values:
        tag, findings = normalize_tag(raw)
        lint.extend(findings)
        if not tag:
            continue
        key = _key(tag)
        if key in seen:
            lint.append({"code": "duplicate_tag", "value": str(raw), "message": "重复标签已忽略"})
            continue
        seen.add(key)
        result.append(tag)
    return result, lint


def compile_anima_recipe(
    sections: Mapping[str, Iterable[str]],
    captions: Iterable[str] = (),
    excluded_tags: Iterable[str] = (),
    negative_extra: Iterable[str] = (),
    *,
    compiler_version: str = "2.0-anima-hybrid",
    prompt_settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile an exact, reviewable tag+caption recipe.

    Section membership is supplied by the caller's domain knowledge; this
    module never guesses that a string is a character, series or garment tag.
    Unknown section names are retained after the known sections in stable input
    order and explicitly linted.
    """
    configured = runtime_defaults(prompt_settings)
    fixed_positive, fixed_lint = _unique_tags(configured["fixed_positive"].split(","))
    artist_style, artist_lint = _unique_tags(configured["artist_style"].split(","))
    fixed_negative, fixed_negative_lint = _unique_tags(configured["fixed_negative"].split(","))

    ordered_names = list(SECTION_ORDER)
    ordered_names.extend(name for name in sections if name not in SECTION_ORDER)
    normalized_sections: dict[str, list[str]] = {}
    lint: list[dict[str, str]] = [*fixed_lint, *artist_lint, *fixed_negative_lint]
    # Runtime quality/meta defaults are first and participate in global dedupe,
    # but never become template sections.
    seen: set[str] = {_key(tag) for tag in fixed_positive}
    runtime_artist: list[str] = []
    for name in ordered_names:
        if name == "artist":
            for tag in artist_style:
                key = _key(tag)
                if key in seen:
                    lint.append(
                        {
                            "code": "duplicate_tag",
                            "value": tag,
                            "message": "运行时画师标签与前序标签重复，已忽略",
                        }
                    )
                    continue
                seen.add(key)
                runtime_artist.append(tag)
        tags, findings = _unique_tags(sections.get(name, ()))
        lint.extend(findings)
        if name not in SECTION_ORDER and tags:
            lint.append(
                {"code": "unknown_section", "value": name, "message": "未知分类按输入顺序保留"}
            )
        kept = []
        for tag in tags:
            key = _key(tag)
            if key in seen:
                lint.append(
                    {"code": "duplicate_tag", "value": tag, "message": "跨分类重复标签已忽略"}
                )
                continue
            seen.add(key)
            kept.append(tag)
        if kept:
            normalized_sections[name] = kept

    exclusions, exclusion_lint = _unique_tags(excluded_tags)
    lint.extend(exclusion_lint)
    overlap = [tag for tag in exclusions if _key(tag) in seen]
    if overlap:
        raise ValueError("Included and excluded prompt tags overlap: " + ", ".join(overlap))

    caption_values = []
    caption_seen: set[str] = set()
    for raw in captions:
        value = str(raw or "").strip()
        if not value or value.casefold() in caption_seen:
            continue
        caption_seen.add(value.casefold())
        caption_values.append(value)

    # Insert saved artist/style preferences in the official artist slot.  They
    # remain runtime settings and are not written into recipe.sections.
    positive_tags = list(fixed_positive)
    for name in ordered_names:
        if name == "artist":
            positive_tags.extend(runtime_artist)
        positive_tags.extend(normalized_sections.get(name, []))
    positive = ", ".join(positive_tags)
    if caption_values:
        positive += (". " if positive else "") + " ".join(caption_values)

    negative_additions, negative_lint = _unique_tags(
        [*fixed_negative, *negative_extra, *exclusions]
    )
    lint.extend(negative_lint)
    negative = ", ".join(negative_additions)
    recipe = {
        "sections": normalized_sections,
        "captions": caption_values,
        "excluded_tags": exclusions,
        "runtime_settings": {
            "fixed_positive": fixed_positive,
            "artist_style": runtime_artist,
            "fixed_negative": fixed_negative,
            "content_hash": configured["content_hash"],
        },
        "assembly_order": [
            "fixed_positive",
            "count",
            "character",
            "series",
            "artist_style",
            "artist",
            "outfit",
            "general",
            "composition",
            "captions",
        ],
        "lint": lint,
        "policy": "anima-tag-caption-v3-runtime-settings",
        # Tag category is supplied by the domain caller. Canonical vocabulary
        # validation is a separate RAG/catalog audit and is never inferred here.
        "classification_source": "caller_owned_sections",
        "canonical_validation": "external_evidence_required",
    }
    return {
        "positive": positive,
        "negative": negative,
        "compiler_version": compiler_version,
        # workflows.build must bind these strings byte-for-byte. Prompts without
        # this marker retain the pre-v2 compatibility behavior.
        "workflow_prompt_mode": "exact",
        "recipe": recipe,
    }
