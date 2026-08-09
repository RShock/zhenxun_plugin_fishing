from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, Mock

import pytest


class _Model:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeMessage(list):
    def __init__(self, segment):
        super().__init__([segment])


class _FakeMessageSegment:
    @staticmethod
    def markdown(text):
        return ("markdown", text)

    @staticmethod
    def keyboard(keyboard):
        return ("keyboard", keyboard)


def _install_fake_qq_adapter(monkeypatch):
    qq_module = types.ModuleType("nonebot.adapters.qq")
    qq_module.Message = _FakeMessage
    qq_module.MessageSegment = _FakeMessageSegment

    common_module = types.ModuleType("nonebot.adapters.qq.models.common")
    for name in (
        "Action",
        "Button",
        "InlineKeyboard",
        "InlineKeyboardRow",
        "MessageKeyboard",
        "Permission",
        "RenderData",
    ):
        setattr(common_module, name, _Model)

    models_module = types.ModuleType("nonebot.adapters.qq.models")
    models_module.common = common_module
    monkeypatch.setitem(sys.modules, "nonebot.adapters.qq", qq_module)
    monkeypatch.setitem(sys.modules, "nonebot.adapters.qq.models", models_module)
    monkeypatch.setitem(
        sys.modules, "nonebot.adapters.qq.models.common", common_module
    )


def _load_menu():
    from zhenxun.plugins.zhenxun_plugin_fishing.handlers import menu

    return menu


def test_qq_keyboard_buttons_submit_commands_directly(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    menu = _load_menu()

    message = menu._build_qq_keyboard_message()
    keyboard = message[1][1]
    buttons = [button for row in keyboard.content.rows for button in row.buttons]

    assert message[0] == ("markdown", "🎣 钓鱼菜单")
    assert len(buttons) == sum(len(row) for row in menu._MENU_ROWS)
    assert all(button.action.enter is True for button in buttons)
    assert [button.action.data for button in buttons] == [
        command for row in menu._MENU_ROWS for _, command in row
    ]


@pytest.mark.asyncio
async def test_official_group_menu_sends_one_keyboard_message(monkeypatch):
    menu = _load_menu()
    monkeypatch.setattr(menu, "_is_official_qq_group_event", lambda event: True)
    monkeypatch.setattr(menu, "_build_qq_keyboard_message", Mock(return_value="menu"))
    send_to_group = AsyncMock()
    bot = Mock(send_to_group=send_to_group)
    event = Mock(group_openid="group-open-id", get_user_id=Mock(return_value="user"))
    matcher = Mock()
    send_text = AsyncMock()
    monkeypatch.setattr(menu, "_send_text", send_text)

    await menu._(bot, event, matcher)

    send_to_group.assert_awaited_once_with(
        group_openid="group-open-id", message="menu"
    )
    send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_official_group_menu_falls_back_to_one_text_message(monkeypatch):
    menu = _load_menu()
    monkeypatch.setattr(menu, "_is_official_qq_group_event", lambda event: True)
    monkeypatch.setattr(menu, "_build_qq_keyboard_message", Mock(return_value="menu"))
    send_to_group = AsyncMock(side_effect=RuntimeError("send failed"))
    bot = Mock(send_to_group=send_to_group)
    event = Mock(group_openid="group-open-id", get_user_id=Mock(return_value="user"))
    matcher = Mock()
    send_text = AsyncMock()
    monkeypatch.setattr(menu, "_send_text", send_text)

    await menu._(bot, event, matcher)

    send_to_group.assert_awaited_once()
    send_text.assert_awaited_once_with(matcher, menu._build_menu_text(), "user")
