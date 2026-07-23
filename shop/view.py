"""
商店视图渲染 — 商店页、状态页、地点列表、皮肤列表。
"""

from ..config import ConfigManager
from ..models import FishingUser
from ..render import render_shop, render_user_status
from ..services import get_or_create_user


async def get_shop_image(user_id: str) -> bytes:
    user = await get_or_create_user(user_id)
    shop = ConfigManager.get_shop()
    rod_price = ConfigManager.get_rod_upgrade_price(user.base_rod_level)
    hook_price = ConfigManager.get_hook_upgrade_price(user.hook_level)
    from ..starry import has_starry_ship

    return await render_shop(
        shop.baits,
        [],
        user.rod_level,
        rod_price,
        user.hook_level,
        hook_price,
        user.display_slots,
        user.display_frames,
        user.cat_frames,
        user.upgraded_display_count,
        user.gold,
        user_id,
        starry_frames=int(user.starry_frames or 0),
        has_starry_ship=await has_starry_ship(user_id),
        star_frames=int(user.star_frames or 0),
        base_rod_level=user.base_rod_level,
    )


async def get_status_image(user_id: str) -> bytes:
    user = await get_or_create_user(user_id)
    bait = ConfigManager.get_bait(user.bait_id)

    rod_name = ConfigManager.get_rod_name(user.rod_level)
    bait_name = "不使用鱼饵"
    bait_speed_bonus = 0
    bait_remaining = 0
    if bait and user.bait_id != "0":
        bait_name = bait.name
        bait_speed_bonus = bait.speed_bonus
        bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
        bait_remaining = bait_item["count"] if bait_item else 0

    fishing_interval = ConfigManager.calculate_fishing_interval(
        user.hook_level, bait_speed_bonus
    )

    is_fishing = await FishingUser.is_fishing(user_id)
    fishing_location = None
    if is_fishing:
        status = await FishingUser.get_status(user_id)
        if status:
            loc = ConfigManager.get_location(status["location_id"])
            if loc:
                fishing_location = loc.name

    return await render_user_status(
        user_id,
        user.gold,
        rod_name,
        user.rod_level,
        user.hook_level,
        bait_name,
        fishing_interval,
        is_fishing,
        fishing_location,
        user.corn,
        bait_remaining,
        user.display_frames,
    )


async def get_location_list_image(user_id: str) -> bytes:
    from ..render import render_location_select

    user = await get_or_create_user(user_id)
    locations = ConfigManager.get_locations()
    return await render_location_select(locations, user.rod_level)


async def get_skin_list_image(user_id: str) -> bytes:
    user = await get_or_create_user(user_id)
    owned_skins = await FishingUser.get_owned_skins(user_id)
    from ..render import render_skin_list

    return await render_skin_list(owned_skins, user.skin_id)