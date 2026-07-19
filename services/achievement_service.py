from typing import Any

from zhenxun.services.log import logger

from ..config import ConfigManager, calculate_fish_price
from ..models import FishingUser

RARITIES_UP_TO_UR = ["N", "R", "SR", "SSR", "UR"]
RARITIES_FULL = ["N", "R", "SR", "SSR", "UR", "UTR"]


async def _check_achievement(
    user_id: str,
    achievement_key: str,
    required_pairs: list[tuple[str, str]],
    description: str,
    collected_set: set,
    difficulty: int,
    extra_message: str = "",
    bonus_multiplier: float = 1.0,
) -> dict[str, Any]:
    result = {"coins": 0, "messages": []}
    if await FishingUser.is_achievement_completed(user_id, achievement_key):
        return result

    total_price = 0
    for fish_id, rarity in required_pairs:
        if (fish_id, rarity) not in collected_set:
            return result
        fish = ConfigManager.get_fish(fish_id)
        if fish:
            total_price += calculate_fish_price(fish, rarity, difficulty)

    await FishingUser.mark_achievement_completed(user_id, achievement_key)
    bonus = int(total_price * bonus_multiplier)
    result["coins"] = bonus
    msg = f"完成 {description}，获得 {bonus} 钓鱼币"
    if extra_message:
        msg += f"\n{extra_message}"
    result["messages"].append(msg)
    logger.info(f"用户 {user_id} 完成 {description}，获得 {bonus} 钓鱼币")
    return result


async def check_achievements_for_location(user_id: str, location) -> dict[str, Any]:
    result = {"coins": 0, "messages": []}
    fish_pool = location.fish_pool
    collected_set = await FishingUser.get_user_collected(user_id)

    all_fish_in_pool = []
    for fish_id in fish_pool:
        fish = ConfigManager.get_fish(fish_id)
        if fish:
            all_fish_in_pool.append(fish)

    if not all_fish_in_pool:
        return result

    checks: list[tuple[str, list[tuple[str, str]], str, str, float]] = []

    for rarity in RARITIES_UP_TO_UR:
        key = f"collect_rarity_{location.id}_{rarity}"
        pairs = [(fish.id, rarity) for fish in all_fish_in_pool]
        desc = f"{location.name} 收集全部{rarity}级鱼"
        checks.append((key, pairs, desc, "", 3.0))

    # UTR 稀有度全收集（5条鱼）
    key = f"collect_rarity_{location.id}_UTR"
    pairs = [(fish.id, "UTR") for fish in all_fish_in_pool]
    desc = f"{location.name} 收集全部UTR级鱼"
    checks.append((key, pairs, desc, "", 3.0))

    for fish in all_fish_in_pool:
        key = f"collect_fish_{location.id}_{fish.id}"
        pairs = [(fish.id, rarity) for rarity in RARITIES_UP_TO_UR]
        desc = f"{fish.id} 全稀有度收集"
        checks.append((key, pairs, desc, "", 3.0))

    key = f"collect_scene_{location.id}"
    pairs = [
        (fish.id, rarity) for fish in all_fish_in_pool for rarity in RARITIES_UP_TO_UR
    ]
    desc = f"{location.name} 场景全收集"
    try:
        from ..starry import is_starry_location

        is_starry = is_starry_location(location.id)
    except Exception:
        is_starry = False
    extra_msg = (
        f"✨ {location.name}的UTR稀有度已对你解锁！\n该图处于乱纪元时，将在保持乱纪元显示的同时启用迷途风效果、递进概率与 150 次 UTR 保底。"
        if is_starry
        else f"🌀 {location.name}的迷途风天气已对你解锁！"
    )
    checks.append((key, pairs, desc, extra_msg, 1.0))

    for fish in all_fish_in_pool:
        key = f"collect_fish_utr_{location.id}_{fish.id}"
        pairs = [(fish.id, rarity) for rarity in RARITIES_FULL]
        desc = f"{fish.id} 真全稀有度收集"
        checks.append((key, pairs, desc, "", 3.0))

    key = f"collect_scene_utr_{location.id}"
    pairs = [(fish.id, rarity) for fish in all_fish_in_pool for rarity in RARITIES_FULL]
    desc = f"{location.name} 场景真全收集"
    checks.append((key, pairs, desc, "", 1.0))

    for (
        achievement_key,
        required_pairs,
        description,
        extra_message,
        bonus_multiplier,
    ) in checks:
        r = await _check_achievement(
            user_id,
            achievement_key,
            required_pairs,
            description,
            collected_set,
            location.difficulty,
            extra_message=extra_message,
            bonus_multiplier=bonus_multiplier,
        )
        result["coins"] += r["coins"]
        result["messages"].extend(r["messages"])

    return result


async def check_all_achievements(user_id: str) -> dict[str, Any]:
    result = {"coins": 0, "messages": []}
    all_locations = ConfigManager.get_locations()
    for location in all_locations:
        location_achievements = await check_achievements_for_location(user_id, location)
        result["coins"] += location_achievements["coins"]
        result["messages"].extend(location_achievements["messages"])
    return result
