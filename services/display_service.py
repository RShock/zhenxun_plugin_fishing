from zhenxun.services.log import logger

from ..config import ConfigManager, calculate_fish_price
from ..models import FishingUser


async def calculate_display_income(user_id: str) -> int:
    displays = await FishingUser.get_user_displays(user_id)
    user = await FishingUser.get_user(user_id)
    upgraded_count = user.upgraded_display_count if user else 0
    starry_count = int(getattr(user, "starry_frames", 0) or 0) if user else 0

    display_values = []
    for d in displays:
        fish_data = ConfigManager.get_fish_by_name(d["fish_name"])
        if fish_data:
            price = calculate_fish_price(fish_data, d["rarity"], 0)
            display_values.append(price)

    display_values.sort(reverse=True)

    total_income = 0
    for i, price in enumerate(display_values):
        if i < starry_count:
            # 星空展示框：最贵的鱼 4 倍展示收益
            total_income += price * 4
        elif i < upgraded_count:
            total_income += price * 3
        else:
            total_income += price * 2
    return total_income


async def auto_display_fish(
    user_id: str, fish_name: str, rarity: str, numeric_id: str
) -> bool:
    result = await auto_display_fish_with_msg(user_id, fish_name, rarity, numeric_id)
    return result is not None


async def auto_display_fish_with_msg(
    user_id: str, fish_name: str, rarity: str, numeric_id: str
) -> str | None:
    if fish_name in ("展示木框", "木框"):
        return None

    fish_data = ConfigManager.get_fish_by_name(fish_name)
    if not fish_data:
        return None

    new_value = calculate_fish_price(fish_data, rarity, 0) * 2

    user = await FishingUser.get_user(user_id)
    displays = await FishingUser.get_user_displays(user_id)

    displayed_keys = {(d["fish_name"], d["rarity"]) for d in displays}
    if (fish_name, rarity) in displayed_keys:
        return None

    used_slots = {d["slot"] for d in displays}
    for slot in range(1, user.display_slots + 1):
        if slot not in used_slots:
            success = await FishingUser.remove_fish_by_numeric_id(
                user_id, numeric_id, 1
            )
            if success:
                await FishingUser.set_display(
                    user_id, slot, fish_name, rarity, numeric_id
                )
                logger.info(
                    f"用户 {user_id} 自动展示 {fish_name}({rarity}) 到栏位{slot}"
                )
                return f"{fish_name}({rarity})被放在了栏位{slot}（每天获得展示收益）"
            return None

    min_value = float("inf")
    min_slot = None
    for d in displays:
        d_fish_data = ConfigManager.get_fish_by_name(d["fish_name"])
        d_value = (
            calculate_fish_price(d_fish_data, d["rarity"], 0) * 2 if d_fish_data else 0
        )
        if d_value < min_value:
            min_value = d_value
            min_slot = d["slot"]

    if min_slot is not None and new_value > min_value:
        success = await FishingUser.remove_fish_by_numeric_id(
            user_id, numeric_id, 1
        )
        if success:
            await FishingUser.set_display(
                user_id, min_slot, fish_name, rarity, numeric_id
            )
            logger.info(
                f"用户 {user_id} 自动替换展示框{min_slot}为 {fish_name}({rarity})"
            )
            return f"{fish_name}({rarity})替换了展示框{min_slot}（每天获得展示收益）"

    return None


async def auto_fill_new_display_slot(user_id: str, slot: int) -> str | None:
    fish_list = await FishingUser.get_user_fish(user_id)
    if not fish_list:
        return None

    displays = await FishingUser.get_user_displays(user_id)
    displayed_keys = {(d["fish_name"], d["rarity"]) for d in displays}

    best_fish = None
    best_value = -1
    best_numeric_id = None
    best_rarity = None
    for fish in fish_list:
        if fish["fish_name"] in ("展示木框", "木框"):
            continue
        if (fish["fish_name"], fish["rarity"]) in displayed_keys:
            continue
        fish_data = ConfigManager.get_fish_by_name(fish["fish_name"])
        if not fish_data:
            continue
        value = calculate_fish_price(fish_data, fish["rarity"], 0) * 2
        if value > best_value:
            best_value = value
            best_fish = fish
            best_numeric_id = fish["numeric_id"]
            best_rarity = fish["rarity"]

    if best_fish and best_numeric_id:
        success = await FishingUser.remove_fish_by_numeric_id(
            user_id, best_numeric_id, 1
        )
        if success:
            await FishingUser.set_display(
                user_id, slot, best_fish["fish_name"], best_rarity, best_numeric_id
            )
            logger.info(
                f"用户 {user_id} 自动填充新展示框{slot}为 {best_fish['fish_name']}({best_rarity})"
            )
            return f"{best_fish['fish_name']}({best_rarity})"

    return None
