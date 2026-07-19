"""
鱼获结果处理 — 保存到背包、成就检查、自动展示。
"""

from ..config import ConfigManager, FishData, LocationData, calculate_fish_price, generate_fish_numeric_id, DISPLAY_SLOT_COSTS
from ..models import FishingBuffCalculator, FishingUser
from ..services import auto_display_fish_with_msg, check_all_achievements

from .context import merge_fish


async def _calculate_entry_price(user_id: str, fish_data: FishData, rarity: str, effective_difficulty: int) -> int:
    from ..cat_park import CAT_PARK_FISH, cat_park_fish_price, get_user_cat_park_effect_values

    if fish_data.id in CAT_PARK_FISH:
        effects = await get_user_cat_park_effect_values(user_id)
        return cat_park_fish_price(fish_data, rarity, effects.get("price_bonus", 0))
    return calculate_fish_price(fish_data, rarity, effective_difficulty)


async def add_fish_to_user(
    user_id: str,
    fish_entries: list[tuple[str, str, str, int]],
    effective_difficulty: int = 0,
    check_achievements: bool = True,
    auto_display: bool = True,
) -> dict:
    """统一的鱼添加接口，处理UTR自动消耗、背包存储、图鉴标记、自动展示、成就检查。

    Args:
        user_id: 用户ID
        fish_entries: 鱼条目列表，每个元素为 (fish_name, rarity, numeric_id, count)
        effective_difficulty: 有效难度（用于计算鱼价值），默认0
        check_achievements: 是否检查成就，默认True
        auto_display: 是否自动放入展示栏，默认True

    Returns:
        dict: {
            "fish_coins": int,
            "achievement_coins": int,
            "messages": list[str],
            "achievement_messages": list[str],
            "displayable_fish": list[tuple[str, str, str]],
            "utr_consumed": list[str],
        }
    """
    fish_coins = 0
    achievement_coins = 0
    messages: list[str] = []
    achievement_messages: list[str] = []
    displayable_fish: list[tuple[str, str, str]] = []
    auto_display_fish_entries: list[tuple[str, str, str]] = []
    utr_consumed: list[str] = []

    for fish_name, rarity, numeric_id, count in fish_entries:
        fish_data = ConfigManager.get_fish(fish_name)
        if not fish_data:
            continue

        if rarity == "UTR":
            utr_collected = await FishingUser.is_collected(user_id, fish_name, "UTR")
            if not utr_collected:
                await FishingUser.mark_collected(user_id, fish_name, "UTR", 1)
                displayable_fish.append((fish_name, rarity, numeric_id))
                messages.append(f"🌈 {fish_name} UTR图鉴已解锁！（已自动消耗1条）")
                utr_consumed.append(fish_name)
                remaining = count - 1
                if remaining > 0:
                    await FishingUser.add_fish(user_id, fish_name, rarity, numeric_id, remaining)
                    await FishingUser.mark_collected(user_id, fish_name, rarity, remaining)
                    price = await _calculate_entry_price(user_id, fish_data, rarity, effective_difficulty)
                    fish_coins += price * remaining
                    messages.append(f"🎒 剩余{remaining}条{fish_name} UTR已放入背包")
                    auto_display_fish_entries.append((fish_name, rarity, numeric_id))
                continue
            await FishingUser.add_fish(user_id, fish_name, rarity, numeric_id, count)
            await FishingUser.mark_collected(user_id, fish_name, rarity, count)
            price = await _calculate_entry_price(user_id, fish_data, rarity, effective_difficulty)
            fish_coins += price * count
            displayable_fish.append((fish_name, rarity, numeric_id))
            auto_display_fish_entries.append((fish_name, rarity, numeric_id))
        else:
            await FishingUser.add_fish(user_id, fish_name, rarity, numeric_id, count)
            await FishingUser.mark_collected(user_id, fish_name, rarity, count)
            price = await _calculate_entry_price(user_id, fish_data, rarity, effective_difficulty)
            fish_coins += price * count
            displayable_fish.append((fish_name, rarity, numeric_id))
            auto_display_fish_entries.append((fish_name, rarity, numeric_id))

    if auto_display:
        for fish_name, rarity, numeric_id in auto_display_fish_entries:
            display_msg = await auto_display_fish_with_msg(user_id, fish_name, rarity, numeric_id)
            if display_msg:
                messages.append(f"🏆 自动展示: {display_msg}")

    if check_achievements and fish_entries:
        achievements = await check_all_achievements(user_id)
        if achievements["coins"] > 0:
            await FishingUser.add_gold(user_id, achievements["coins"])
        achievement_coins = achievements["coins"]
        achievement_messages = achievements["messages"]

    return {
        "fish_coins": fish_coins,
        "achievement_coins": achievement_coins,
        "messages": messages,
        "achievement_messages": achievement_messages,
        "displayable_fish": displayable_fish,
        "utr_consumed": utr_consumed,
    }


