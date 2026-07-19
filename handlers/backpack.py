"""
背包 & 图鉴 handler — 背包、卖鱼、锁鱼、解锁、赠送、图鉴。
"""

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from zhenxun.services.log import logger

from ..backpack import (
    extract_market_exchange_input,
    black_market_exchange,
    gift_fish,
    get_backpack_image,
    get_collection_image,
    get_starry_exhibition_image,
    is_likely_misfire,
    lock_fish,
    render_white_market_records,
    sell_bait,
    sell_fish,
    unlock_fish,
    white_market_exchange,
)
from ..core.bait import set_preferred_bait
from ..matchers import (
    backpack_matcher,
    black_market_matcher,
    collection_matcher,
    gift_fish_matcher,
    lock_fish_matcher,
    sell_bait_matcher,
    sell_fish_matcher,
    set_bait_matcher,
    starry_exhibition_matcher,
    unlock_fish_matcher,
    white_market_exchange_matcher,
    white_market_matcher,
)
from ..utils import _ensure_user, _get_at_list, _is_private_chat, _send_image, _send_text


LOG_COMMAND = "钓鱼黑白商"


def _market_exchange_input_from_event(event: Event) -> str:
    return extract_market_exchange_input(event.get_plaintext())


def _log_silent_market_command(user_id: str, command: str, raw_text: str):
    logger.info(
        f"{command} 前缀命中但参数不像交换指令，已静默: {raw_text}",
        LOG_COMMAND,
        session=user_id,
    )


@backpack_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    image = await get_backpack_image(user_id)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@sell_fish_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    fish_input = group[0] if group and group[0] else "全部"
    exclude_utr = not (group and group[0])
    success, message = await sell_fish(user_id, fish_input, is_private=is_private, exclude_utr=exclude_utr)
    await _send_text(matcher, message, user_id, is_private=is_private)


@lock_fish_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    fish_id = group[0] if group and group[0] else ""
    if not fish_id:
        await _send_text(
            matcher,
            "格式：锁鱼 鱼ID / 锁鱼 SR / 锁鱼 **3 / 锁鱼 S1** / 锁鱼 全部\n批量：锁鱼 111,112（逗号/分号/空格分隔）",
            user_id,
            is_private=is_private,
        )
        return
    if is_likely_misfire(fish_id):
        return
    success, message = await lock_fish(user_id, fish_id)
    await _send_text(matcher, message, user_id, is_private=is_private)


@unlock_fish_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    fish_id = group[0] if group and group[0] else ""
    if not fish_id:
        await _send_text(
            matcher,
            "格式：解锁 鱼ID / 解锁 SR / 解锁 **3 / 解锁 S1** / 解锁 全部\n批量：解锁 111,112（逗号/分号/空格分隔）",
            user_id,
            is_private=is_private,
        )
        return
    if is_likely_misfire(fish_id):
        return
    success, message = await unlock_fish(user_id, fish_id)
    await _send_text(matcher, message, user_id, is_private=is_private)


@gift_fish_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if _is_private_chat(event):
        await matcher.finish("请在群内送鱼！")

    user_id, _ = await _ensure_user(event)
    fish_id = group[0] if group and group[0] else ""

    gift_usage = "格式：赠送/送鱼 鱼ID @某人\n@需要通过长按对方头像（手机端），或输入@后选择指定人（电脑端）来生效，直接打字@名字无效。"
    if not fish_id:
        await _send_text(matcher, gift_usage, user_id)

    at_list = _get_at_list(event)

    if not at_list:
        await _send_text(matcher, f"请@要赠送的人！{gift_usage}", user_id)

    target_id = str(at_list[0])
    success, message = await gift_fish(user_id, target_id, fish_id)
    await _send_text(matcher, message, user_id)


@black_market_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    raw_text = event.get_plaintext()
    exchange_input = _market_exchange_input_from_event(event)
    success, message, should_reply = await black_market_exchange(user_id, exchange_input)
    if not should_reply:
        _log_silent_market_command(user_id, "黑商", raw_text)
        return
    await _send_text(matcher, message, user_id, is_private=is_private)


@white_market_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    image = await render_white_market_records(user_id)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@white_market_exchange_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    raw_text = event.get_plaintext()
    exchange_input = _market_exchange_input_from_event(event)
    success, message, should_reply = await white_market_exchange(user_id, exchange_input)
    if not should_reply:
        _log_silent_market_command(user_id, "白商", raw_text)
        return
    await _send_text(matcher, message, user_id, is_private=is_private)


@collection_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    page = int(group[0]) if group and group[0] else 1
    if page == 2:
        from ..starry import has_starry_ship

        if not await has_starry_ship(user_id):
            await _send_text(
                matcher,
                "图鉴2需要先修好星空艇才能查看。",
                user_id,
                is_private=is_private,
            )
            return
    image = await get_collection_image(user_id, page=page)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@starry_exhibition_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    image = await get_starry_exhibition_image(user_id)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)


@set_bait_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    bait_input = group[0] if group and group[0] else ""
    if not bait_input:
        await _send_text(
            matcher,
            "格式：设定鱼饵 鱼饵ID/名称\n输入「设定鱼饵 取消」清除设定",
            user_id,
            is_private=is_private,
        )
    success, message = await set_preferred_bait(user_id, bait_input)
    await _send_text(matcher, message, user_id, is_private=is_private)


@sell_bait_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id, _ = await _ensure_user(event)
    is_private = _is_private_chat(event)
    bait_input = group[0] if group and group[0] else ""
    if not bait_input:
        await _send_text(
            matcher,
            "格式：卖出鱼饵 鱼饵ID/名称",
            user_id,
            is_private=is_private,
        )
    success, message = await sell_bait(user_id, bait_input)
    await _send_text(matcher, message, user_id, is_private=is_private)
