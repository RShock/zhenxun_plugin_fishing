"""
钓鱼上下文数据类 — FishingContext, StepResult, 序列化/合并辅助函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import FishData, LocationData
from ..models import FishingUser


@dataclass
class FishingContext:
    """钓鱼结算所需的完整上下文。"""
    user: FishingUser
    user_id: str
    location: LocationData
    buffs: list
    bait: FishData | None
    bait_speed_bonus: int
    bait_remaining: int
    settle_start: datetime
    now: datetime
    buff_messages: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """主钓鱼模拟循环的完整结果。"""

    fish_caught: list[tuple[FishData, str, int]]
    bait_usage: dict[str, int]
    frame_pity: int
    bait: FishData | None
    bait_remaining: int
    cat_eaten_fish: list[tuple[FishData, str, int]]
    cat_gifts: dict
    utr_pity: int
    meteor_fish_numbers: list[int]


@dataclass
class StepResult:
    """单次钓鱼步进结算的结果。"""
    new_fish: list[tuple[FishData, str, int]]
    new_bait_consumed: int
    frame_pity: int
    cat_frame_pity: int
    bait: FishData | None
    bait_remaining: int
    utr_pity: int = 0
    bait_usage: dict[str, int] = field(default_factory=dict)
    buff_messages: list[str] = field(default_factory=list)
    cat_eaten_fish: list[tuple[FishData, str, int]] = field(default_factory=list)
    cat_gifts: dict = field(
        default_factory=lambda: {
            "gold": 0,
            "corn": 0,
            "bait_id": "",
            "bait_count": 0,
            "cat_frames": 0,
            "fish_name": "",
            "fish_rarity": "",
        }
    )


def deserialize_fish_caught(
    fish_caught_raw: list,
) -> list[tuple[FishData, str, int]]:
    """将 JSON 反序列化的鱼获列表转为 FishData 元组列表。"""
    from ..config import ConfigManager

    result: list[tuple[FishData, str, int]] = []
    for entry in fish_caught_raw:
        fish_id = entry["fish_id"]
        fish = ConfigManager.get_fish(fish_id)
        if not fish and fish_id == "展示木框":
            fish = FishData(id="展示木框", base_price=0)
        if not fish and fish_id.startswith("cat_park_material:"):
            fish = FishData(id=fish_id, base_price=0)
        if fish:
            result.append((fish, entry["rarity"], entry["count"]))
    return result


def serialize_fish_caught(
    fish_caught: list[tuple[FishData, str, int]],
) -> list[dict]:
    """将 FishData 元组列表序列化为 JSON 可存储的字典列表。"""
    return [
        {"fish_id": fish.id, "rarity": rarity, "count": count}
        for fish, rarity, count in fish_caught
    ]


def merge_fish(
    *fish_lists: list[tuple[FishData, str, int]],
    as_dict: bool = False,
) -> list[tuple[FishData, str, int]] | dict[tuple[str, str], tuple[FishData, str, int]]:
    """合并多个鱼获列表，按 (fish_id, rarity) 去重并累加数量。"""
    merged: dict[tuple[str, str], tuple[FishData, str, int]] = {}
    for fish_list in fish_lists:
        for fish, rarity, count in fish_list:
            key = (fish.id, rarity)
            if key in merged:
                f, r, c = merged[key]
                merged[key] = (f, r, c + count)
            else:
                merged[key] = (fish, rarity, count)
    return merged if as_dict else list(merged.values())
