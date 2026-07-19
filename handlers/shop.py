"""
商店 & 升级 handler — 鱼店、升级钓竿/鱼钩、购买、展示栏、打窝、兑换。
"""

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..config import ConfigManager
from ..matchers import (
    build_starry_ship_matcher,
    buy_matcher,
    display_slot_matcher,
    exchange_matcher,
    nest_matcher,
    shop_matcher,
    upgrade_hook_matcher,
    upgrade_rod_matcher,
    use_item_matcher,
)
from ..render import render_exchange_result, render_upgrade_result
from ..services import get_or_create_user, get_user
from ..shop import (
    buy_item,
    do_nest,
    exchange_to_gold,
    get_shop_image,
    upgrade_display_slots,
)
from ..shop.item_dispatch import resolve_item_handler
from ..utils import (
    _ensure_user,
    _get_nickname,
    _is_private_chat,
    _send_image,
    _send_text,
)


@shop_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    image = await get_shop_image(user_id)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@upgrade_rod_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..shop import upgrade_rod

    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    user = await get_or_create_user(user_id, nickname)
    old_level = user.rod_level
    # 商店定价基于基础等级（排除猫猫乐园雕像额外加成）
    base_level = user.base_rod_level
    price = ConfigManager.get_rod_upgrade_price(base_level)
    success, message = await upgrade_rod(user_id)
    if success:
        user = await get_user(user_id)
        next_price = ConfigManager.get_rod_upgrade_price(base_level + 1)
        rod_name = ConfigManager.get_rod_name(old_level + 1)
        image = await render_upgrade_result(
            user_id,
            "钓竿升级",
            old_level,
            old_level + 1,
            rod_name,
            price,
            user.gold,
            next_price,
        )
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
    else:
        await _send_text(matcher, message, user_id, is_private=is_private)


@build_starry_ship_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..starry import build_starry_ship

    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    await get_or_create_user(user_id, nickname)
    success, message = await build_starry_ship(user_id, nickname=nickname)
    await _send_text(matcher, message, user_id, is_private=is_private)


@upgrade_hook_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..shop import upgrade_hook

    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    user = await get_or_create_user(user_id, nickname)
    old_level = user.hook_level
    price = ConfigManager.get_hook_upgrade_price(old_level)
    success, message = await upgrade_hook(user_id)
    if success:
        user = await get_user(user_id)
        next_price = ConfigManager.get_hook_upgrade_price(old_level + 1)
        image = await render_upgrade_result(
            user_id,
            "鱼钩升级",
            old_level,
            old_level + 1,
            "鱼钩",
            price,
            user.gold,
            next_price,
        )
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
    else:
        await _send_text(matcher, message, user_id, is_private=is_private)


@buy_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    name_or_id = group[0] if group and group[0] else ""
    count = int(group[1]) if group and len(group) > 1 and group[1] else 1

    if not name_or_id:
        await _send_text(
            matcher, "请指定要购买的物品名称或编号！", user_id, is_private=is_private
        )

    name_or_id = name_or_id.lstrip("#")

    success, message = await buy_item(user_id, name_or_id, count)
    await _send_text(matcher, message, user_id, is_private=is_private)


@display_slot_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    success, message = await upgrade_display_slots(user_id)
    await _send_text(matcher, message, user_id, is_private=is_private)


@nest_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    corn_count = 1
    if group and group[0]:
        try:
            corn_count = int(group[0])
            if corn_count < 1:
                corn_count = 1
        except ValueError:
            corn_count = 1

    success, message = await do_nest(user_id, corn_count, is_private=is_private)
    await _send_text(matcher, message, user_id, is_private=is_private)


@exchange_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    amount_str = group[0] if group and group[0] else ""

    if not amount_str:
        await _send_text(
            matcher,
            "请指定要兑换的钓鱼币数量！\n格式：钓鱼币兑换 数量",
            user_id,
            is_private=is_private,
        )

    try:
        amount = int(amount_str)
    except ValueError:
        await _send_text(matcher, "请输入有效的数字！", user_id, is_private=is_private)

    success, message, gold_received = await exchange_to_gold(user_id, amount)
    if success:
        user = await get_user(user_id)
        image = await render_exchange_result(amount, gold_received, user.gold)
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
    else:
        await _send_text(matcher, message, user_id, is_private=is_private)


@use_item_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    item_name = group[0].strip() if group and group[0] else ""
    rest = group[1].strip() if group and len(group) > 1 and group[1] else ""

    available = (
        "时光药水、回档药水、幸运药水、闪光药水、UTR自选券、香甜玉米、展示木框"
    )
    if not item_name:
        await _send_text(
            matcher,
            "请指定要使用的物品！\n"
            f"格式：钓鱼使用 物品名 [数量/参数]\n可用物品：{available}\n"
            "例：钓鱼使用 闪光药水 1\n例：钓鱼使用 UTR自选券 鱼名",
            user_id,
            is_private=is_private,
        )
        return

    count = 1
    arg = ""
    if rest:
        parts = rest.split()
        if len(parts) == 1 and parts[0].isdigit():
            count = max(1, int(parts[0]))
        elif parts and parts[-1].isdigit() and len(parts) > 1:
            # 兼容：钓鱼使用 UTR自选券 某某鱼 1
            count = max(1, int(parts[-1]))
            arg = " ".join(parts[:-1]).strip()
        else:
            arg = rest

    handler, is_image = resolve_item_handler(item_name)
    if handler is None:
        await _send_text(
            matcher,
            f"未知的物品：{item_name}\n可用物品：{available}",
            user_id,
            is_private=is_private,
        )
        return

    if is_image:
        success, message = await handler(
            user_id, count, is_private=is_private, arg=arg
        )
        if success:
            await _send_image(matcher, message, "", user_id, is_private=is_private)
            return
    else:
        success, message = await handler(
            user_id, count, is_private=is_private, arg=arg
        )

    await _send_text(matcher, message, user_id, is_private=is_private)
