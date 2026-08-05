"""
钓鱼核心指令 handler — 钓鱼/抛竿、收杆、钓鱼状态。
"""

from datetime import date
import re

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import Arg, RegexGroup

from ..config import ConfigManager
from ..core import (
    check_fishing_status,
    render_scene,
    start_fishing,
    stop_fishing,
    try_auto_fish_on_idle,
)
from ..core.actions import run_post_settlement
from ..matchers import fishing_matcher, status_matcher, stop_fishing_matcher
from ..models import FishingUser
from ..render import render_fishing_result, render_location_select
from ..services import get_or_create_user
from ..services.limit_service import (
    is_group_action_limit_enabled,
    is_last_status_view,
    is_last_stop_action,
    max_status_views,
    remaining_stop_actions,
)
from ..services.user_lock_service import with_user_lock
from ..utils import (
    _ensure_user,
    _get_nickname,
    _is_private_chat,
    _send_image,
    _send_text,
)


def normalize_location_reply(text: str) -> str | None:
    value = text.strip()
    if value.lower() == "s1":
        return "S1"
    if re.fullmatch(r"-?\d+", value):
        return value
    return None


def should_show_black_market_hint(
    black_market_count: int,
    smart_black_market_available_date: date | None,
    *,
    today: date | None = None,
) -> bool:
    """原黑商或智能黑商任一可用时，收竿结果应显示黑商提示。"""
    current_date = today or date.today()
    original_available = black_market_count < 1
    smart_available = (
        smart_black_market_available_date is None
        or smart_black_market_available_date <= current_date
    )
    return original_available or smart_available


@fishing_matcher.handle()
@with_user_lock("钓鱼/选择地图")
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

        # ── 防闲置：未在钓鱼但闲置超阈值，自动回到上次地图 ──
        auto_loc = await try_auto_fish_on_idle(user_id, nickname)
        if auto_loc:
            status = await FishingUser.get_status(user_id)
            if status:
                loc = ConfigManager.get_location(status["location_id"])
                if loc:
                    image = await render_scene(user_id, loc, group_id=group_id)
                    await _send_image(
                        matcher,
                        image,
                        f"你的角色自己去{auto_loc}钓鱼了，请输入收杆",
                        user_id,
                        is_private=is_private,
                    )
                    await matcher.finish()

        locations = ConfigManager.get_locations()
        image = await render_location_select(user_id, locations, user.rod_level)
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@fishing_matcher.got("location")
@with_user_lock("钓鱼/确认地图")
async def _(event: Event, matcher: Matcher, location=Arg("location")):
    user_id, nickname = await _ensure_user(event)
    group_id = str(event.group_id) if hasattr(event, "group_id") else None
    is_private = _is_private_chat(event)

    raw_location = location.extract_plain_text() if location else ""
    location_input = normalize_location_reply(raw_location)
    # A pending map choice must not consume ordinary conversation merely because
    # it contains a number. Invalid replies end this choice without side effects.
    if location_input is None:
        await matcher.finish()

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


@with_user_lock("收杆结算")
async def _settle_stop_fishing(event: Event, matcher: Matcher):
    user_id, nickname = await _ensure_user(event)
    is_private = _is_private_chat(event)
    group_id = str(event.group_id) if hasattr(event, "group_id") else None

    stop_count = await FishingUser.get_stop_count(user_id)
    status_count = await FishingUser.get_status_count(user_id)
    limit_enabled = await is_group_action_limit_enabled()

    if (
        not is_private
        and limit_enabled
        and remaining_stop_actions(stop_count, status_count) <= 0
    ):
        await matcher.finish()

    # ── 防闲置：收杆时若未在钓鱼且闲置超阈值，自动回到上次地图钓鱼再结算 ──
    auto_loc = None
    if not await FishingUser.is_fishing(user_id):
        auto_loc = await try_auto_fish_on_idle(user_id, nickname)

    try:
        render_data, buff_messages, _ = await stop_fishing(
            user_id,
            is_private=is_private,
            limit_enabled=limit_enabled,
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
        return None

    # 活跃群只是公告索引，必须在主结算成功后记录，且失败不能反向阻断玩家收杆。
    if group_id and not is_private:
        from zhenxun.services.log import logger

        from ..models import FishingActiveGroup

        try:
            await FishingActiveGroup.record_fishing(group_id, user_id, nickname)
        except Exception as e:
            logger.warning(
                f"记录钓鱼活跃群失败: user={user_id}, group={group_id}", e=e
            )

    hints = list(buff_messages)
    user = await FishingUser.get_user(user_id)
    black_market_count = await FishingUser.get_black_market_count(user_id)
    available_date = getattr(user, "smart_black_market_available_date", None)
    if should_show_black_market_hint(black_market_count, available_date):
        hints.insert(0, "今天黑商来了")
    if auto_loc:
        hints.insert(0, f"你的角色自己去{auto_loc}钓鱼了")
    if (
        not is_private
        and limit_enabled
        and is_last_stop_action(stop_count, status_count)
    ):
        hints.append("⚠️ 这是今天的最后一次收杆！")

    # 共用后半段结算：自动锁鱼、自动卖鱼、自动卖猫乐园材料
    hints = await run_post_settlement(user_id, is_private=is_private, messages=hints)

    return render_data, hints, is_private, user_id


@stop_fishing_matcher.handle()
async def _(event: Event, matcher: Matcher):
    settlement = await _settle_stop_fishing(event, matcher)
    if settlement is None:
        return
    render_data, hints, is_private, user_id = settlement

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
        bait=render_data.get("bait"),
        bait_remaining=render_data.get("bait_remaining"),
    )

    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@status_matcher.handle()
@with_user_lock("钓鱼状态结算")
async def _(event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    limit_enabled = await is_group_action_limit_enabled()
    user = await get_or_create_user(user_id, nickname)
    stop_count = await FishingUser.get_stop_count(user_id)
    status_count = await FishingUser.get_status_count(user_id)

    if not is_private and limit_enabled:
        _max_status = max_status_views(stop_count)
        if status_count >= _max_status:
            await matcher.finish()

    # ── 防闲置：未在钓鱼但闲置超阈值，自动回到上次地图 ──
    auto_loc = await try_auto_fish_on_idle(user_id, nickname)

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
        if auto_loc:
            side_text = f"你的角色自己去{auto_loc}钓鱼了" + (
                f"\n{side_text}" if side_text else ""
            )
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
