"""
FishingUser 内存变更层。

约定：
- apply_* 只修改传入的 user 实例，不读写数据库
- dirty: set[str] 记录需要 save 的字段名
- 调用方负责一次 await user.save(update_fields=list(dirty))
- 类方法包装：get_user → apply_* → save_dirty
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..config import DAILY_ACTION_LIMIT, normalize_fish_numeric_id

# 与 user.py 保持一致的空结构
_EMPTY_DAILY = {
    "stop": {"count": 0, "date": None},
    "sell": {"count": 0, "date": None},
    "nest": {"count": 0, "date": None},
    "gift": {"count": 0, "date": None},
    "status": {"count": 0, "date": None},
    "black_market": {"count": 0, "date": None},
}


def mark_dirty(dirty: set[str] | None, *fields: str) -> None:
    if dirty is None:
        return
    dirty.update(fields)


async def save_dirty(user, dirty: set[str] | None) -> None:
    """若有脏字段则单次 save。"""
    if not dirty:
        return
    await user.save(update_fields=list(dirty))


def _ensure_dict(data: Any) -> dict:
    if not data or not isinstance(data, dict):
        return {}
    return data


def _ensure_list(data: Any) -> list:
    if not data or not isinstance(data, list):
        return []
    return data


def _normalize_collection(collection: dict) -> tuple[dict, bool]:
    normalized: dict = {}
    changed = False
    for key, value in collection.items():
        if isinstance(value, dict):
            fish_name = key
            normalized.setdefault(fish_name, {})
            for rarity, count in value.items():
                normalized[fish_name][rarity] = normalized[fish_name].get(rarity, 0) + int(
                    count or 0
                )
            continue
        parts = str(key).split("|", 1)
        if len(parts) != 2:
            normalized[key] = value
            continue
        fish_name, rarity = parts
        normalized.setdefault(fish_name, {})
        normalized[fish_name][rarity] = normalized[fish_name].get(rarity, 0) + int(
            value or 0
        )
        changed = True
    return normalized, changed


def _get_daily_counter(user, counter_type: str) -> tuple[int, str | None]:
    counters = _ensure_dict(user.daily_counters)
    info = counters.get(counter_type, {"count": 0, "date": None})
    return info.get("count", 0), info.get("date")


def _set_daily_counter(
    user, counter_type: str, count: int, date_str: str | None, dirty: set[str] | None
) -> None:
    counters = _ensure_dict(user.daily_counters)
    counters[counter_type] = {"count": count, "date": date_str}
    user.daily_counters = dict(counters)
    mark_dirty(dirty, "daily_counters")


# ── 标量资源 ──────────────────────────────────────────────────────────────


def apply_add_gold(user, amount: int, dirty: set[str] | None = None) -> None:
    user.gold = int(user.gold or 0) + int(amount)
    mark_dirty(dirty, "gold")


def apply_reduce_gold(user, amount: int, dirty: set[str] | None = None) -> bool:
    if int(user.gold or 0) < amount:
        return False
    user.gold = int(user.gold or 0) - int(amount)
    mark_dirty(dirty, "gold")
    return True


def apply_add_corn(user, amount: int = 1, dirty: set[str] | None = None) -> None:
    user.corn = int(user.corn or 0) + int(amount)
    mark_dirty(dirty, "corn")


def apply_reduce_corn(user, amount: int = 1, dirty: set[str] | None = None) -> bool:
    if int(user.corn or 0) < amount:
        return False
    user.corn = int(user.corn or 0) - int(amount)
    mark_dirty(dirty, "corn")
    return True


def apply_add_display_frames(
    user, count: int = 1, dirty: set[str] | None = None
) -> None:
    user.display_frames = int(user.display_frames or 0) + int(count)
    mark_dirty(dirty, "display_frames")


def apply_reduce_display_frames(
    user, count: int = 1, dirty: set[str] | None = None
) -> bool:
    if int(user.display_frames or 0) < count:
        return False
    user.display_frames = int(user.display_frames or 0) - int(count)
    mark_dirty(dirty, "display_frames")
    return True


def apply_add_cat_frames(user, count: int = 1, dirty: set[str] | None = None) -> None:
    user.cat_frames = int(user.cat_frames or 0) + int(count)
    mark_dirty(dirty, "cat_frames")


def apply_reduce_cat_frames(
    user, count: int = 1, dirty: set[str] | None = None
) -> bool:
    if int(user.cat_frames or 0) < count:
        return False
    user.cat_frames = int(user.cat_frames or 0) - int(count)
    mark_dirty(dirty, "cat_frames")
    return True


def apply_writeback_pity(
    user,
    frame_pity: int,
    cat_frame_pity: int,
    utr_pity: int,
    dirty: set[str] | None = None,
) -> None:
    user.frame_pity_counter = int(frame_pity)
    user.cat_frame_pity_counter = int(cat_frame_pity)
    user.utr_pity_counter = int(utr_pity)
    mark_dirty(
        dirty, "frame_pity_counter", "cat_frame_pity_counter", "utr_pity_counter"
    )


def apply_set_bait_id(user, bait_id: str, dirty: set[str] | None = None) -> None:
    user.bait_id = str(bait_id)
    mark_dirty(dirty, "bait_id")


# ── 签到 / 每日计数 ──────────────────────────────────────────────────────


def apply_check_and_sign(
    user, dirty: set[str] | None = None
) -> tuple[bool, int, int]:
    """签到。返回 (是否新签到, 当前玉米数, 错过天数)。"""
    today = date.today()
    if user.last_sign_date == today:
        return False, 0, 0

    days_missed = 0
    if user.last_sign_date is not None:
        delta = (today - user.last_sign_date).days
        days_missed = max(0, delta - 1)

    user.last_sign_date = today
    user.corn = int(user.corn or 0) + 1
    mark_dirty(dirty, "last_sign_date", "corn")
    return True, user.corn, days_missed


def apply_increment_daily_counter(
    user,
    counter_type: str,
    max_count: int,
    dirty: set[str] | None = None,
) -> tuple[int, bool]:
    today_str = date.today().isoformat()
    current_count, current_date = _get_daily_counter(user, counter_type)
    if current_date != today_str:
        current_count = 0
    new_count = current_count + 1
    _set_daily_counter(user, counter_type, new_count, today_str, dirty)
    return new_count, new_count >= max_count


def apply_increment_stop_count(
    user, dirty: set[str] | None = None
) -> tuple[int, bool]:
    return apply_increment_daily_counter(user, "stop", DAILY_ACTION_LIMIT, dirty)


# ── 背包 / 图鉴 ──────────────────────────────────────────────────────────


def apply_add_fish(
    user,
    fish_name: str,
    rarity: str,
    numeric_id: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> None:
    backpack = _ensure_dict(user.backpack)
    numeric_id = normalize_fish_numeric_id(numeric_id)
    entry = backpack.get(numeric_id)
    if entry:
        entry["count"] = entry.get("count", 0) + count
    else:
        backpack[numeric_id] = {
            "fish_name": fish_name,
            "rarity": rarity,
            "count": count,
            "locked": False,
        }
    user.backpack = dict(backpack)
    mark_dirty(dirty, "backpack")


def apply_remove_fish_by_numeric_id(
    user,
    numeric_id: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> bool:
    backpack = _ensure_dict(user.backpack)
    normalized_id = normalize_fish_numeric_id(numeric_id)
    entry = backpack.get(normalized_id)
    if not entry or entry.get("count", 0) < count:
        return False
    entry["count"] -= count
    if entry["count"] <= 0:
        del backpack[normalized_id]
    user.backpack = dict(backpack)
    mark_dirty(dirty, "backpack")
    return True


def apply_mark_collected(
    user,
    fish_name: str,
    rarity: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> None:
    collection, _ = _normalize_collection(_ensure_dict(user.collection))
    fish_entry = collection.setdefault(fish_name, {})
    fish_entry[rarity] = fish_entry.get(rarity, 0) + count
    user.collection = collection
    mark_dirty(dirty, "collection")


def is_collected_on_user(user, fish_name: str, rarity: str) -> bool:
    collection, changed = _normalize_collection(_ensure_dict(user.collection))
    if changed:
        user.collection = collection
        # 规范化也算脏，但调用方未必传 dirty；尽量不静默丢
    return bool(collection.get(fish_name, {}).get(rarity, 0))


def ensure_collection_normalized(
    user, dirty: set[str] | None = None
) -> dict:
    collection, changed = _normalize_collection(_ensure_dict(user.collection))
    if changed:
        user.collection = collection
        mark_dirty(dirty, "collection")
    return collection


def get_collected_set_on_user(user, dirty: set[str] | None = None) -> set[tuple[str, str]]:
    collection = ensure_collection_normalized(user, dirty)
    result = set()
    for fish_name, rarities in collection.items():
        if not isinstance(rarities, dict):
            continue
        for rarity, count in rarities.items():
            if count:
                result.add((fish_name, rarity))
    return result


def apply_mark_achievement(
    user, achievement_key: str, dirty: set[str] | None = None
) -> bool:
    """标记成就完成。已完成返回 False。"""
    achievements = list(_ensure_list(user.achievements))
    if achievement_key in achievements:
        return False
    achievements.append(achievement_key)
    user.achievements = achievements
    mark_dirty(dirty, "achievements")
    return True


def is_achievement_completed_on_user(user, achievement_key: str) -> bool:
    return achievement_key in _ensure_list(user.achievements)


# ── 物品 ─────────────────────────────────────────────────────────────────


def apply_add_item(
    user,
    item_id: str,
    item_type: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> None:
    items = _ensure_dict(user.items)
    key = f"{item_id}|{item_type}"
    entry = items.get(key)
    if entry:
        entry["count"] = entry.get("count", 0) + count
    else:
        items[key] = {"item_type": item_type, "count": count}
    user.items = dict(items)
    mark_dirty(dirty, "items")


def apply_remove_item(
    user,
    item_id: str,
    item_type: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> bool:
    items = _ensure_dict(user.items)
    key = f"{item_id}|{item_type}"
    entry = items.get(key)
    if not entry or entry.get("count", 0) < count:
        return False
    entry["count"] -= count
    if entry["count"] <= 0:
        del items[key]
    user.items = dict(items)
    mark_dirty(dirty, "items")
    return True


def get_item_on_user(user, item_id: str, item_type: str) -> dict | None:
    items = _ensure_dict(user.items)
    key = f"{item_id}|{item_type}"
    entry = items.get(key)
    if not entry:
        return None
    return {
        "item_id": item_id,
        "item_type": entry.get("item_type", item_type),
        "count": entry.get("count", 0),
    }


def get_user_items_on_user(user) -> list[dict]:
    items = _ensure_dict(user.items)
    result = []
    for key, entry in items.items():
        parts = key.split("|", 1)
        if len(parts) == 2:
            result.append(
                {
                    "item_id": parts[0],
                    "item_type": entry.get("item_type", parts[1]),
                    "count": entry.get("count", 0),
                }
            )
    return result


# ── 展示栏 ───────────────────────────────────────────────────────────────


def get_user_displays_on_user(user) -> list[dict]:
    displays = _ensure_dict(user.displays)
    if not displays:
        return []
    result = []
    for slot_str, entry in displays.items():
        result.append(
            {
                "slot": int(slot_str),
                "fish_name": entry.get("fish_name", ""),
                "rarity": entry.get("rarity", "N"),
                "numeric_id": normalize_fish_numeric_id(entry.get("numeric_id", "")),
            }
        )
    result.sort(key=lambda d: d["slot"])
    return result


def apply_set_display(
    user,
    slot: int,
    fish_name: str,
    rarity: str,
    numeric_id: str,
    dirty: set[str] | None = None,
) -> dict:
    """设置展示栏；若栏位已有鱼则退回背包。"""
    displays = _ensure_dict(user.displays)
    numeric_id = normalize_fish_numeric_id(numeric_id)
    slot_str = str(slot)
    existing = displays.get(slot_str)
    if existing:
        apply_add_fish(
            user,
            existing.get("fish_name", ""),
            existing.get("rarity", "N"),
            existing.get("numeric_id", ""),
            1,
            dirty,
        )
    displays[slot_str] = {
        "fish_name": fish_name,
        "rarity": rarity,
        "numeric_id": numeric_id,
    }
    user.displays = dict(displays)
    mark_dirty(dirty, "displays")
    return user.displays[slot_str]


def apply_remove_display(
    user, slot: int, dirty: set[str] | None = None
) -> bool:
    displays = _ensure_dict(user.displays)
    slot_str = str(slot)
    if slot_str not in displays:
        return False
    del displays[slot_str]
    user.displays = dict(displays)
    mark_dirty(dirty, "displays")
    return True


# ── 流星鱼 ───────────────────────────────────────────────────────────────


def apply_add_starry_fish(
    user,
    fish_id: int | str,
    location_id: str = "",
    dirty: set[str] | None = None,
) -> dict:
    from ..core.starry_system import (
        EXHIBITION_LIMIT,
        EXHIBITION_MIN_SCORE,
        score_starry_fish,
    )

    user.starry_fish = list(_ensure_list(user.starry_fish))
    user.starry_exhibition = list(_ensure_list(user.starry_exhibition))
    scored = score_starry_fish(fish_id)
    record = {
        "id": scored.id_text,
        "location_id": str(location_id),
        "score": round(scored.raw_score, 6),
        "display_score": scored.display_score,
        "reward_pool": scored.reward_pool,
        "features": [feature.display_name for feature in scored.features],
    }
    if scored.display_score >= EXHIBITION_MIN_SCORE:
        user.starry_exhibition.append(record)
        user.starry_exhibition.sort(
            key=lambda item: (
                float(item.get("score", 0)),
                int(item.get("id", 0)),
            ),
            reverse=True,
        )
        overflow = user.starry_exhibition[EXHIBITION_LIMIT:]
        user.starry_exhibition = user.starry_exhibition[:EXHIBITION_LIMIT]
        user.starry_fish.extend(overflow)
    else:
        user.starry_fish.append(record)
    user.starry_score_accumulated = (
        float(user.starry_score_accumulated or 0) + scored.raw_score
    )
    mark_dirty(dirty, "starry_fish", "starry_exhibition", "starry_score_accumulated")
    return record


def apply_try_claim_miracle(user, dirty: set[str] | None = None) -> dict | None:
    from ..core.starry_system import (
        MIRACLE_TARGET,
        STAR_FRAMES_MAX,
        find_miracle_subset,
    )

    current_frames = int(user.star_frames or 0)
    if current_frames >= STAR_FRAMES_MAX:
        return None

    backpack = list(_ensure_list(user.starry_fish))
    if not backpack:
        return None

    ids = [int(item.get("id", 0)) for item in backpack]
    indices = find_miracle_subset(ids)
    if not indices:
        return None

    index_set = set(indices)
    subset_records = [backpack[i] for i in sorted(indices)]
    new_backpack = [item for i, item in enumerate(backpack) if i not in index_set]

    user.starry_fish = new_backpack
    user.star_frames = current_frames + 1
    subset_count = len(subset_records)
    mark_dirty(dirty, "starry_fish", "star_frames")

    return {
        "target": MIRACLE_TARGET,
        "subset_count": subset_count,
        "star_frames": user.star_frames,
        "star_frames_max": STAR_FRAMES_MAX,
        "hint": "流星鱼编号相加后，末七位为 7777777",
    }


def apply_try_claim_miracles(
    user, *, max_claims: int | None = None, dirty: set[str] | None = None
) -> list[dict]:
    from ..core.starry_system import STAR_FRAMES_MAX

    claims: list[dict] = []
    limit = max_claims if max_claims is not None else STAR_FRAMES_MAX
    for _ in range(max(0, int(limit))):
        info = apply_try_claim_miracle(user, dirty)
        if not info:
            break
        claims.append(info)
    return claims


# ── 钓鱼状态 ─────────────────────────────────────────────────────────────


def apply_start_fishing(
    user, location_id: str, dirty: set[str] | None = None
) -> dict:
    now_iso = datetime.now().isoformat()
    user.fishing_status = {
        "location_id": location_id,
        "start_time": now_iso,
        "last_settle_time": now_iso,
        "fish_caught": [],
        "bait_consumed": 0,
        "frame_pity": user.frame_pity_counter,
        "utr_pity": user.utr_pity_counter,
        "cat_frame_pity": user.cat_frame_pity_counter,
    }
    mark_dirty(dirty, "fishing_status")
    return user.fishing_status


def apply_update_fishing_status(
    user, status: dict | None, dirty: set[str] | None = None
) -> None:
    user.fishing_status = status
    mark_dirty(dirty, "fishing_status")


def apply_stop_fishing(user, dirty: set[str] | None = None) -> dict | None:
    status = user.fishing_status
    if status:
        user.fishing_status = None
        mark_dirty(dirty, "fishing_status")
    return status


# ── 鱼饵选择（读 items） ─────────────────────────────────────────────────


def select_best_bait_on_user(user) -> tuple[int, int]:
    """从用户背包中选择价格最高的鱼饵。返回 (bait_id, count)。"""
    from ..config import ConfigManager

    items = get_user_items_on_user(user)
    bait_items = [i for i in items if i["item_type"] == "bait" and i["count"] > 0]
    if not bait_items:
        return 0, 0

    best_bait = None
    best_price = -1
    for bi in bait_items:
        bait_data = ConfigManager.get_bait(bi["item_id"])
        if bait_data and bait_data.price > best_price:
            best_price = bait_data.price
            best_bait = bait_data

    if best_bait:
        bait_item = get_item_on_user(user, str(best_bait.id), "bait")
        return best_bait.id, bait_item["count"] if bait_item else 0
    return 0, 0


def apply_consume_bait_incremental(
    user,
    bait_usage: dict[str, int],
    buff_messages: list[str],
    dirty: set[str] | None = None,
) -> None:
    """渐增消耗鱼饵并更新 bait_id。"""
    from ..config import ConfigManager

    for bait_id_str, consumed in bait_usage.items():
        if consumed <= 0:
            continue
        apply_remove_item(user, bait_id_str, "bait", consumed, dirty)
        bait_data = ConfigManager.get_bait(bait_id_str)
        if bait_data:
            remaining_item = get_item_on_user(user, bait_id_str, "bait")
            remaining = remaining_item["count"] if remaining_item else 0
            buff_messages.append(
                f"🪱 使用了{consumed}个{bait_data.name}（剩余{remaining}个）"
            )

    best_bait_id, _ = select_best_bait_on_user(user)
    apply_set_bait_id(user, str(best_bait_id), dirty)
