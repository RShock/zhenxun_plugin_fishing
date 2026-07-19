def default_cat_gifts() -> dict:
    return {
        "gold": 0,
        "corn": 0,
        "bait_id": "",
        "bait_count": 0,
        "cat_frames": 0,
        "fish_gifts": [],
    }


def extract_fish_gifts(cat_gifts: dict | None) -> list[dict]:
    """从 cat_gifts 中提取送鱼列表，兼容新旧两种格式。

    新格式: cat_gifts["fish_gifts"] = [{"fish_name": ..., "fish_rarity": ...}, ...]
    旧格式: cat_gifts["fish_name"] / cat_gifts["fish_rarity"] (标量)
    """
    if not cat_gifts:
        return []
    if "fish_gifts" in cat_gifts:
        return cat_gifts["fish_gifts"]
    fish_name = cat_gifts.get("fish_name", "")
    fish_rarity = cat_gifts.get("fish_rarity", "")
    if fish_name:
        return [{"fish_name": fish_name, "fish_rarity": fish_rarity}]
    return []


def merge_cat_gifts(
    existing_cat_gifts: dict | None,
    new_cat_gifts: dict | None,
    cat_frame_pity: int,
) -> dict:
    existing_cat_gifts = existing_cat_gifts or default_cat_gifts()
    new_cat_gifts = new_cat_gifts or {}
    existing_fish_gifts = extract_fish_gifts(existing_cat_gifts)
    new_fish_gifts = extract_fish_gifts(new_cat_gifts)
    return {
        "gold": existing_cat_gifts.get("gold", 0) + new_cat_gifts.get("gold", 0),
        "corn": existing_cat_gifts.get("corn", 0) + new_cat_gifts.get("corn", 0),
        "bait_id": new_cat_gifts.get("bait_id", "") or existing_cat_gifts.get("bait_id", ""),
        "bait_count": existing_cat_gifts.get("bait_count", 0) + new_cat_gifts.get("bait_count", 0),
        "cat_frames": existing_cat_gifts.get("cat_frames", 0) + new_cat_gifts.get("cat_frames", 0),
        "fish_gifts": existing_fish_gifts + new_fish_gifts,
        "cat_frame_pity": cat_frame_pity,
    }


async def distribute_cat_gifts(
    user_id: str,
    location_id: str,  # 用于 numeric_id 生成
    fish_pool: list,   # location.fish_pool
    cat_gifts: dict | None,
) -> list[str]:
    """将猫礼物发放给玩家：金币/猫框/玉米/鱼饵/送鱼。

    返回提示消息列表。收杆和时光药水共用此函数。
    """
    from ..models import FishingUser

    if not cat_gifts:
        return []

    messages: list[str] = []

    if cat_gifts.get("gold", 0) > 0:
        await FishingUser.add_gold(user_id, cat_gifts["gold"])
        messages.append(f"🐱 猫送了{cat_gifts['gold']}金币")
    if cat_gifts.get("cat_frames", 0) > 0:
        await FishingUser.add_cat_frames(user_id, cat_gifts["cat_frames"])
        messages.append(f"🐱 猫送了{cat_gifts['cat_frames']}个猫框")
    if cat_gifts.get("corn", 0) > 0:
        await FishingUser.add_corn(user_id, cat_gifts["corn"])
        messages.append(f"🐱 猫送了{cat_gifts['corn']}个玉米")
    if cat_gifts.get("bait_count", 0) > 0 and cat_gifts.get("bait_id", ""):
        await FishingUser.add_item(
            user_id,
            cat_gifts["bait_id"],
            "bait",
            cat_gifts["bait_count"],
        )
        messages.append(f"🐱 猫送了{cat_gifts['bait_count']}个鱼饵")

    for gift in extract_fish_gifts(cat_gifts):
        gift_fish_name = gift.get("fish_name", "")
        gift_fish_rarity = gift.get("fish_rarity", "")
        if not gift_fish_name or not gift_fish_rarity:
            continue
        from ..config import ConfigManager, generate_fish_numeric_id
        from .result import add_fish_to_user

        gift_fish = ConfigManager.get_fish(gift_fish_name)
        if gift_fish:
            fish_index = 0
            if gift_fish.id in fish_pool:
                fish_index = fish_pool.index(gift_fish.id)
                if location_id.upper() != "S1":
                    fish_index += 1
            numeric_id = generate_fish_numeric_id(
                location_id, fish_index, gift_fish_rarity
            )
            cat_result = await add_fish_to_user(
                user_id,
                [(gift_fish.id, gift_fish_rarity, numeric_id, 1)],
                check_achievements=False,
            )
            messages.extend(cat_result["messages"])

    return messages


async def writeback_pity_counters(
    user,
    frame_pity: int,
    cat_frame_pity: int,
    utr_pity: int,
) -> None:
    """保底次数回写：更新 user 模型的三个保底计数器并保存。"""
    user.frame_pity_counter = frame_pity
    user.cat_frame_pity_counter = cat_frame_pity
    user.utr_pity_counter = utr_pity
    await user.save(
        update_fields=[
            "frame_pity_counter",
            "cat_frame_pity_counter",
            "utr_pity_counter",
        ]
    )
