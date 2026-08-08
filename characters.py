"""角色定义与角色栏数据规范化。"""

from __future__ import annotations

from typing import Any

CHARACTER_SLOT_COUNT = 3

CHARACTER_DEFINITIONS: dict[str, dict[str, str | int]] = {
    "大肥鱼": {
        "character_id": "大肥鱼",
        "name": "大肥鱼",
        "level": 1,
        "rarity": "UTR",
    }
}


def build_character_data(
    character_id: str, level: int | None = None
) -> dict[str, str | int]:
    definition = CHARACTER_DEFINITIONS.get(character_id)
    if definition:
        character = dict(definition)
    else:
        character = {
            "character_id": character_id,
            "name": character_id,
            "level": 1,
            "rarity": "N",
        }
    if level is not None:
        character["level"] = max(1, int(level))
    return character


def normalize_character_data(value: Any) -> dict[str, str | int] | None:
    if isinstance(value, str):
        character_id = value.strip()
        return build_character_data(character_id) if character_id else None
    if not isinstance(value, dict):
        return None

    character_id = str(
        value.get("character_id") or value.get("name") or ""
    ).strip()
    if not character_id:
        return None

    character = build_character_data(character_id)
    try:
        character["level"] = max(
            1, int(value.get("level", character["level"]))
        )
    except (TypeError, ValueError):
        pass

    # 已登记角色的名称与稀有度由定义控制，避免旧数据或手工数据破坏卡片样式。
    if character_id not in CHARACTER_DEFINITIONS:
        character["name"] = (
            str(value.get("name") or character_id).strip() or character_id
        )
        character["rarity"] = (
            str(value.get("rarity") or "N").strip().upper() or "N"
        )
    return character


def normalize_character_slots(
    slots: Any,
) -> list[dict[str, str | int] | None]:
    if not isinstance(slots, list):
        return [None] * CHARACTER_SLOT_COUNT
    normalized = [
        normalize_character_data(slot) for slot in slots[:CHARACTER_SLOT_COUNT]
    ]
    normalized.extend([None] * (CHARACTER_SLOT_COUNT - len(normalized)))
    return normalized