async def save_fish_to_backpack(
    user_id: str,
    location: LocationData,
    merged: dict[tuple[str, str], tuple[FishData, str, int]],
    effective_difficulty: int,
    buff_messages: list[str],
) -> tuple[int, list[tuple[str, str, str]], list[str]]:
    """将鱼获保存到用户背包，处理 UTR 自动消耗、展示木框、成就检查。"""
    frame_count = 0
    fish_entries: list[tuple[str, str, str, int]] = []
    cat_park_materials: dict[str, int] = {}

    from ..cat_park import CAT_PARK_MATERIAL_TYPE, add_cat_park_material

    for fish, rarity, count in merged.values():
        if fish.id.startswith(f"{CAT_PARK_MATERIAL_TYPE}:"):
            material_name = fish.id.split(":", 1)[1]
            cat_park_materials[material_name] = cat_park_materials.get(material_name, 0) + count
            continue
        if fish.id == "展示木框":
            frame_count += count
            continue
        fish_index = 0
        if fish.id in location.fish_pool:
            fish_index = location.fish_pool.index(fish.id)
            if location.id.upper() != "S1":
                fish_index += 1
        numeric_id = generate_fish_numeric_id(location.id, fish_index, rarity)
        fish_entries.append((fish.id, rarity, numeric_id, count))

    result = await add_fish_to_user(user_id, fish_entries, effective_difficulty)

    if cat_park_materials:
        for material_name, count in cat_park_materials.items():
            await add_cat_park_material(user_id, material_name, count)

    if frame_count > 0:
        await FishingUser.add_display_frames(user_id, frame_count)
        buff_messages.append(f"🖼️ 获得{frame_count}个展示木框！")

    buff_messages.extend(result["messages"])
    return result["fish_coins"], result["displayable_fish"], result["achievement_messages"]


async def check_and_apply_achievements(
    user_id: str, location: LocationData, merged: dict
) -> tuple[int, list[str]]:
    """检查并应用成就奖励。

    注意：成就检查已集成到 add_fish_to_user，此函数保留用于兼容。
    现在会检查所有场景的成就而非仅当前场景。
    """
    if not merged:
        return 0, []

    achievements = await check_all_achievements(user_id)
    if achievements["coins"] > 0:
        await FishingUser.add_gold(user_id, achievements["coins"])

    return achievements["coins"], achievements["messages"]


async def process_fish_results(
    user_id: str,
    user,
    location: LocationData,
    fish_caught: list[tuple[FishData, str, int]],
    buffs: list,
    bait_speed_bonus: int,
    now,
    frame_pity: int,
    utr_pity: int,
    buff_messages: list[str],
) -> tuple[int, list[str], list[tuple[FishData, str, int]], list[tuple[str, str, int]]]:
    """处理收杆后的鱼获：保存、成就、展示、保底提示。

    返回 (fish_coins, achievement_messages, visible_fish, materials)
    materials 为 [(material_name, rarity, count), ...]，供收杆页素材区渲染。
    """
    merged = merge_fish(fish_caught, as_dict=True)

    final_effects = FishingBuffCalculator.get_effects_at_time(
        buffs, now, user.rod_level, bait_speed_bonus, location.difficulty
    )
    effective_difficulty = final_effects["difficulty"]

    fish_coins, displayable_fish, achievement_messages = await save_fish_to_backpack(
        user_id, location, merged, effective_difficulty, buff_messages
    )

    user = await FishingUser.get_user(user_id)
    if user.display_slots < 10:
        next_slot = user.display_slots + 1
        frames_needed = DISPLAY_SLOT_COSTS.get(next_slot, next_slot - 3)
        if user.display_frames >= frames_needed:
            buff_messages.append("💡 展示木框充足，输入【增加展示栏位】可升级展示数量")

    user.frame_pity_counter = frame_pity
    user.utr_pity_counter = utr_pity
    await user.save(update_fields=["frame_pity_counter", "utr_pity_counter"])

    from ..cat_park import CAT_PARK_MATERIAL_TYPE

    visible_fish: list[tuple[FishData, str, int]] = []
    materials: list[tuple[str, str, int]] = []
    for fish, rarity, count in merged.values():
        if fish.id.startswith(f"{CAT_PARK_MATERIAL_TYPE}:"):
            material_name = fish.id.split(":", 1)[1]
            materials.append((material_name, rarity, count))
        else:
            visible_fish.append((fish, rarity, count))
    return fish_coins, achievement_messages, visible_fish, materials
