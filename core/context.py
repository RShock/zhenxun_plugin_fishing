"""
钓鱼上下文数据类 — FishingContext, StepResult, 序列化/合并辅助函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..config import FishData, LocationData
from ..models import FishingUser, _make_naive


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

    fish_caught: list[tuple[FishData, str, int, datetime | None]]
    bait_usage: dict[str, int]
    frame_pity: int
    bait: FishData | None
    bait_remaining: int
    cat_eaten_fish: list[tuple[FishData, str, int, datetime | None]]
    cat_gifts: dict
    utr_pity: int
    meteor_fish_numbers: list[int]
    meteor_fish_records: list[tuple[int, datetime | None]]
    # 供时光药水的多阶段模拟完整继承鱼饵状态，避免第二阶段从数据库恢复库存。
    available_baits: dict[str, dict[str, Any]] = field(default_factory=dict)
    no_bait_mode: bool = False


@dataclass
class StepResult:
    """单次钓鱼步进结算的结果。"""
    new_fish: list[tuple[FishData, str, int, datetime | None]]
    new_bait_consumed: int
    frame_pity: int
    cat_frame_pity: int
    bait: FishData | None
    bait_remaining: int
    utr_pity: int = 0
    bait_usage: dict[str, int] = field(default_factory=dict)
    buff_messages: list[str] = field(default_factory=list)
    cat_eaten_fish: list[tuple[FishData, str, int, datetime | None]] = field(default_factory=list)
    cat_gifts: dict = field(
        default_factory=lambda: {
            "gold": 0,
            "corn": 0,
            "bait_id": "",
            "bait_count": 0,
            "bait_gifts": {},
            "cat_frames": 0,
            "fish_name": "",
            "fish_rarity": "",
        }
    )


def deserialize_fish_caught(
    fish_caught_raw: list,
) -> list[tuple[FishData, str, int, datetime | None]]:
    """将 JSON 反序列化的鱼获列表转为 FishData 元组列表。

    返回4元组 (fish, rarity, count, catch_time)。
    向后兼容：旧数据没有 catch_time 字段时返回 None，回档药水将 None
    视为"24小时前"（保留而非丢弃），避免升级后旧鱼获被误删。
    """
    from ..config import ConfigManager

    result: list[tuple[FishData, str, int, datetime | None]] = []
    for entry in fish_caught_raw:
        fish_id = entry["fish_id"]
        fish = ConfigManager.get_fish(fish_id)
        if not fish and fish_id in ("展示木框", "木框"):
            fish = FishData(id="木框", base_price=0)
        if not fish and fish_id.startswith("cat_park_material:"):
            fish = FishData(id=fish_id, base_price=0)
        if fish:
            catch_time: datetime | None = None
            raw_ct = entry.get("catch_time")
            if raw_ct:
                try:
                    catch_time = _make_naive(datetime.fromisoformat(raw_ct))
                except (ValueError, TypeError):
                    pass
            result.append((fish, entry["rarity"], entry["count"], catch_time))
    return result


def serialize_fish_caught(
    fish_caught: list[tuple[FishData, str, int, datetime | None]],
) -> list[dict]:
    """将 FishData 元组列表序列化为 JSON 可存储的字典列表。

    兼容3元组（无 catch_time）和4元组（有 catch_time）输入。
    """
    serialized: list[dict] = []
    for item in fish_caught:
        fish = item[0]
        rarity = item[1]
        count = item[2]
        catch_time = item[3] if len(item) > 3 else None
        entry: dict = {"fish_id": fish.id, "rarity": rarity, "count": count}
        if catch_time is not None:
            entry["catch_time"] = catch_time.isoformat()
        serialized.append(entry)
    return serialized


def deserialize_meteor_fish_records(
    status_dict: dict,
) -> list[tuple[int, datetime | None]]:
    """读取带捕获时间的流星鱼记录，并兼容旧编号数组。

    新状态以 ``meteor_fish_records`` 为权威来源；旧状态只有
    ``meteor_fish_numbers`` 时将捕获时间记为 None。回档药水在长会话中
    会保留这些无法判定时间的旧记录，优先避免玩家资产损失。
    """
    if "meteor_fish_records" not in status_dict:
        return [
            (int(number), None)
            for number in status_dict.get("meteor_fish_numbers", [])
        ]

    records: list[tuple[int, datetime | None]] = []
    for entry in status_dict.get("meteor_fish_records", []):
        if not isinstance(entry, dict) or "number" not in entry:
            continue
        catch_time: datetime | None = None
        raw_ct = entry.get("catch_time")
        if raw_ct:
            try:
                catch_time = _make_naive(datetime.fromisoformat(raw_ct))
            except (ValueError, TypeError):
                pass
        records.append((int(entry["number"]), catch_time))
    return records


def serialize_meteor_fish_records(
    records: list[tuple[int, datetime | None]],
) -> list[dict]:
    """将逐条流星鱼记录序列化为 JSON 可存储格式。"""
    serialized: list[dict] = []
    for number, catch_time in records:
        entry: dict = {"number": int(number)}
        if catch_time is not None:
            entry["catch_time"] = catch_time.isoformat()
        serialized.append(entry)
    return serialized


def merge_fish(
    *fish_lists: list[tuple],
    as_dict: bool = False,
) -> list[tuple[FishData, str, int, datetime | None]] | dict[tuple[str, str], tuple[FishData, str, int, datetime | None]]:
    """合并多个鱼获列表，按 (fish_id, rarity, catch_time) 去重并累加数量。

    合并键包含 catch_time，不同时间捕获的同种鱼不会合并，
    保留时间粒度供回档药水按24小时窗口精确筛选。
    兼容3元组和4元组输入。
    """
    merged: dict[tuple, tuple[FishData, str, int, datetime | None]] = {}
    for fish_list in fish_lists:
        for item in fish_list:
            fish = item[0]
            rarity = item[1]
            count = item[2]
            catch_time = item[3] if len(item) > 3 else None
            # 合并键包含 catch_time，避免不同时间的同种鱼被合并后回档整批错判
            key = (fish.id, rarity, catch_time)
            if key in merged:
                f, r, c, ct = merged[key]
                merged[key] = (f, r, c + count, ct)
            else:
                merged[key] = (fish, rarity, count, catch_time)
    return merged if as_dict else list(merged.values())


def normalize_time_potions(raw) -> list[str | None]:
    """将 time_potions_used 字段统一为时间戳字符串列表。

    向后兼容：
    - 旧数据为 int（如 3）→ 转为 [None, None, None]，回档时视为 24h 前使用（不退还）
    - 新数据为 list[str] → 原样返回
    - 空值 → []
    """
    if raw is None:
        return []
    if isinstance(raw, int):
        return [None] * raw
    if isinstance(raw, list):
        return raw
    return []
