"""QQ official-group shortcut menus for fishing item use and UTR tickets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nonebot import get_bots, logger
from nonebot.adapters import Bot, Event

from ..config import ConfigManager
from ..constants import DAILY_NEST_LIMIT, MAX_FRAME_BUFF_LAYERS, MAX_NEST_LAYERS
from ..core.context import normalize_time_potions
from ..models import BuffEffect, FishingBuff, FishingUser
from ..scene_instance import get_scene_instance_id
from ..services import get_or_create_user
from ..services.achievement_service import BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE
from ..starry import get_starry_bonus_count, is_starry_location
from ..utils import _get_group_context_id, _is_official_qq_group_event

_KEYBOARD_ROWS_PER_MESSAGE = 5
_ITEM_BUTTONS_PER_ROW = 2
_UTR_MENU_LIMIT = 10
_BUTTON_LABEL_MAX_LENGTH = 10
_UTR_TICKET_ALIASES = {
    "UTR自选券",
    "utr自选券",
    "UTR券",
    "utr券",
}


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
    compact = (item_name or "").replace(" ", "").replace("　", "")
    return compact in _UTR_TICKET_ALIASES


def _json_item_count(user, item_id: str, item_type: str) -> int:
    items = user.items if isinstance(getattr(user, "items", None), dict) else {}
    entry = items.get(f"{item_id}|{item_type}")
    if not isinstance(entry, dict):
        return 0
    return max(0, int(entry.get("count", 0) or 0))


def _compact_label(label: str) -> str:
    if len(label) <= _BUTTON_LABEL_MAX_LENGTH:
        return label
    return label[: _BUTTON_LABEL_MAX_LENGTH - 1] + "…"


async def _active_buff_count(**filters) -> int:
    return await FishingBuff.filter(**filters).count()


async def _time_potion_unavailable_reason(user, status: dict) -> str | None:
    if not status:
        return "未在钓鱼"
    bait = ConfigManager.get_bait(str(getattr(user, "bait_id", "0") or "0"))
    if not bait or str(getattr(user, "bait_id", "0")) == "0":
        return "未装备鱼饵"
    bait_count = _json_item_count(user, str(bait.id), "bait")
    if bait_count < 30:
        return f"当前鱼饵不足30个（{bait_count}个）"
    return None


def _rollback_potion_unavailable_reason(status: dict) -> str | None:
    if not status:
        return "未在钓鱼"
    if not is_starry_location(str(status.get("location_id", ""))):
        return "仅可在11-20星空图使用"
    if normalize_time_potions(status.get("time_potions_used", [])):
        return "本次钓鱼已使用时光药水"
    return None


async def _corn_nest_unavailable_reason(
    user_id: str, status: dict, *, is_private: bool
) -> str | None:
    if not status:
        return "未在钓鱼"
    location_id = str(status.get("location_id", ""))
    location = ConfigManager.get_location(location_id)
    if not location:
        return "当前钓鱼地点无效"
    if not is_private and await FishingUser.get_nest_count(user_id) >= DAILY_NEST_LIMIT:
        return "今日打窝次数已用完"

    available_layers = MAX_NEST_LAYERS
    if not is_starry_location(location_id):
        available_layers = max(0, MAX_NEST_LAYERS - await get_starry_bonus_count())
    if available_layers <= 0:
        return "当前地点打窝上限已被星空艇加成占满"

    scene_instance_id = get_scene_instance_id(status, location_id)
    active_layers = await _active_buff_count(
        target_type=BuffEffect.TARGET_TYPE_LOCATION,
        target_id=scene_instance_id,
        buff_type=BuffEffect.BUFF_TYPE_NEST,
        end_time__gt=datetime.now(),
    )
    if active_layers >= available_layers:
        return "当前地点打窝层数已满"
    return None


async def _cat_nest_unavailable_reason(
    user_id: str, status: dict, *, is_private: bool
) -> str | None:
    if not status:
        return "未在钓鱼"
    if not is_starry_location(str(status.get("location_id", ""))):
        return "仅可在11-20星空图使用"
    if not is_private and await FishingUser.get_nest_count(user_id) >= DAILY_NEST_LIMIT:
        return "今日打窝次数已用完"
    active_layers = await _active_buff_count(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_CAT_NEST,
        end_time__gt=datetime.now(),
    )
    if active_layers >= MAX_NEST_LAYERS:
        return "星空图猫框打窝层数已满"
    return None


async def _build_utr_ticket_options(user_id: str) -> list[UseItemMenuOption]:
    collected = set(await FishingUser.get_user_collected(user_id))
    options: list[UseItemMenuOption] = []
    for location in ConfigManager.get_locations():
        fish_names = list(location.fish_pool)
        if not fish_names:
            continue
        if not any((fish_name, "UTR") in collected for fish_name in fish_names):
            continue
        if any((fish_name, "UR") not in collected for fish_name in fish_names):
            continue
        for fish_name in fish_names:
            label = _compact_label(f"{location.id}图 {fish_name}")
            options.append(
                UseItemMenuOption(
                    label=label,
                    command=f"钓鱼使用 UTR自选券 {fish_name}",
                )
            )
            if len(options) >= _UTR_MENU_LIMIT:
                return options
    return options


async def get_use_item_menu_state(
    user_id: str, *, is_private: bool = False
) -> UseItemMenuState:
    """Return usable buttons and held-but-unusable item explanations."""
    user = await get_or_create_user(user_id)
    status = user.fishing_status if isinstance(user.fishing_status, dict) else {}
    options: list[UseItemMenuOption] = []
    unavailable: list[UnavailableUseItem] = []

    def add(name: str, count: int, reason: str | None = None) -> None:
        if count <= 0:
            return
        if reason:
            unavailable.append(UnavailableUseItem(name, count, reason))
            return
        options.append(
            UseItemMenuOption(
                label=_compact_label(f"{name}×{count}"),
                command=f"钓鱼使用 {name}",
            )
        )

    time_count = _json_item_count(user, "time_potion", "potion")
    if time_count:
        add(
            "时光药水",
            time_count,
            await _time_potion_unavailable_reason(user, status),
        )

    rollback_count = _json_item_count(user, "回档药水", "potion")
    if rollback_count:
        add(
            "回档药水",
            rollback_count,
            _rollback_potion_unavailable_reason(status),
        )

    add("幸运药水", _json_item_count(user, "幸运药水", "potion"))
    add(
        "真多多药水",
        _json_item_count(user, "真多多药水", "potion"),
    )
    add("闪光药水", _json_item_count(user, "闪光药水", "potion"))

    ticket_count = _json_item_count(user, "utr_select_ticket", "ticket")
    if ticket_count:
        utr_options = await _build_utr_ticket_options(user_id)
        add(
            "UTR自选券",
            ticket_count,
            None
            if utr_options
            else "暂无符合兑换条件的UTR鱼（需对应图已解锁UTR且集齐全部UR）",
        )

    corn_count = max(0, int(getattr(user, "corn", 0) or 0))
    if corn_count:
        add(
            "香甜玉米",
            corn_count,
            await _corn_nest_unavailable_reason(
                user_id, status, is_private=is_private
            ),
        )

    display_frame_count = max(0, int(getattr(user, "display_frames", 0) or 0))
    if display_frame_count:
        frame_layers = await FishingBuff.get_global_buff_count(
            BuffEffect.BUFF_TYPE_FRAME
        )
        add(
            "展示木框",
            display_frame_count,
            f"全图展示木框效果已满{MAX_FRAME_BUFF_LAYERS * 5}%"
            if frame_layers >= MAX_FRAME_BUFF_LAYERS
            else None,
        )

    cat_frame_count = max(0, int(getattr(user, "cat_frames", 0) or 0))
    if cat_frame_count:
        add(
            "猫猫框",
            cat_frame_count,
            await _cat_nest_unavailable_reason(
                user_id, status, is_private=is_private
            ),
        )

    add(
        "大肥鱼",
        _json_item_count(user, BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE),
    )
    add(
        "许愿药水",
        _json_item_count(user, "许愿药水", "potion"),
        "当前版本暂未开放使用方式",
    )
    add(
        "星空框",
        max(0, int(getattr(user, "star_frames", 0) or 0)),
        "当前版本暂未开放使用方式",
    )
    return UseItemMenuState(options=options, unavailable=unavailable)


async def get_use_item_menu_options(
    user_id: str, *, is_private: bool = False
) -> list[UseItemMenuOption]:
    """Compatibility wrapper returning only usable buttons."""
    state = await get_use_item_menu_state(user_id, is_private=is_private)
    return state.options


async def get_utr_ticket_menu_state(user_id: str) -> UtrTicketMenuState:
    user = await get_or_create_user(user_id)
    ticket_count = _json_item_count(user, "utr_select_ticket", "ticket")
    if ticket_count <= 0:
        return UtrTicketMenuState(ticket_count=0, options=[])
    return UtrTicketMenuState(
        ticket_count=ticket_count,
        options=await _build_utr_ticket_options(user_id),
    )


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
