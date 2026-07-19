"""
钓鱼核心指令 handler — 钓鱼/抛竿、收杆、钓鱼状态。
"""

import re

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import Arg, RegexGroup

from ..config import ConfigManager
from ..fishing import check_fishing_status, render_scene, start_fishing, stop_fishing
from ..core.actions import run_post_settlement
from ..matchers import fishing_matcher, status_matcher, stop_fishing_matcher
from ..models import FishingUser
from ..render import render_fishing_result, render_location_select
from ..services import get_or_create_user, get_user
from ..services.limit_service import (
    is_group_action_limit_enabled,
    is_last_status_view,
    is_last_stop_action,
    max_status_views,
    remaining_stop_actions,
)
from ..utils import _ensure_user, _get_nickname, _is_private_chat, _send_image, _send_text


@fishing_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    group_id = str(event.group_id) if hasattr(event, "group_id") else None
    is_private = _is_private_chat(event)

    location_input = group[0] if group and group[0] else ""
    if location_input:
        if location_input.lower() == "s1":
            location_input = "S1"
        image, success, hint = await start_fishing(
            user_id, location_input, nickname, group_id=group_id
        )
        await _send_image(matcher, image, hint, user_id, is_private=is_private)
        await matcher.finish()
    else:
        if await FishingUser.is_fishing(user_id):
            status = await FishingUser.get_status(user_id)
            if status:
                loc = ConfigManager.get_location(status["location_id"])
                if loc:
                    image = await render_scene(user_id, loc, group_id=group_id)
                    await _send_image(
                        matcher, image, user_id=user_id, is_private=is_private
                    )
                    await matcher.finish()

        user = await get_or_create_user(user_id, nickname)
        locations = ConfigManager.get_locations()
        image = await render_location_select(user_id, locations, user.rod_level)
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@fishing_matcher.got("location")
async def _(event: Event, matcher: Matcher, location=Arg("location")):
    user_id, nickname = await _ensure_user(event)
    group_id = str(event.group_id) if hasattr(event, "group_id") else None
    is_private = _is_private_chat(event)

    location_input = location.extract_plain_text().strip() if location else ""
    if not location_input:
        await matcher.finish()

    if location_input.lower() == "s1":
        location_input = "S1"
    else:
        match = re.search(r"\d+", location_input)
        if match:
            location_input = match.group()

    image, success, hint = await start_fishing(
        user_id, location_input, nickname, group_id=group_id
    )
    if success:
        await _send_image(matcher, image, hint, user_id, is_private=is_private)
    else:
        if hint:
            await _send_image(matcher, image, hint, user_id, is_private=is_private)
        else:
            await matcher.finish()


@stop_fishing_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, nickname = await _ensure_user(event)
    is_private = _is_private_chat(event)
    group_id = str(event.group_id) if hasattr(event, "group_id") else None

    stop_count = await FishingUser.get_stop_count(user_id)
    status_count = await FishingUser.get_status_count(user_id)

    if not is_private and remaining_stop_actions(stop_count, status_count) <= 0:
        await matcher.finish()

    # 记录活跃群（群聊收杆时记录）
    if group_id and not is_private:
        from ..models import FishingActiveGroup

        await FishingActiveGroup.record_fishing(group_id, user_id, nickname)

    try:
        render_data, buff_messages, _ = await stop_fishing(
            user_id, is_private=is_private
        )
    except Exception as e:
        # 事务已回滚，数据库保持收杆前状态；提示用户重试
        from zhenxun.services.log import logger

        logger.error(f"用户 {user_id} 收杆失败（数据库未修改）", e=e)
        await _send_text(
            matcher,
            "收杆失败，数据未变更，请稍后重试。",
            user_id,
            is_private=is_private,
        )
        return

    if render_data is None:
        await _send_text(matcher, "你还没有开始钓鱼！", user_id, is_private=is_private)

    hints = list(buff_messages)
    if not is_private and is_last_stop_action(stop_count, status_count):
        hints.append("⚠️ 这是今天的最后一次收杆！")

    # 共用后半段结算：自动锁鱼、自动卖鱼、自动卖猫乐园材料
    hints = await run_post_settlement(user_id, is_private=is_private, messages=hints)

    image = await render_fishing_result(
        render_data["user_id"],
        render_data["location"],
        render_data["duration_minutes"],
        render_data["merged_fish"],
        render_data["fish_coins"],
        render_data["achievement_messages"],
        sign_info=render_data["sign_info"],
        hints=hints if hints else None,
        cat_eaten_fish=render_data.get("cat_eaten_fish"),
        cat_gifts=render_data.get("cat_gifts"),
        buffs=render_data.get("buffs"),
        fishing_start_time=render_data.get("fishing_start_time"),
        now_time=render_data.get("now_time"),
        meteor_fish_numbers=render_data.get("meteor_fish_numbers"),
        cat_park_materials=render_data.get("cat_park_materials"),
        starry_score=render_data.get("starry_score"),
        miracle=render_data.get("miracle"),
            starry_rewards=render_data.get("starry_rewards"),
    )

    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@status_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    limit_enabled = is_group_action_limit_enabled()
    user = await get_or_create_user(user_id, nickname)
    stop_count = await FishingUser.get_stop_count(user_id)
    status_count = await FishingUser.get_status_count(user_id)

    if not is_private and limit_enabled:
        _max_status = max_status_views(stop_count)
        if status_count >= _max_status:
            await matcher.finish()

    try:
        if not await FishingUser.is_fishing(user_id):
            from ..shop import get_status_image

            image = await get_status_image(user_id)
            if not is_private and limit_enabled:
                await FishingUser.increment_status_count(user_id)
                side_text = (
                    "⚠️ 这是今天最后一次看钓鱼状态！"
                    if is_last_status_view(status_count, stop_count)
                    else ""
                )
            else:
                side_text = ""
            await _send_image(matcher, image, side_text, user_id, is_private=is_private)
            return

        image, step = await check_fishing_status(user_id)
        if image is None:
            from ..shop import get_status_image

            image = await get_status_image(user_id)

        if not is_private and limit_enabled:
            await FishingUser.increment_status_count(user_id)
            side_text = (
                "⚠️ 这是今天最后一次看钓鱼状态！"
                if is_last_status_view(status_count, stop_count)
                else ""
            )
        else:
            side_text = ""
        await _send_image(matcher, image, side_text, user_id, is_private=is_private)
    except Exception as e:
        from nonebot.log import logger

        logger.error(f"钓鱼状态渲染失败: {e}")
        rod_name = ConfigManager.get_rod_name(user.rod_level)
        bait = ConfigManager.get_bait(user.bait_id)
        bait_name = "不使用鱼饵" if not bait or user.bait_id == "0" else bait.name
        is_fishing = await FishingUser.is_fishing(user_id)
        location_text = ""
        if is_fishing:
            status = await FishingUser.get_status(user_id)
            if status:
                loc = ConfigManager.get_location(status["location_id"])
                if loc:
                    location_text = f"\n📍 正在 {loc.name} 钓鱼中"
        text = (
            f"🎣 钓鱼状态\n"
            f"💰 鱼币: {user.gold}\n"
            f"🎣 钓竿: {rod_name} (Lv.{user.rod_level})\n"
            f"🪝 鱼钩: Lv.{user.hook_level} (速度+{user.hook_level * ConfigManager.get_shop().hook_speed_bonus_per_level}%)\n"
            f"🪱 鱼饵: {bait_name}\n"
            f"🌽 香甜玉米: {user.corn}"
            f"{location_text}"
        )
        await _send_text(matcher, text, user_id)
