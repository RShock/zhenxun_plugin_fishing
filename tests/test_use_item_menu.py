from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.constants import (
    MAX_FRAME_BUFF_LAYERS,
    MAX_NEST_LAYERS,
)
from zhenxun.plugins.zhenxun_plugin_fishing.handlers import item_menu
from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
    BIG_FISH_ITEM_ID,
    BIG_FISH_ITEM_TYPE,
)


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


def _item(item_id: str, item_type: str, count: int) -> tuple[str, dict]:
    return f"{item_id}|{item_type}", {"item_type": item_type, "count": count}


@pytest.mark.asyncio
async def test_use_item_menu_hides_contextually_full_nest_items(monkeypatch):
    items = dict(
        [
            _item("time_potion", "potion", 2),
            _item("\u56de\u6863\u836f\u6c34", "potion", 1),
            _item("\u5e78\u8fd0\u836f\u6c34", "potion", 3),
            _item("\u771f\u591a\u591a\u836f\u6c34", "potion", 4),
            _item("\u95ea\u5149\u836f\u6c34", "potion", 5),
            _item("utr_select_ticket", "ticket", 1),
            _item("1", "bait", 30),
            _item(BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE, 1),
        ]
    )
    user = SimpleNamespace(
        items=items,
        bait_id="1",
        fishing_status={"location_id": "13", "time_potions_used": []},
        corn=6,
        display_frames=7,
        cat_frames=8,
    )
    monkeypatch.setattr(item_menu, "get_or_create_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        item_menu.ConfigManager,
        "get_bait",
        lambda bait_id: SimpleNamespace(id=1, name="\u9c7c\u9975"),
    )
    monkeypatch.setattr(
        item_menu.ConfigManager,
        "get_location",
        lambda location_id: SimpleNamespace(id=location_id, name="13\u56fe"),
    )
    monkeypatch.setattr(
        item_menu.FishingUser, "get_nest_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        item_menu, "get_starry_bonus_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        item_menu,
        "_build_utr_ticket_options",
        AsyncMock(
            return_value=[
                item_menu.UseItemMenuOption(
                    label="13\u56fe UTR\u9c7c",
                    command="\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238 UTR\u9c7c",
                )
            ]
        ),
    )
    monkeypatch.setattr(
        item_menu, "_active_buff_count", AsyncMock(return_value=MAX_NEST_LAYERS)
    )
    monkeypatch.setattr(
        item_menu.FishingBuff,
        "get_global_buff_count",
        AsyncMock(return_value=MAX_FRAME_BUFF_LAYERS),
    )

    state = await item_menu.get_use_item_menu_state("user")
    commands = {option.command for option in state.options}
    reasons = {item.name: item.reason for item in state.unavailable}

    assert "\u9493\u9c7c\u4f7f\u7528 \u65f6\u5149\u836f\u6c34" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u56de\u6863\u836f\u6c34" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u5927\u80a5\u9c7c" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u9999\u751c\u7389\u7c73" not in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u5c55\u793a\u6728\u6846" not in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u732b\u732b\u6846" not in commands
    assert reasons["\u9999\u751c\u7389\u7c73"] == (
        "\u5f53\u524d\u5730\u70b9\u6253\u7a9d\u5c42\u6570\u5df2\u6ee1"
    )
    assert "50%" in reasons["\u5c55\u793a\u6728\u6846"]
    assert reasons["\u732b\u732b\u6846"] == (
        "\u661f\u7a7a\u56fe\u732b\u6846\u6253\u7a9d\u5c42\u6570\u5df2\u6ee1"
    )


