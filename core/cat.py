"""
猫天气系统 — 猫吃鱼礼物、送鱼逻辑。
"""

import random

from ..config import ConfigManager, FishData, LocationData, calculate_fish_price
from ..constants import CAT_FRAME_PITY_THRESHOLD


def process_cat_gift(
    fish: FishData,
    rarity: str,
    cat_gifts: dict,
    location: LocationData | None,
    collected_set: set[tuple[str, str]] | None,
    bait_id: str = "",
    lucky_double: bool = False,
) -> None:
    """猫吃掉鱼后生成随机礼物（金币/猫猫框/鱼饵/玉米/未收集鱼）。

    幸运药水激活时：两次独立结算取最优（猫框为最优结果），保底仅计算一次。
    送鱼礼物追加到 cat_gifts["fish_gifts"] 列表，支持多条鱼独立累积。
    """
    cat_frame_pity = cat_gifts.get("cat_frame_pity", 0)
    cat_frame_pity += 1  # 幸运药水也只增加一次

    roll = random.random()

    # 判定是否获得猫框：保底触发 或 roll 落在 0.30~0.45 区间
    got_cat_frame = cat_frame_pity >= CAT_FRAME_PITY_THRESHOLD or 0.30 <= roll < 0.45
    # 幸运药水：第二次独立结算，仅判定猫框（取最优）
    if lucky_double and not got_cat_frame:
        roll2 = random.random()
        got_cat_frame = 0.30 <= roll2 < 0.45

    if got_cat_frame:
        cat_gifts["cat_frames"] += 1
        cat_frame_pity = 0
    elif roll < 0.30:
        price = calculate_fish_price(fish, rarity, 0) // 2
        cat_gifts["gold"] += price
    elif roll < 0.60:
        effective_bait_id = bait_id
        if not effective_bait_id:
            shop = ConfigManager.get_shop()
            if shop.baits:
                effective_bait_id = str(shop.baits[0].id)
        if effective_bait_id and not cat_gifts.get("bait_id"):
            cat_gifts["bait_id"] = effective_bait_id
        cat_gifts["bait_count"] += 3
    elif roll < 0.9:
        cat_gifts["corn"] += 1
    else:
        if location:
            gift_fish_name, gift_fish_rarity = _find_cat_gift_fish(
                rarity, location, collected_set
            )
            if gift_fish_name:
                cat_gifts.setdefault("fish_gifts", []).append(
                    {"fish_name": gift_fish_name, "fish_rarity": gift_fish_rarity}
                )

    cat_gifts["cat_frame_pity"] = cat_frame_pity


def _find_cat_gift_fish(
    rarity: str,
    location: LocationData,
    collected_set: set[tuple[str, str]] | None,
) -> tuple[str, str]:
    """猫礼物送鱼：优先未收集，其次最贵。返回 (fish_name, fish_rarity)。"""
    uncollected = []
    for fish_id in location.fish_pool:
        fd = ConfigManager.get_fish(fish_id)
        if fd:
            if collected_set is not None and (fish_id, rarity) not in collected_set:
                uncollected.append(fd)
            elif collected_set is None:
                uncollected.append(fd)
    if uncollected:
        return uncollected[0].id, rarity
    best = None
    best_price = -1
    for fish_id in location.fish_pool:
        fd = ConfigManager.get_fish(fish_id)
        if fd:
            p = calculate_fish_price(fd, rarity, 0)
            if p > best_price:
                best_price = p
                best = fd
    if best:
        return best.id, rarity
    return "", ""
