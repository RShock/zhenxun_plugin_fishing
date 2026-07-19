"""
杂项 handler — 签到、自动卖鱼、改名、皮肤、测试渲染、调试模式。
"""

import random
from datetime import datetime

from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..config import ConfigManager
from ..matchers import (
    auto_lock_matcher,
    auto_sell_matcher,
    debug_render_matcher,
    rename_matcher,
    skin_matcher,
    test_render_matcher,
    test_scene_render_matcher,
    weather_forecast_matcher,
)
from ..models import FishingUser
from ..render import (
    _get_all_skin_files,
    render_emoji_test,
    render_fishing_scene,
    render_weather_forecast,
)
from ..shop import change_skin, get_skin_list_image, rename_fishing_user
from ..utils import _ensure_user, _is_private_chat, _send_image, _send_text


@auto_sell_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    is_private = _is_private_chat(event)
    action = group[0] if group and group[0] else ""
    if not action:
        current = await FishingUser.get_auto_sell(user_id)
        rarity = await FishingUser.get_auto_sell_rarity(user_id)
        if current:
            await _send_text(
                matcher,
                f"自动卖鱼当前状态：开启（{rarity}及以下）\n使用【自动卖鱼 开启】【自动卖鱼 关闭】或【自动卖鱼 SR】设置稀有度",
                user_id,
                is_private=is_private,
            )
        else:
            await _send_text(
                matcher,
                "自动卖鱼当前状态：关闭\n使用【自动卖鱼 开启】【自动卖鱼 关闭】或【自动卖鱼 SR】设置稀有度",
                user_id,
                is_private=is_private,
            )
    elif action == "开启":
        await FishingUser.toggle_auto_sell(user_id, True)
        rarity = await FishingUser.get_auto_sell_rarity(user_id)
        await _send_text(
            matcher,
            f"已开启自动卖鱼！（{rarity}及以下）收杆后将自动出售对应稀有度未锁定的鱼。",
            user_id,
            is_private=is_private,
        )
    elif action == "关闭":
        await FishingUser.toggle_auto_sell(user_id, False)
        await _send_text(matcher, "已关闭自动卖鱼。", user_id, is_private=is_private)
    elif action in ("N", "R", "SR", "SSR", "UR", "UTR"):
        await FishingUser.set_auto_sell_rarity(user_id, action)
        await _send_text(
            matcher,
            f"已开启自动卖鱼！（{action}及以下）收杆后将自动出售{action}及以下稀有度未锁定的鱼。",
            user_id,
            is_private=is_private,
        )
    else:
        await _send_text(
            matcher,
            "请使用【自动卖鱼 开启】【自动卖鱼 关闭】或【自动卖鱼 SR】设置稀有度",
            user_id,
            is_private=is_private,
        )


@auto_lock_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    is_private = _is_private_chat(event)
    action = group[0] if group and group[0] else ""
    if not action:
        current = await FishingUser.get_auto_lock(user_id)
        pattern = await FishingUser.get_auto_lock_pattern(user_id)
        if current:
            await _send_text(
                matcher,
                f"自动锁鱼当前状态：开启（{pattern}）\n"
                "使用【自动锁鱼 开启】【自动锁鱼 关闭】或【自动锁鱼 S1**】设置通配符",
                user_id,
                is_private=is_private,
            )
        else:
            await _send_text(
                matcher,
                "自动锁鱼当前状态：关闭\n"
                "使用【自动锁鱼 开启】【自动锁鱼 关闭】或【自动锁鱼 S1**】设置通配符",
                user_id,
                is_private=is_private,
            )
    elif action == "开启":
        await FishingUser.toggle_auto_lock(user_id, True)
        pattern = await FishingUser.get_auto_lock_pattern(user_id)
        await _send_text(
            matcher,
            f"已开启自动锁鱼！（{pattern}）收杆后将自动锁定匹配的鱼。",
            user_id,
            is_private=is_private,
        )
    elif action == "关闭":
        await FishingUser.toggle_auto_lock(user_id, False)
        await _send_text(matcher, "已关闭自动锁鱼。", user_id, is_private=is_private)
    else:
        await FishingUser.set_auto_lock_pattern(user_id, action)
        await _send_text(
            matcher,
            f"已开启自动锁鱼！（{action}）收杆后将自动锁定匹配的鱼。",
            user_id,
            is_private=is_private,
        )


