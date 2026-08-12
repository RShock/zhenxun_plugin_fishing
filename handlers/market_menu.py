"""QQ official Bot proactive black/white market shortcut menus."""

from __future__ import annotations

from typing import Any

from nonebot import get_bots, logger
from nonebot.adapters import Bot, Event

from ..backpack.black_market import MarketMenuOption
from ..utils import _get_group_context_id, _is_official_qq_group_event

_KEYBOARD_ROWS_PER_MESSAGE = 5


def _button_label(option: MarketMenuOption) -> str:
    """Build a concise label within QQ keyboard limits."""
    label = f"{option.source.name}?{option.target.name}"
    if len(label) <= 10:
        return label
    return f"{option.source.name[:4]}?{option.target.name[:4]}"


def _build_qq_market_message(
    title: str,
    options: list[MarketMenuOption],
    *,
    page: int = 1,
    pages: int = 1,
    empty_text: str = "No exchange options are currently available.",
):
    """Build one Markdown and keyboard message with at most five rows."""
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

    page_suffix = f"?{page}/{pages}?" if pages > 1 else ""
    lines = [f"## {title}{page_suffix}"]
    if options:
        lines.append("点击按钮发送完整兑换指令：")
        for index, option in enumerate(options, 1):
            lines.append(
                f"{index}. {option.source.name}{option.source.rarity} ? "
                f"{option.target.name}{option.target.rarity}"
            )
    else:
        lines.append(empty_text)

    message = QQMessage(QQMessageSegment.markdown("\n".join(lines)))
    if not options:
        return message

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
                            unsupport_tips="请升级至最新版本",
                        ),
                    )
                ]
            )
        )
    keyboard = MessageKeyboard(content=InlineKeyboard(rows=rows))
    message.append(QQMessageSegment.keyboard(keyboard))
    return message


def build_qq_market_messages(
    title: str,
    options: list[MarketMenuOption],
    *,
    empty_text: str = "No exchange options are currently available.",
) -> list[Any]:
    """Split the menu at QQ's five keyboard rows per message."""
    if not options:
        return [_build_qq_market_message(title, [], empty_text=empty_text)]
    chunks = [
        options[index : index + _KEYBOARD_ROWS_PER_MESSAGE]
        for index in range(0, len(options), _KEYBOARD_ROWS_PER_MESSAGE)
    ]
    pages = len(chunks)
    return [
        _build_qq_market_message(
            title,
            chunk,
            page=page,
            pages=pages,
            empty_text=empty_text,
        )
        for page, chunk in enumerate(chunks, 1)
    ]


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
    title: str,
    options: list[MarketMenuOption],
    empty_text: str,
) -> bool:
    """Send proactively through QQ; return False when fallback is required."""
    sender = _resolve_official_group_sender(bot, event)
    if sender is None:
        return False
    official_bot, group_openid = sender
    try:
        for message in build_qq_market_messages(title, options, empty_text=empty_text):
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