@pytest.mark.asyncio
async def test_use_item_menu_includes_available_frames_and_corn(monkeypatch):
    user = SimpleNamespace(
        items={},
        bait_id="0",
        fishing_status={"location_id": "13", "time_potions_used": []},
        corn=2,
        display_frames=3,
        cat_frames=4,
    )
    monkeypatch.setattr(item_menu, "get_or_create_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        item_menu.ConfigManager,
        "get_location",
        lambda location_id: SimpleNamespace(id=location_id, name="13\u56fe"),
    )
    monkeypatch.setattr(
        item_menu.FishingUser, "get_nest_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        item_menu, "get_starry_bonus_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(item_menu, "_active_buff_count", AsyncMock(return_value=2))
    monkeypatch.setattr(
        item_menu.FishingBuff,
        "get_global_buff_count",
        AsyncMock(return_value=2),
    )

    options = await item_menu.get_use_item_menu_options("user")
    labels = {option.label for option in options}

    assert "\u9999\u751c\u7389\u7c73\u00d72" in labels
    assert "\u5c55\u793a\u6728\u6846\u00d73" in labels
    assert "\u732b\u732b\u6846\u00d74" in labels


@pytest.mark.asyncio
async def test_held_but_unusable_items_include_text_reasons(monkeypatch):
    user = SimpleNamespace(
        items=dict(
            [
                _item("time_potion", "potion", 2),
                _item("\u8bb8\u613f\u836f\u6c34", "potion", 1),
            ]
        ),
        bait_id="0",
        fishing_status=None,
        corn=0,
        display_frames=0,
        cat_frames=0,
        star_frames=3,
    )
    monkeypatch.setattr(item_menu, "get_or_create_user", AsyncMock(return_value=user))

    state = await item_menu.get_use_item_menu_state("user")
    reasons = {item.name: item.reason for item in state.unavailable}
    text = item_menu.format_unavailable_items(state.unavailable)

    assert state.options == []
    assert reasons["\u65f6\u5149\u836f\u6c34"] == "\u672a\u5728\u9493\u9c7c"
    unavailable_reason = (
        "\u5f53\u524d\u7248\u672c\u6682\u672a\u5f00\u653e\u4f7f\u7528\u65b9\u5f0f"
    )
    assert reasons["\u8bb8\u613f\u836f\u6c34"] == unavailable_reason
    assert reasons["\u661f\u7a7a\u6846"] == unavailable_reason
    assert "\u65f6\u5149\u836f\u6c34\u00d72\uff1a\u672a\u5728\u9493\u9c7c" in text
    assert "\u661f\u7a7a\u6846\u00d73" in text


def test_unavailable_text_does_not_create_keyboard_rows(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    state = item_menu.UseItemMenuState(
        options=[
            item_menu.UseItemMenuOption(
                label="\u5e78\u8fd0\u836f\u6c34\u00d71",
                command="\u9493\u9c7c\u4f7f\u7528 \u5e78\u8fd0\u836f\u6c34",
            )
        ],
        unavailable=[
            item_menu.UnavailableUseItem(
                name="\u9999\u751c\u7389\u7c73",
                count=5,
                reason="\u5f53\u524d\u5730\u70b9\u6253\u7a9d\u5c42\u6570\u5df2\u6ee1",
            ),
            item_menu.UnavailableUseItem(
                name="\u661f\u7a7a\u6846",
                count=2,
                reason="\u5f53\u524d\u7248\u672c\u6682\u672a\u5f00\u653e\u4f7f\u7528\u65b9\u5f0f",
            ),
        ],
    )
    markdown = item_menu.build_use_item_menu_markdown("\u9009\u62e9\u7269\u54c1", state)

    messages = item_menu.build_qq_use_item_messages(
        state.options,
        title=markdown,
    )

    assert len(messages) == 1
    assert "\u9999\u751c\u7389\u7c73\u00d75" in messages[0][0][1]
    keyboard = messages[0][1][1]
    assert len(keyboard.content.rows) == 1
    assert len(keyboard.content.rows[0].buttons) == 1


@pytest.mark.asyncio
async def test_utr_ticket_menu_is_limited_to_ten_and_marks_map_id(monkeypatch):
    locations = [
        SimpleNamespace(
            id="13", fish_pool=[f"\u5341\u4e09\u9c7c{i}" for i in range(1, 7)]
        ),
        SimpleNamespace(
            id="14", fish_pool=[f"\u5341\u56db\u9c7c{i}" for i in range(1, 7)]
        ),
    ]
    collected = {
        (fish_name, rarity)
        for location in locations
        for fish_name in location.fish_pool
        for rarity in ("UR", "UTR")
    }
    user = SimpleNamespace(
        items=dict([_item("utr_select_ticket", "ticket", 2)]),
    )
    monkeypatch.setattr(item_menu, "get_or_create_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        item_menu.FishingUser,
        "get_user_collected",
        AsyncMock(return_value=collected),
    )
    monkeypatch.setattr(item_menu.ConfigManager, "get_locations", lambda: locations)

    state = await item_menu.get_utr_ticket_menu_state("user")

    assert state.ticket_count == 2
    assert len(state.options) == 10
    assert state.options[0].label == "13\u56fe \u5341\u4e09\u9c7c1"
    assert state.options[0].command == (
        "\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238 \u5341\u4e09\u9c7c1"
    )
    assert state.options[-1].label.startswith("14\u56fe ")


def test_utr_ticket_menu_builds_two_messages_with_five_rows(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    options = [
        item_menu.UseItemMenuOption(
            label=f"13\u56fe \u9c7c{i}",
            command=f"\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238 \u9c7c{i}",
        )
        for i in range(10)
    ]

    messages = item_menu.build_qq_use_item_messages(
        options,
        title="\u9009\u62e9 UTR",
        buttons_per_row=1,
    )

    assert len(messages) == 2
    for message in messages:
        keyboard = message[1][1]
        assert len(keyboard.content.rows) == 5
        assert all(len(row.buttons) == 1 for row in keyboard.content.rows)
        assert all(row.buttons[0].action.enter is True for row in keyboard.content.rows)
    assert messages[0][1][1].content.rows[0].buttons[0].action.data == (
        "\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238 \u9c7c0"
    )