@rename_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    is_private = _is_private_chat(event)
    new_name = group[0] if group and group[0] else ""

    if not new_name:
        await _send_text(
            matcher,
            "请输入新名字！\n格式：钓鱼改名 新名字",
            user_id,
            is_private=is_private,
        )

    success, message = await rename_fishing_user(user_id, new_name)
    await _send_text(matcher, message, user_id, is_private=is_private)


@skin_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    skin_id = group[0] if group and group[0] else ""

    if not skin_id:
        image = await get_skin_list_image(user_id)
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
    else:
        success, message = await change_skin(user_id, skin_id)
        await _send_text(matcher, message, user_id, is_private=is_private)


@test_render_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    custom_text = group[0] if group and group[0] else ""
    try:
        image = await render_emoji_test(custom_text)
        msg = Message()
        msg += MessageSegment.image(image)
        await matcher.send(msg)
    except Exception as e:
        await matcher.finish(f"渲染测试失败: {e}")


@test_scene_render_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    is_private = _is_private_chat(event)
    location_id = (group[0] if group and group[0] else "").upper()
    location = ConfigManager.get_location(location_id)
    if not location:
        await _send_text(
            matcher,
            "未找到该场景，请使用数字ID或S1，例如：测试场景渲染 11",
            user_id,
            is_private=is_private,
        )
        return

    skin_ids = _get_all_skin_files()
    if not skin_ids:
        await _send_text(matcher, "没有可用角色皮肤。", user_id, is_private=is_private)
        return

    players = [
        {
            "user_id": f"test_scene_{i}",
            "nickname": f"测试{i + 1}",
            "skin_id": random.choice(skin_ids),
        }
        for i in range(8)
    ]
    players[0]["user_id"] = user_id
    players[0]["nickname"] = "你"

    try:
        image = await render_fishing_scene(
            location,
            players,
            user_id,
            hints=[f"测试场景渲染：{location.id} {location.name}"],
            now_time=datetime.now(),
        )
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
    except Exception as e:
        await _send_text(
            matcher, f"场景渲染测试失败: {e}", user_id, is_private=is_private
        )


@debug_render_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    from ..render.base import DEBUG_MODE, DEBUG_TEMP_DIR

    action = group[0] if group and group[0] else ""

    if action == "开启":
        import zhenxun.plugins.fishing.render.base as _base

        _base.DEBUG_MODE = True
        await matcher.finish(f"钓鱼调试模式已开启\n渲染文件将保存到: {DEBUG_TEMP_DIR}")
    elif action == "关闭":
        import zhenxun.plugins.fishing.render.base as _base

        _base.DEBUG_MODE = False
        await matcher.finish("钓鱼调试模式已关闭")
    else:
        status = "开启" if DEBUG_MODE else "关闭"
        msg = f"钓鱼调试模式当前状态：{status}"
        if DEBUG_MODE:
            msg += f"\n渲染文件保存路径: {DEBUG_TEMP_DIR}"
        msg += "\n使用【钓鱼调试 开启】或【钓鱼调试 关闭】切换"
        await matcher.finish(msg)


@weather_forecast_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    is_private = _is_private_chat(event)
    page = (group[0] if group and group[0] else "").strip()

    from ..cat_park import has_cat_park_ticket, is_cat_park_location
    from ..starry import has_starry_ship, is_starry_location
    from ..weather_service import ensure_weather_generated

    await ensure_weather_generated()
    locations = ConfigManager.get_locations()

    if page == "2":
        # 天气2：星空地图 11-20（仅已建设星空艇用户可见）
        has_ship = await has_starry_ship(user_id)
        visible_locations = [
            loc for loc in locations if is_starry_location(loc.id) and has_ship
        ]
    else:
        # 天气1（默认）：前 10 图 + 猫猫乐园 S1
        has_ticket = await has_cat_park_ticket(user_id)
        visible_locations = [
            loc
            for loc in locations
            if not is_starry_location(loc.id)
            and (not is_cat_park_location(loc.id) or has_ticket)
        ]

    image = await render_weather_forecast(user_id, visible_locations, page=page)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)
