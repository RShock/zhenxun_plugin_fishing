"""QQ official Bot proactive black/white market shortcut menus."""

from __future__ import annotations

from typing import Any

from nonebot import get_bots, logger
from nonebot.adapters import Bot, Event

from ..backpack.black_market import MarketMenuOption
from ..utils import _get_group_context_id, _is_official_qq_group_event

_KEYBOARD_ROWS_PER_MESSAGE = 5
_BUTTON_LABEL_MAX_LENGTH = 10


def _button_label(option: MarketMenuOption) -> str:
    """Keep both rarities visible within QQ's ten-character label limit."""
    source_rarity = option.source.rarity
    target_rarity = option.target.rarity
    fixed_length = len(source_rarity) + len(target_rarity) + 1
    name_budget = max(2, _BUTTON_LABEL_MAX_LENGTH - fixed_length)
    source_budget = max(1, (name_budget + 1) // 2)
    target_budget = max(1, name_budget - source_budget)
    return (
        f"{option.source.name[:source_budget]}{source_rarity}>"
        f"{option.target.name[:target_budget]}{target_rarity}"
    )


def _build_qq_market_message(options: list[MarketMenuOption]):
    """Build one keyboard-only message with at most five button rows."""
    from nonebot.adapters.qq import Message as QQMessage
    from nonebot.adapters.qq import MessageSegment as QQMessageSegment
    from nonebot.adapters.qq.models.common import (
        Action,
        Button,
        InlineKeyboard,
        InlineKeyboardRow,
        MessageKeyboard,
        Permission,
        RenderData,
    )

    message = QQMessage(QQMessageSegment.markdown("\u200b"))
    rows = []
    for option in options:
        label = _button_label(option)
        rows.append(
            InlineKeyboardRow(
                buttons=[
                    Button(
                        render_data=RenderData(
                            label=label,
                            visited_label=label,
                            style=1,
                        ),
                        action=Action(
                            type=2,
                            data=option.command,
                            enter=True,
                            permission=Permission(type=2),
                            unsupport_tips="\u8bf7\u5347\u7ea7\u81f3\u6700\u65b0\u7248\u672c",
                        ),
                    )
                ]
            )
        )
    keyboard = MessageKeyboard(content=InlineKeyboard(rows=rows))
    message.append(QQMessageSegment.keyboard(keyboard))
    return message


def build_qq_market_messages(options: list[MarketMenuOption]) -> list[Any]:
    """Split non-empty options at QQ's five keyboard rows per message."""
    if not options:
        return []
    chunks = [
        options[index : index + _KEYBOARD_ROWS_PER_MESSAGE]
        for index in range(0, len(options), _KEYBOARD_ROWS_PER_MESSAGE)
    ]
    return [_build_qq_market_message(chunk) for chunk in chunks]


def _resolve_official_group_sender(bot: Bot, event: Event) -> tuple[Bot, str] | None:
    """Resolve an official QQ Bot capable of proactive group sending."""
    if _is_official_qq_group_event(event):
        group_openid = str(getattr(event, "group_openid", "") or "")
        if group_openid and callable(getattr(bot, "send_to_group", None)):
            return bot, group_openid

    group_id = _get_group_context_id(event)
    if not group_id:
        return None
    try:
        from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
            official_route_bridge as bridge,
        )

        target = bridge.get_target(group_id)
        bots = get_bots()
        if target and target.bot_id in bots:
            official_bot = bots[target.bot_id]
            if callable(getattr(official_bot, "send_to_group", None)):
                return official_bot, target.group_openid
    except Exception as e:
        logger.debug(f"[黑白商菜单] 查找 QQ 官方主动发送通道失败: {e}")
    return None


async def try_send_market_menu(
    bot: Bot,
    event: Event,
    *,
    options: list[MarketMenuOption],
) -> bool:
    """Send non-empty options proactively; otherwise require caller fallback."""
    if not options:
        return False
    sender = _resolve_official_group_sender(bot, event)
    if sender is None:
        return False
    official_bot, group_openid = sender
    try:
        for message in build_qq_market_messages(options):
            await official_bot.send_to_group(
                group_openid=group_openid,
                message=message,
            )
    except Exception as e:
        logger.warning(f"[黑白商菜单] QQ 主动发送失败，沿用旧回复: {e}")
        return False
    return True


__all__ = [
    "build_qq_market_messages",
    "try_send_market_menu",
]
