from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.constants import STARRY_FRAMES_MAX
from zhenxun.plugins.zhenxun_plugin_fishing.handlers import shop as shop_handler
from zhenxun.plugins.zhenxun_plugin_fishing.handlers import shop_menu


def _user(**overrides):
    data = {
        "gold": 123456,
        "rod_level": 5,
        "base_rod_level": 5,
        "hook_level": 5,
        "display_slots": 3,
        "upgraded_display_count": 0,
        "starry_frames": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_shop_menu_lists_current_upgrades_and_every_bait(monkeypatch):
    user = _user(rod_level=11, base_rod_level=10)
    baits = [
        SimpleNamespace(name="蚯蚓鱼饵"),
        SimpleNamespace(name="虾米鱼饵"),
        SimpleNamespace(name="拟饵"),
    ]
    monkeypatch.setattr(shop_menu, "get_or_create_user", AsyncMock(return_value=user))
    monkeypatch.setattr(shop_menu, "has_starry_ship", AsyncMock(return_value=False))
    monkeypatch.setattr(
        shop_menu.ConfigManager,
        "get_shop",
        lambda: SimpleNamespace(baits=baits),
    )

    state = await shop_menu.get_shop_menu_state("user")

    assert state.gold == 123456
    assert [option.command for option in state.options] == [
        "建设星空艇",
        "升级鱼钩",
        "升级展示栏",
        "鱼店购买 蚯蚓鱼饵 1",
        "鱼店购买 虾米鱼饵 1",
        "鱼店购买 拟饵 1",
    ]


@pytest.mark.asyncio
async def test_shop_menu_hides_maxed_upgrades_but_keeps_all_baits(monkeypatch):
    user = _user(
        rod_level=20,
        base_rod_level=20,
        hook_level=10,
        display_slots=10,
        upgraded_display_count=10,
        starry_frames=STARRY_FRAMES_MAX,
    )
    baits = [SimpleNamespace(name="传说鱼饵")]
    monkeypatch.setattr(shop_menu, "get_or_create_user", AsyncMock(return_value=user))
    monkeypatch.setattr(shop_menu, "has_starry_ship", AsyncMock(return_value=True))
    monkeypatch.setattr(
        shop_menu.ConfigManager,
        "get_shop",
        lambda: SimpleNamespace(baits=baits),
    )

    state = await shop_menu.get_shop_menu_state("user")

    assert [option.command for option in state.options] == ["鱼店购买 传说鱼饵 1"]


@pytest.mark.asyncio
async def test_shop_menu_uses_two_buttons_per_row(monkeypatch):
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(shop_menu, "try_send_use_item_menu", sender)
    state = shop_menu.ShopMenuState(
        gold=1,
        options=[
            shop_menu.UseItemMenuOption(label="拟饵×1", command="鱼店购买 拟饵 1")
        ],
    )
    bot = Mock()
    event = Mock()

    assert await shop_menu.try_send_shop_menu(bot, event, state=state, title="鱼店")
    sender.assert_awaited_once_with(
        bot,
        event,
        options=state.options,
        title="鱼店",
        buttons_per_row=2,
    )


@pytest.mark.asyncio
async def test_shop_handler_sends_image_then_markdown_menu_separately(monkeypatch):
    calls = []
    state = shop_menu.ShopMenuState(gold=10, options=[])
    monkeypatch.setattr(
        shop_handler, "_ensure_user", AsyncMock(return_value=("user", "name"))
    )
    monkeypatch.setattr(shop_handler, "_is_private_chat", lambda event: False)
    monkeypatch.setattr(
        shop_handler, "get_shop_menu_state", AsyncMock(return_value=state)
    )
    monkeypatch.setattr(shop_handler, "get_shop_image", AsyncMock(return_value=b"png"))

    async def send_image(*args, **kwargs):
        calls.append("image")

    async def send_menu(*args, **kwargs):
        calls.append("markdown")
        return True

    monkeypatch.setattr(shop_handler, "_send_image", send_image)
    monkeypatch.setattr(shop_handler, "try_send_shop_menu", send_menu)
    send_text = AsyncMock()
    monkeypatch.setattr(shop_handler, "_send_text", send_text)

    await shop_handler.show_shop(Mock(), Mock(), Mock())

    assert calls == ["image", "markdown"]
    send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_shop_handler_still_sends_menu_when_image_fails(monkeypatch):
    state = shop_menu.ShopMenuState(gold=10, options=[])
    monkeypatch.setattr(
        shop_handler, "_ensure_user", AsyncMock(return_value=("user", "name"))
    )
    monkeypatch.setattr(shop_handler, "_is_private_chat", lambda event: False)
    monkeypatch.setattr(
        shop_handler, "get_shop_menu_state", AsyncMock(return_value=state)
    )
    monkeypatch.setattr(shop_handler, "get_shop_image", AsyncMock(return_value=b"png"))
    monkeypatch.setattr(
        shop_handler, "_send_image", AsyncMock(side_effect=RuntimeError("failed"))
    )
    send_menu = AsyncMock(return_value=True)
    monkeypatch.setattr(shop_handler, "try_send_shop_menu", send_menu)
    send_text = AsyncMock()
    monkeypatch.setattr(shop_handler, "_send_text", send_text)

    await shop_handler.show_shop(Mock(), Mock(), Mock())

    send_menu.assert_awaited_once()
    send_text.assert_not_awaited()
