"""
工具模块 — 事件处理辅助函数 + render 相关路径/函数 re-export。

包含：
- 事件工具: _get_at_list, _ensure_user, _get_nickname, _is_private_chat
- 消息发送: _send_image, _send_text
- render 相关: 路径常量、渲染函数 re-export（供外部便捷引用）
"""

from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.matcher import Matcher

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


def _get_at_list(event) -> list[str]:
    at_list = []
    if hasattr(event, "get_message"):
        for seg in event.get_message():
            if seg.type == "at":
                at_list.append(seg.data.get("qq") or seg.data.get("user_id", ""))
    return at_list


async def _ensure_user(event) -> tuple[str, str]:
    user_id = event.get_user_id()
    nickname = _get_nickname(event)
    await get_or_create_user(user_id, nickname)
    return user_id, nickname


def _get_nickname(event) -> str:
    nickname = ""
    if hasattr(event, "sender") and hasattr(event.sender, "nickname"):
        nickname = event.sender.nickname or ""
    return nickname


def _is_private_chat(event: Event) -> bool:
    return not hasattr(event, "group_id") or getattr(event, "group_id", None) is None


async def _send_image(
    matcher: Matcher,
    image: bytes,
    text: str = "",
    user_id: str = "",
    is_private: bool = False,
):
    msg = Message()
    if user_id and not is_private:
        msg += MessageSegment.at(user_id)
    msg += MessageSegment.image(image)
    if text:
        msg += MessageSegment.text("\n" + text)
    await matcher.send(msg)


async def _send_text(
    matcher: Matcher, text: str, user_id: str = "", is_private: bool = False
):
    msg = Message()
    if user_id and not is_private:
        msg += MessageSegment.at(user_id)
    msg += MessageSegment.text(text)
    await matcher.finish(msg)


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
    "_get_at_list",
    "_get_nickname",
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
