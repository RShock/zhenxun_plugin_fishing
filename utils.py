"""
工具模块 — 事件处理辅助函数 + render 相关路径/函数 re-export。

包含：
- 事件工具: _get_at_list, _ensure_user, _get_nickname, _is_private_chat
- 消息发送: _send_image, _send_text
- render 相关: 路径常量、渲染函数 re-export（供外部便捷引用）
"""

import asyncio

from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.internal.matcher import current_bot
from nonebot.matcher import Matcher, current_event
from nonebot_plugin_alconna import UniMessage

from .render import (
    FISH_IMAGES_PATH,
    FONT_FACE_CSS,
    FONT_FAMILY,
    FONT_FAMILY_DEFAULT,
    FONTS_PATH,
    GRADIENTS,
    HYPIXEL_FONT_URI,
    PLAYER_IMAGES_PATH,
    SCENES_IMAGES_PATH,
    TEMPLATES_PATH,
    ConfigManager,
    _find_scene_file,
    _find_skin_file,
    _get_all_skin_files,
    _get_skin_display_size,
    gradient_bg,
    render_backpack,
    render_collection,
    render_display,
    render_exchange_result,
    render_fishing_result,
    render_fishing_scene,
    render_fishing_start,
    render_html,
    render_location_select,
    render_nest_confirm,
    render_nest_result,
    render_sell_result,
    render_shop,
    render_sign_result,
    render_skin_list,
    render_template,
    render_upgrade_result,
    render_user_status,
)
from .services import get_or_create_user
from .services.user_lock_service import defer_user_lock_send


def _get_at_list(event) -> list[str]:
    at_list = []
    if hasattr(event, "get_message"):
        for seg in event.get_message():
            if getattr(seg, "type", None) not in {"at", "mention_user"}:
                continue
            target = seg.data.get("qq") or seg.data.get("user_id")
            if target:
                at_list.append(str(target))
    return at_list


def _clean_nickname_candidate(value) -> str:
    """拒绝协议残片式昵称，避免控制字符进入消息或 PostgreSQL 文本字段。"""
    if value is None:
        return ""
    nickname = str(value).strip()
    if not nickname or any(ord(char) < 32 or ord(char) == 127 for char in nickname):
        return ""
    return nickname[:255]


def _get_at_display_name(event) -> str:
    if not hasattr(event, "get_message"):
        return ""
    for seg in event.get_message():
        if getattr(seg, "type", None) not in {"at", "mention_user"}:
            continue
        data = getattr(seg, "data", {})
        if not isinstance(data, dict):
            continue
        name = _clean_nickname_candidate(
            data.get("username") or data.get("name") or data.get("nickname")
        )
        if name:
            return name
    return ""


async def _ensure_user(event) -> tuple[str, str]:
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    await get_or_create_user(user_id, nickname)
    return user_id, nickname


def _get_nickname(event) -> str:
    sender = getattr(event, "sender", None)
    if sender is not None:
        # 部分 OneBot 群名片会误传 protobuf 二进制片段；card 不可信时回退 QQ 昵称。
        for value in (
            getattr(sender, "card", None),
            getattr(sender, "nickname", None),
        ):
            if nickname := _clean_nickname_candidate(value):
                return nickname
    author = getattr(event, "author", None)
    return _clean_nickname_candidate(
        getattr(author, "username", None) if author is not None else None
    )


def _is_private_chat(event: Event) -> bool:
    return not hasattr(event, "group_id") or getattr(event, "group_id", None) is None


_MESSAGE_SEND_TIMEOUT_SECONDS = 30.0
_ROUTE2_ORIGINAL_USER_ID_ATTR = "_route2_original_user_id"


def _is_official_qq_group_event(event: Event | None) -> bool:
    author = getattr(event, "author", None) if event is not None else None
    return bool(getattr(event, "group_openid", None) and author is not None)


def _outgoing_recipient(
    user_id: str, event: Event | None = None
) -> tuple[str, str]:
    if event is None:
        try:
            event = current_event.get()
        except LookupError:
            return user_id, ""
    if _is_official_qq_group_event(event):
        # QQ 群事件只提供开放平台内部身份，实测群聊发送接口会把 <@内部ID>
        # 原样展示；这里改用“@昵称”文本标记玩家，避免把任何 OpenID 暴露出去。
        return "", _get_nickname(event)
    return _transport_user_id(user_id, event), ""


