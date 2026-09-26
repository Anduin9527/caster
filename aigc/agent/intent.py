"""Natural language to structured :class:`ProductionIntent`.

The first pass is deliberately deterministic and local: it picks a route, pulls
out action/expression/scene/composition, collects negations and detects
ordinals that refer to a live candidate set. A model may instead supply the
intent directly; either way the planner validates the result, so a missed
keyword degrades the plan and never invents parameters.
"""

import re
from typing import Any

from .contracts import ROUTE_SOURCE_STAGE, ROUTES, ProductionIntent, WorkbenchContext
from .retrieval import normalize, strip_negation

ROUTE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("local_expression", ("表情", "微笑", "生气", "哭", "expression", "smile", "frown", "blush")),
    ("anima_matte", ("抠图", "透明背景", "去背景", "白底", "matte", "transparent")),
    ("anima_outfit", ("换装", "换衣服", "换一套", "服装版本", "outfit change", "recloth")),
    ("qwen_pose", ("姿态", "姿势", "摆一个", "骨架", "pose studio", "change pose")),
]

# A background is a standalone asset, not a scene description: "背景是夜晚的街道"
# in a character request stays a scene on the free route.
BACKGROUND_ONLY = (
    "空场景",
    "只要背景",
    "背景图",
    "纯背景",
    "无人背景",
    "换背景",
    "scene only",
    "background only",
    "empty scene",
)

CANDIDATE_ORDINALS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
}
_ORDINAL = re.compile(r"第\s*([一二三四五六1-6])\s*个|第\s*([一二三四五六1-6])\s*张|([1-6])\s*号")

FIELD_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("expression", ("表情", "微笑", "笑着", "expression")),
    (
        "action",
        (
            "动作",
            "正在",
            "站着",
            "坐着",
            "跳",
            "跑",
            "挥",
            "伸手",
            "回头",
            "action",
            "poses",
            "sitting",
            "standing",
            "running",
            "jumping",
        ),
    ),
    (
        "scene",
        (
            "背景",
            "场景",
            "在",
            "房间里",
            "森林",
            "街道",
            "夜晚",
            "白天",
            "background",
            "scene",
            "room",
            "forest",
            "street",
        ),
    ),
    (
        "composition",
        (
            "构图",
            "全身",
            "半身",
            "特写",
            "俯视",
            "仰视",
            "侧面",
            "镜头",
            "composition",
            "close-up",
            "full body",
            "wide shot",
        ),
    ),
]


def extract_ordinal(text: str) -> int | None:
    """Map "第二个" to an index inside the current candidate set."""
    match = _ORDINAL.search(text or "")
    if not match:
        return None
    token = next((g for g in match.groups() if g), "")
    return CANDIDATE_ORDINALS.get(token)


def pick_route(text: str, context: WorkbenchContext) -> tuple[str, list[str], list[str]]:
    """Return the route, informational notes and blocking clarifications."""
    lowered = normalize(text)
    notes: list[str] = []
    clarify: list[str] = []
    for route, markers in ROUTE_RULES:
        if any(normalize(marker) in lowered for marker in markers):
            needed = {"local_expression": "pose", "qwen_pose": "pose", "anima_matte": "outfit"}.get(
                route
            )
            if needed and not context.selected(needed) and not context.selected("identity"):
                names = {"pose": "姿态图", "outfit": "服装图", "identity": "身份图"}
                clarify.append("该路线需要已选定的" + names[needed] + "，请先在工作台完成选图")
            return route, notes, clarify
    if any(normalize(marker) in lowered for marker in BACKGROUND_ONLY):
        return "anima_background", ["背景作为独立资产生成，画面里不会出现人物"], clarify
    if context.character_id and context.selected("identity"):
        return "anima_free", ["已按自由动作／交互路线处理，沿用当前选图与画布"], clarify
    if context.character_id:
        return "anima_text", ["当前没有选定参考图，先按文字立绘准备"], clarify
    return "anima_text", ["尚未选择角色，先准备文字立绘；角色确定后可改为参考图路线"], clarify


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?；;\n]", text or "") if s.strip()]


