"""鱼店购买按钮菜单。"""

from __future__ import annotations

from dataclasses import dataclass

from nonebot.adapters import Bot, Event

from ..config import ConfigManager
from ..constants import STARRY_FRAMES_MAX
from ..services import get_or_create_user
from ..starry import has_starry_ship
from .item_menu import UseItemMenuOption, try_send_use_item_menu

_SHOP_BUTTONS_PER_ROW = 2


@dataclass(frozen=True)
class ShopMenuState:
    gold: int
    options: list[UseItemMenuOption]


def _display_upgrade_available(user, *, has_ship: bool) -> bool:
    wood_available = int(user.display_slots or 0) < 10
    cat_available = (
        int(user.display_slots or 0) > 0
        and int(user.upgraded_display_count or 0) < 10
        and int(user.upgraded_display_count or 0) < int(user.display_slots or 0)
    )
    starry_available = has_ship and int(user.starry_frames or 0) < STARRY_FRAMES_MAX
    return wood_available or cat_available or starry_available


async def get_shop_menu_state(user_id: str) -> ShopMenuState:
    """返回当前玩家鱼店中仍可执行的全部购买/升级入口。"""
    user = await get_or_create_user(user_id)
    has_ship = await has_starry_ship(user_id)
    options: list[UseItemMenuOption] = []

    if int(user.rod_level or 0) < 20:
        if int(user.base_rod_level or 0) >= 10 and not has_ship:
            options.append(UseItemMenuOption(label="购买星空艇", command="建设星空艇"))
        else:
            options.append(UseItemMenuOption(label="升级钓竿", command="升级钓竿"))

    if int(user.hook_level or 0) < 10:
        options.append(UseItemMenuOption(label="升级鱼钩", command="升级鱼钩"))

    if _display_upgrade_available(user, has_ship=has_ship):
        options.append(UseItemMenuOption(label="升级展示栏", command="升级展示栏"))

    options.extend(
        UseItemMenuOption(
            label=f"{bait.name}×1",
            command=f"鱼店购买 {bait.name} 1",
        )
        for bait in ConfigManager.get_shop().baits
    )
    return ShopMenuState(gold=int(user.gold or 0), options=options)


def build_shop_menu_markdown(state: ShopMenuState) -> str:
    return (
        "🛒 鱼店购买\n"
        f"当前钓鱼币：{state.gold:,}\n"
        "鱼饵按钮默认购买 1 个；升级按钮执行一次对应升级。"
    )


def build_shop_menu_fallback_text(state: ShopMenuState) -> str:
    lines = [build_shop_menu_markdown(state), "", "可用指令："]
    lines.extend(f"- {option.command}" for option in state.options)
    return "\n".join(lines)


async def try_send_shop_menu(
    bot: Bot,
    event: Event,
    *,
    state: ShopMenuState,
    title: str,
) -> bool:
    return await try_send_use_item_menu(
        bot,
        event,
        options=state.options,
        title=title,
        buttons_per_row=_SHOP_BUTTONS_PER_ROW,
    )


__all__ = [
    "ShopMenuState",
    "build_shop_menu_fallback_text",
    "build_shop_menu_markdown",
    "get_shop_menu_state",
    "try_send_shop_menu",
]