def _transport_user_id(user_id: str, event: Event | None = None) -> str:
    if event is None:
        try:
            event = current_event.get()
        except LookupError:
            return user_id
    # route2 replaces the business user ID with the bound legacy QQ number, but
    # adapter mentions must still use the official OpenID kept on the event.
    original = getattr(event, _ROUTE2_ORIGINAL_USER_ID_ATTR, None)
    return str(original or user_id)


def _build_image_message(
    image: bytes,
    text: str = "",
    user_id: str = "",
    is_private: bool = False,
    display_name: str = "",
) -> UniMessage:
    """Build a message that UniMessage can export for the active adapter."""
    msg = UniMessage()
    if user_id and not is_private:
        msg += UniMessage.at(user_id)
    elif display_name and not is_private:
        msg += UniMessage.text(f"@{display_name}，\n")
    msg += UniMessage.image(raw=image)
    if text:
        msg += UniMessage.text("\n" + text)
    return msg


def _build_text_message(
    text: str,
    user_id: str = "",
    is_private: bool = False,
    display_name: str = "",
) -> UniMessage:
    """Build a message that UniMessage can export for the active adapter."""
    msg = UniMessage()
    if user_id and not is_private:
        msg += UniMessage.at(user_id)
    elif display_name and not is_private:
        msg += UniMessage.text(f"@{display_name}，")
    msg += UniMessage.text(text)
    return msg


async def _deliver_universal_message(
    message: UniMessage, *, finish: bool = False
):
    """Send through the active adapter or collect directly for the internal web route."""
    try:
        bot = current_bot.get()
    except LookupError:
        bot = None

    # FakeWebBot has no protocol adapter, so UniMessage.export() cannot run.
    # Inspect the class to avoid Bot.__getattr__ treating this capability as an API.
    collector = (
        getattr(type(bot), "_collect_universal_message", None)
        if bot is not None
        else None
    )
    if collector is not None:
        await collector(bot, message)
        if finish:
            raise FinishedException
        return

    if finish:
        await message.finish()
    else:
        await message.send()


async def _send_image(
    matcher: Matcher,
    image: bytes,
    text: str = "",
    user_id: str = "",
    is_private: bool = False,
):
    del matcher  # UniMessage exports through the bot and event in the active context.
    mention_id, display_name = _outgoing_recipient(user_id)
    msg = _build_image_message(
        image,
        text,
        mention_id,
        is_private,
        display_name=display_name if not mention_id else "",
    )

    async def send():
        async with asyncio.timeout(_MESSAGE_SEND_TIMEOUT_SECONDS):
            await _deliver_universal_message(msg)

    if defer_user_lock_send(send):
        return
    await send()


async def _send_text(
    matcher: Matcher, text: str, user_id: str = "", is_private: bool = False
):
    mention_id, display_name = _outgoing_recipient(user_id)
    msg = _build_text_message(
        text,
        mention_id,
        is_private,
        display_name=display_name if not mention_id else "",
    )

    async def send():
        async with asyncio.timeout(_MESSAGE_SEND_TIMEOUT_SECONDS):
            await _deliver_universal_message(msg)

    if defer_user_lock_send(send):
        # The deferred sender owns delivery; stop this matcher to avoid a second send.
        await matcher.finish()
        return
    async with asyncio.timeout(_MESSAGE_SEND_TIMEOUT_SECONDS):
        await _deliver_universal_message(msg, finish=True)


__all__ = [
    "FISH_IMAGES_PATH",
    "FONTS_PATH",
    "FONT_FACE_CSS",
    "FONT_FAMILY",
    "FONT_FAMILY_DEFAULT",
    "GRADIENTS",
    "HYPIXEL_FONT_URI",
    "PLAYER_IMAGES_PATH",
    "SCENES_IMAGES_PATH",
    "TEMPLATES_PATH",
    "ConfigManager",
    "_ensure_user",
    "_find_scene_file",
    "_find_skin_file",
    "_get_all_skin_files",
    "_get_at_display_name",
    "_get_at_list",
    "_get_nickname",
    "_outgoing_recipient",
    "_get_skin_display_size",
    "_is_private_chat",
    "_send_image",
    "_send_text",
    "build_fish_item_data",
    "build_fish_list_data",
    "gradient_bg",
    "render_backpack",
    "render_collection",
    "render_display",
    "render_exchange_result",
    "render_fish_list",
    "render_fishing_result",
    "render_fishing_scene",
    "render_fishing_start",
    "render_html",
    "render_location_select",
    "render_nest_confirm",
    "render_nest_result",
    "render_sell_result",
    "render_shop",
    "render_sign_result",
    "render_skin_list",
    "render_template",
    "render_upgrade_result",
    "render_user_status",
    "render_weather_forecast",
]

_gradient_bg = gradient_bg
