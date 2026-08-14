"""QQ official-group shortcut menus for fishing item use and UTR tickets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nonebot import get_bots, logger
from nonebot.adapters import Bot, Event

from ..items.use_checks import (
    UseCheckContext,
    get_held_item_use_checks,
    normalize_use_item_name,
)
from ..utils import _get_group_context_id, _is_official_qq_group_event

_KEYBOARD_ROWS_PER_MESSAGE = 5
_ITEM_BUTTONS_PER_ROW = 2
_UTR_MENU_LIMIT = 10
_BUTTON_LABEL_MAX_LENGTH = 10

@dataclass(frozen=True)
class UseItemMenuOption:
    label: str
    command: str


@dataclass(frozen=True)
class UnavailableUseItem:
    name: str
    count: int
    reason: str


@dataclass(frozen=True)
class UseItemMenuState:
    options: list[UseItemMenuOption]
    unavailable: list[UnavailableUseItem]


@dataclass(frozen=True)
class UtrTicketMenuState:
    ticket_count: int
    options: list[UseItemMenuOption]


def is_utr_ticket_name(item_name: str) -> bool:
    return normalize_use_item_name(item_name) == "UTR自选券"


def _compact_label(label: str) -> str:
    if len(label) <= _BUTTON_LABEL_MAX_LENGTH:
        return label
    return label[: _BUTTON_LABEL_MAX_LENGTH - 1] + "…"


async def get_use_item_menu_state(
    user_id: str,
    *,
    is_private: bool = False,
    context: UseCheckContext | None = None,
) -> UseItemMenuState:
    """Convert shared item-use checks into buttons and explanatory text."""
    if context is None:
        context = await UseCheckContext.create(user_id, is_private=is_private)
    checks = await get_held_item_use_checks(context)
    options: list[UseItemMenuOption] = []
    unavailable: list[UnavailableUseItem] = []
    for check in checks:
        if check.usable:
            options.append(
                UseItemMenuOption(
                    label=_compact_label(
                        f"{check.canonical_name}×{check.count}"
                    ),
                    command=f"钓鱼使用 {check.canonical_name}",
                )
            )
        else:
            unavailable.append(
                UnavailableUseItem(
                    name=check.canonical_name,
                    count=check.count,
                    reason=check.reason,
                )
            )
    return UseItemMenuState(options=options, unavailable=unavailable)


async def get_use_item_menu_options(
    user_id: str, *, is_private: bool = False
) -> list[UseItemMenuOption]:
    """Compatibility wrapper returning only usable buttons."""
    state = await get_use_item_menu_state(user_id, is_private=is_private)
    return state.options


async def get_utr_ticket_menu_state(
    user_id: str,
    *,
    is_private: bool = False,
    context: UseCheckContext | None = None,
) -> UtrTicketMenuState:
    if context is None:
        context = await UseCheckContext.create(user_id, is_private=is_private)
    ticket_count = context.item_count("UTR自选券")
    if ticket_count <= 0:
        return UtrTicketMenuState(ticket_count=0, options=[])
    options = [
        UseItemMenuOption(
            label=_compact_label(option.label),
            command=option.command,
        )
        for option in await context.utr_options(limit=_UTR_MENU_LIMIT)
    ]
    return UtrTicketMenuState(ticket_count=ticket_count, options=options)


def format_unavailable_items(items: list[UnavailableUseItem]) -> str:
    if not items:
        return ""
    lines = ["⚠️ 已持有但当前不可用："]
    lines.extend(
        f"- {item.name}×{item.count}：{item.reason}" for item in items
    )
    return "\n".join(lines)


def build_use_item_menu_markdown(title: str, state: UseItemMenuState) -> str:
    unavailable_text = format_unavailable_items(state.unavailable)
    if not unavailable_text:
        return title
    return f"{title}\n\n{unavailable_text}"


def _build_qq_use_item_message(
    options: list[UseItemMenuOption], *, title: str, buttons_per_row: int
):
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

    message = QQMessage(QQMessageSegment.markdown(title))
    rows = []
    for index in range(0, len(options), buttons_per_row):
        row_options = options[index : index + buttons_per_row]
        buttons = []
        for option in row_options:
            buttons.append(
                Button(
                    render_data=RenderData(
                        label=option.label,
                        visited_label=option.label,
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
            )
        rows.append(InlineKeyboardRow(buttons=buttons))
    message.append(
        QQMessageSegment.keyboard(
            MessageKeyboard(content=InlineKeyboard(rows=rows))
        )
    )
    return message


def build_qq_use_item_messages(
    options: list[UseItemMenuOption],
    *,
    title: str,
    buttons_per_row: int = _ITEM_BUTTONS_PER_ROW,
) -> list[Any]:
    """Split menus at QQ's five keyboard rows per message."""
    if not options:
        return []
    per_message = _KEYBOARD_ROWS_PER_MESSAGE * buttons_per_row
    chunks = [
        options[index : index + per_message]
        for index in range(0, len(options), per_message)
    ]
    total = len(chunks)
    messages = []
    for index, chunk in enumerate(chunks, 1):
        chunk_title = title if total == 1 else f"{title}（{index}/{total}）"
        messages.append(
            _build_qq_use_item_message(
                chunk,
                title=chunk_title,
                buttons_per_row=buttons_per_row,
            )
        )
    return messages


def _resolve_official_group_sender(bot: Bot, event: Event) -> tuple[Bot, str] | None:
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
        logger.debug(f"[fishing item menu] official QQ sender lookup failed: {e}")
    return None


async def try_send_use_item_menu(
    bot: Bot,
    event: Event,
    *,
    options: list[UseItemMenuOption],
    title: str,
    buttons_per_row: int = _ITEM_BUTTONS_PER_ROW,
) -> bool:
    if not options:
        return False
    sender = _resolve_official_group_sender(bot, event)
    if sender is None:
        return False
    official_bot, group_openid = sender
    try:
        for message in build_qq_use_item_messages(
            options, title=title, buttons_per_row=buttons_per_row
        ):
            await official_bot.send_to_group(
                group_openid=group_openid,
                message=message,
            )
    except Exception as e:
        logger.warning(f"[fishing item menu] proactive QQ send failed: {e}")
        return False
    return True


__all__ = [
    "UnavailableUseItem",
    "UseItemMenuOption",
    "UseItemMenuState",
    "UtrTicketMenuState",
    "build_qq_use_item_messages",
    "build_use_item_menu_markdown",
    "format_unavailable_items",
    "get_use_item_menu_options",
    "get_use_item_menu_state",
    "get_utr_ticket_menu_state",
    "is_utr_ticket_name",
    "try_send_use_item_menu",
]
