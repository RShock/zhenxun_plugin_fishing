"""
卖鱼系统 — sell_fish, sell_bait。
"""

from zhenxun.services.log import logger

from ..config import (
    DAILY_SELL_LIMIT,
    RARITY_INDEX,
    ConfigManager,
    calculate_fish_price,
)
from ..models import FishingUser
from ..services import get_or_create_user
from .selection import FishSelection, parse_fish_selection

_BAIT_SELL_RATIO = 1.0


async def sell_fish(
    user_id: str,
    fish_input: str | None = None,
    is_private: bool = False,
    exclude_utr: bool = False,
) -> tuple[bool, str]:
    if not is_private:
        sell_count = await FishingUser.get_sell_count(user_id)
        if sell_count >= DAILY_SELL_LIMIT:
            return False, f"今日卖鱼次数已用完（每日{DAILY_SELL_LIMIT}次）"

    if not fish_input:
        return False, "格式：卖鱼 SR（及以下）/ 卖鱼 **3（仅该稀有度）/ 卖鱼 鱼ID"

    selection = parse_fish_selection(fish_input)

    if selection.is_empty():
        return False, "格式：卖鱼 SR（及以下）/ 卖鱼 **3（仅该稀有度）/ 卖鱼 鱼ID"

    fish_list = await _get_sellable_fish(user_id, selection, exclude_utr=exclude_utr)

    if not fish_list:
        return False, "没有可卖的鱼（锁定的鱼不会被出售）"

    total_coins, sold_details = await _calculate_sell_total(user_id, fish_list)

    await FishingUser.delete_fish_entries(user_id, fish_list)
    await FishingUser.add_gold(user_id, total_coins)
    if not is_private:
        await FishingUser.increment_sell_count(user_id)

    detail_str = "\n".join(sold_details[:6])
    if len(sold_details) > 6:
        detail_str += f"\n...共{len(sold_details)}种"
    user = await get_or_create_user(user_id)
    logger.info(f"用户 {user_id} 卖出鱼，获得 {total_coins} 钓鱼币")

    rod_upgrade_hint = ""
    if user.rod_level < 20:
        next_rod_price = ConfigManager.get_rod_upgrade_price(user.base_rod_level)
        rod_diff = next_rod_price - user.gold
        if rod_diff > 0:
            rod_upgrade_hint = f"\n🎣 距下一级钓竿还差 {rod_diff} 钓鱼币"

    return (
        True,
        f"出售成功！获得 {total_coins} 钓鱼币\n{detail_str}\n💰 当前金币：{user.gold}{rod_upgrade_hint}",
    )


async def _get_sellable_fish(
    user_id: str, selection: FishSelection, exclude_utr: bool = False
) -> list[dict]:
    if selection.select_all:
        all_fish = await FishingUser.get_user_fish(user_id)
        fish_list = [f for f in all_fish if not f.get("locked", False)]
        if exclude_utr:
            fish_list = [f for f in fish_list if f.get("rarity", "").upper() != "UTR"]
        return fish_list

    fish_list: list[dict] = []
    sellable_rarities: set[str] = set()
    for r in selection.rarity_letters:
        threshold = RARITY_INDEX.get(r, 0)
        for rarity, idx in RARITY_INDEX.items():
            if idx <= threshold:
                sellable_rarities.add(rarity)
    for r in selection.rarity_precise:
        sellable_rarities.add(r)

    if sellable_rarities:
        rarity_fish = await FishingUser.filter_fish(
            user_id, rarity_in=list(sellable_rarities), locked=False
        )
        fish_list.extend(rarity_fish)

    seen_ids = {f["numeric_id"] for f in fish_list}
    for nid in selection.numeric_ids:
        id_fish = await FishingUser.filter_fish(user_id, locked=False, numeric_id=nid)
        for f in id_fish:
            if f["numeric_id"] not in seen_ids:
                fish_list.append(f)
                seen_ids.add(f["numeric_id"])

    return fish_list


async def _calculate_sell_total(
    user_id: str, fish_list: list[dict]
) -> tuple[int, list[str]]:
    from ..cat_park import (
        CAT_PARK_FISH,
        cat_park_fish_price,
        get_user_cat_park_effect_values,
    )

    cat_park_effects = None
    total_coins = 0
    sold_details = []
    for fish in fish_list:
        fish_data = ConfigManager.get_fish_by_name(fish["fish_name"])
        if fish_data:
            if fish_data.id in CAT_PARK_FISH:
                if cat_park_effects is None:
                    cat_park_effects = await get_user_cat_park_effect_values(user_id)
                price = cat_park_fish_price(
                    fish_data, fish["rarity"], cat_park_effects.get("price_bonus", 0)
                )
            else:
                price = calculate_fish_price(fish_data, fish["rarity"], 0)
            coins = price * fish["count"]
            total_coins += coins
            sold_details.append(
                f"{fish['fish_name']}({fish['rarity']})x{fish['count']}={coins}币"
            )
    return total_coins, sold_details


async def _get_bait_inventory_hint(user_id: str) -> str:
    """获取用户背包中鱼饵列表的提示文本，格式：ID:名称x数量。"""
    items = await FishingUser.get_user_items(user_id)
    bait_items = [i for i in items if i["item_type"] == "bait" and i["count"] > 0]
    if not bait_items:
        return "背包中没有鱼饵"
    parts = []
    for bi in bait_items:
        bait_data = ConfigManager.get_bait(bi["item_id"])
        if bait_data:
            parts.append(f"{bait_data.id}:{bait_data.name}x{bi['count']}")
    if not parts:
        return "背包中没有鱼饵"
    return "背包鱼饵：" + "、".join(parts)


async def sell_bait(user_id: str, bait_input: str) -> tuple[bool, str]:
    """卖出用户所有指定的鱼饵，按购买价的50%回收。"""
    if not bait_input:
        hint = await _get_bait_inventory_hint(user_id)
        return False, f"格式：卖出鱼饵 鱼饵ID/名称\n{hint}"

    bait = ConfigManager.get_bait(bait_input)
    if not bait:
        hint = await _get_bait_inventory_hint(user_id)
        return False, f"未找到鱼饵：{bait_input}\n{hint}"

    bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
    if not bait_item or bait_item["count"] <= 0:
        hint = await _get_bait_inventory_hint(user_id)
        return False, f"你没有{bait.name}可以出售\n{hint}"

    count = bait_item["count"]
    sell_price = max(1, int(bait.price * _BAIT_SELL_RATIO))
    total_coins = sell_price * count

    await FishingUser.remove_item(user_id, str(bait.id), "bait", count)
    await FishingUser.add_gold(user_id, total_coins)

    user = await FishingUser.get_user(user_id)
    if user.preferred_bait_id == str(bait.id):
        user.preferred_bait_id = "0"
        await user.save(update_fields=["preferred_bait_id"])

    if user.bait_id == str(bait.id):
        best_bait_id, _ = await select_best_bait_after_sell(user_id)
        user.bait_id = str(best_bait_id)
        await user.save(update_fields=["bait_id"])

    hint = await _get_bait_inventory_hint(user_id)
    logger.info(f"用户 {user_id} 卖出 {count} 个{bait.name}，获得 {total_coins} 钓鱼币")
    msg = f"出售{count}个{bait.name}，获得 {total_coins} 钓鱼币\n💰 当前金币：{user.gold}\n{hint}"
    return True, msg


async def select_best_bait_after_sell(user_id: str) -> tuple[int, int]:
    from ..core.bait import select_best_bait

    return await select_best_bait(user_id)