def collect_fields(text: str) -> dict[str, str]:
    """Split natural language into the four SceneSpec prose fields."""
    found: dict[str, list[str]] = {}
    for sentence in _sentences(text):
        for field, markers in FIELD_MARKERS:
            if any(normalize(marker) in normalize(sentence) for marker in markers):
                found.setdefault(field, []).append(sentence)
    return {field: " ".join(parts) for field, parts in found.items()}


def negations(text: str) -> list[str]:
    _, excluded = strip_negation(text)
    return [term for term in excluded if term]


def parse_intent(
    text: str, context: WorkbenchContext, override: dict[str, Any] | None = None
) -> tuple[ProductionIntent, list[str]]:
    route, notes, clarify = pick_route(text, context)
    fields = collect_fields(text)
    excluded = negations(text)
    # Availability follows the route's own source rule, not "any image exists".
    needs_source = ROUTES[route]["needs_source"]
    needed_stage = ROUTE_SOURCE_STAGE.get(route, ())
    source_available = bool(
        context.character_id and any(context.selected(stage) for stage in needed_stage)
    )
    if needs_source and not source_available:
        names = {"identity": "身份图", "outfit": "服装图", "pose": "姿态图"}
        wanted = "／".join(names[s] for s in needed_stage if s in names) or "参考图"
        clarify.append("该路线需要已选定的" + wanted + "，请先在工作台完成选图")
    reference_mode = "selected_image" if (needs_source and source_available) else "none"
    intent = ProductionIntent(
        route=route,
        action=fields.get("action", ""),
        expression=fields.get("expression", ""),
        scene=fields.get("scene", ""),
        composition=fields.get("composition", ""),
        count=1,
        reference_mode=reference_mode,
        canvas_preset=context.canvas_preset if route == "anima_text" else None,
        clarify=list(dict.fromkeys(clarify)),
    )
    if excluded:
        intent.change.extend("排除：" + term for term in excluded)
    for key, value in (override or {}).items():
        if value in (None, "", [], {}):
            continue
        setattr(intent, key, value)
    # Re-validate after the override: a model cannot invent an unknown route or
    # drop a required source.
    intent = ProductionIntent.model_validate(intent.model_dump())
    return intent, notes


# Routes whose result is driven by a saved state or an outfit rather than by the
# user's action/scene/composition prose.
PROSE_OPTIONAL_ROUTES = ("qwen_pose", "anima_outfit", "anima_matte")


def identity_conflicts(intent: ProductionIntent, character: dict[str, Any] | None) -> list[str]:
    """Structured checks that vector distance cannot guarantee."""
    if not character:
        return []
    fixed = " ".join(character.get("fixed_tags") or []).casefold()
    description = (character.get("description") or "").casefold()
    conflicts: list[str] = []
    if intent.outfit_id:
        outfits = {o["id"] for o in character.get("outfits") or []}
        if intent.outfit_id not in outfits:
            conflicts.append("角色没有这个服装版本：" + intent.outfit_id)
    wanted = normalize(" ".join(intent.visual_tags))
    if wanted:
        for outfit in character.get("outfits") or []:
            tags = normalize(" ".join(outfit.get("tags") or []))
            shared = [
                tag for tag in intent.visual_tags if normalize(tag) and normalize(tag) in tags
            ]
            if intent.outfit_id and outfit["id"] != intent.outfit_id and shared:
                conflicts.append("外观标签与目标服装之外的服装重叠：" + "、".join(shared[:5]))
    for note in intent.change:
        if note.startswith("排除："):
            term = normalize(note[3:])
            if term and (term in fixed or term in description):
                conflicts.append(
                    "要排除的「" + note[3:] + "」出现在角色固定外观里，无法靠提示词移除"
                )
    describes_action = bool(
        intent.action or intent.expression or intent.scene or intent.composition
    )
    if not describes_action and intent.route not in PROSE_OPTIONAL_ROUTES:
        conflicts.append("没有可执行的动作、场景或构图描述")
    return conflicts
