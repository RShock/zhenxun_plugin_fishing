"""猫猫乐园建设指令。"""

import re

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..cat_park import (
    has_cat_park_ticket,
    render_cat_park_image,
    upgrade_cat_park_building,
)
from ..matchers import cat_park_build_matcher
from ..utils import _get_nickname, _is_private_chat, _send_image, _send_text
from ..services import get_or_create_user


@cat_park_build_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    is_private = _is_private_chat(event)
    await get_or_create_user(user_id, nickname)

    # 异常情况只返回文字提示，不渲染图片，减少渲染时间
    if not await has_cat_park_ticket(user_id):
        await _send_text(
            matcher,
            "猫猫乐园尚未解锁：需要任意两张普通地图的全部 UTR 图鉴。",
            user_id=user_id,
            is_private=is_private,
        )

    target = group[0].strip() if group and group[0] else ""
    if target:
        normalized_digits = re.sub(r"\s+", "", target)
        if normalized_digits.isdigit() and len(normalized_digits) > 1:
            messages = []
            for index in normalized_digits:
                _, message = await upgrade_cat_park_building(user_id, index)
                messages.append(f"{index}. {message}")
            image = await render_cat_park_image(user_id, "<br>".join(messages))
            await _send_image(matcher, image, user_id=user_id, is_private=is_private)
            return

        success, message = await upgrade_cat_park_building(user_id, target)
        if not success:
            await _send_text(matcher, message, user_id=user_id, is_private=is_private)
        image = await render_cat_park_image(user_id, message)
        await _send_image(matcher, image, user_id=user_id, is_private=is_private)
        return

    image = await render_cat_park_image(user_id)
    await _send_image(matcher, image, user_id=user_id, is_private=is_private)
