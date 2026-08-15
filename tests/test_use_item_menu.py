from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.constants import (
    MAX_FRAME_BUFF_LAYERS,
    MAX_NEST_LAYERS,
)
from zhenxun.plugins.zhenxun_plugin_fishing.handlers import item_menu
from zhenxun.plugins.zhenxun_plugin_fishing.items import use_checks
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


def _buff(buff_type: str, target_type: str, target_id: str = "", value: int = 5):
    return SimpleNamespace(
        buff_type=buff_type,
        target_type=target_type,
        target_id=target_id,
        value=value,
    )


@pytest.mark.asyncio
async def test_use_item_menu_hides_contextually_full_nest_items(monkeypatch):
    fish_name = "UTR\u9c7c"
    locked_fish_name = "\u5f85\u89e3\u9501UTR\u9c7c"
    location = SimpleNamespace(
        id="13", name="13\u56fe", fish_pool=[fish_name, locked_fish_name]
    )
    monkeypatch.setattr(use_checks.ConfigManager, "get_locations", lambda: [location])
    monkeypatch.setattr(
        use_checks.ConfigManager,
        "get_location",
        lambda location_id: location,
    )
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
    status = {"location_id": "13", "time_potions_used": []}
    user = SimpleNamespace(
        items=items,
        bait_id="1",
        fishing_status=status,
        collection={
            fish_name: {"UR": 1, "UTR": 1},
            locked_fish_name: {"UR": 1},
        },
        daily_counters={},
        character_slots=[None, None, None],
        corn=6,
        display_frames=7,
        cat_frames=8,
        star_frames=0,
    )
    scene_id = use_checks.get_scene_instance_id(status, "13")
    context = use_checks.UseCheckContext("user", user)
    context._active_buffs_cache = (
        [
            _buff(
                use_checks.BuffEffect.BUFF_TYPE_NEST,
                use_checks.BuffEffect.TARGET_TYPE_LOCATION,
                scene_id,
            )
            for _ in range(MAX_NEST_LAYERS)
        ]
        + [
            _buff(
                use_checks.BuffEffect.BUFF_TYPE_FRAME,
                use_checks.BuffEffect.TARGET_TYPE_GLOBAL,
            )
            for _ in range(MAX_FRAME_BUFF_LAYERS)
        ]
        + [
            _buff(
                use_checks.BuffEffect.BUFF_TYPE_CAT_NEST,
                use_checks.BuffEffect.TARGET_TYPE_GLOBAL,
            )
            for _ in range(MAX_NEST_LAYERS)
        ]
    )

    state = await item_menu.get_use_item_menu_state("user", context=context)
    commands = {option.command for option in state.options}
    reasons = {item.name: item.reason for item in state.unavailable}

    assert "\u9493\u9c7c\u4f7f\u7528 \u65f6\u5149\u836f\u6c34" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u56de\u6863\u836f\u6c34" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 UTR\u81ea\u9009\u5238" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u5927\u80a5\u9c7c" in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u9999\u751c\u7389\u7c73" not in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u5c55\u793a\u6728\u6846" not in commands
    assert "\u9493\u9c7c\u4f7f\u7528 \u732b\u732b\u6846" not in commands
    assert (
        "\u5f53\u524d\u5730\u70b9\u6253\u7a9d\u6548\u679c\u5df2\u6ee1"
        in reasons["\u9999\u751c\u7389\u7c73"]
    )
    assert "50%" in reasons["\u5c55\u793a\u6728\u6846"]
    assert "50%" in reasons["\u732b\u732b\u6846"]


@pytest.mark.asyncio
async def test_use_item_menu_includes_available_frames_and_corn(monkeypatch):
    location = SimpleNamespace(id="13", name="13\u56fe", fish_pool=[])
    monkeypatch.setattr(
        use_checks.ConfigManager,
        "get_location",
        lambda location_id: location,
    )
    user = SimpleNamespace(
        items={},
        bait_id="0",
        fishing_status={"location_id": "13", "time_potions_used": []},
        collection={},
        daily_counters={},
        character_slots=[None, None, None],
        corn=2,
        display_frames=3,
        cat_frames=4,
        star_frames=0,
    )
    context = use_checks.UseCheckContext("user", user)
    context._active_buffs_cache = []

    state = await item_menu.get_use_item_menu_state("user", context=context)
    labels = {option.label for option in state.options}

    assert "\u9999\u751c\u7389\u7c73\u00d72" in labels
    assert "\u5c55\u793a\u6728\u6846\u00d73" in labels
    assert "\u732b\u732b\u6846\u00d74" in labels


@pytest.mark.asyncio
async def test_shared_reason_matches_menu_and_direct_check():
    user = SimpleNamespace(
        items=dict(
            [
                _item("time_potion", "potion", 2),
                _item("\u8bb8\u613f\u836f\u6c34", "potion", 1),
            ]
        ),
        bait_id="0",
        fishing_status=None,
        collection={},
        daily_counters={},
        character_slots=[None, None, None],
        corn=0,
        display_frames=0,
        cat_frames=0,
        star_frames=3,
    )
    context = use_checks.UseCheckContext("user", user)

    direct = await use_checks.check_item_use(context, "\u65f6\u5149\u836f\u6c34")
    state = await item_menu.get_use_item_menu_state("user", context=context)
    reasons = {item.name: item.reason for item in state.unavailable}
    text = item_menu.format_unavailable_items(state.unavailable)

    assert direct.usable is False
    assert direct.reason == reasons["\u65f6\u5149\u836f\u6c34"]
    unavailable_reason = (
        "\u5f53\u524d\u7248\u672c\u6682\u672a\u5f00\u653e\u4f7f\u7528\u65b9\u5f0f"
    )
    assert reasons["\u8bb8\u613f\u836f\u6c34"] == unavailable_reason
    assert reasons["\u661f\u7a7a\u6846"] == unavailable_reason
    assert "\u65f6\u5149\u836f\u6c34\u00d72" in text
    assert "\u661f\u7a7a\u6846\u00d73" in text


@pytest.mark.asyncio
async def test_shared_context_loads_relevant_buffs_only_once(monkeypatch):
    location = SimpleNamespace(id="13", name="13\u56fe", fish_pool=[])
    monkeypatch.setattr(
        use_checks.ConfigManager,
        "get_location",
        lambda location_id: location,
    )

    class Query:
        async def all(self):
            return []

    filter_mock = Mock(return_value=Query())
    monkeypatch.setattr(use_checks.FishingBuff, "filter", filter_mock)
    user = SimpleNamespace(
        items={},
        bait_id="0",
        fishing_status={"location_id": "13", "time_potions_used": []},
        collection={},
        daily_counters={},
        character_slots=[None, None, None],
        corn=1,
        display_frames=1,
        cat_frames=1,
        star_frames=0,
    )
    context = use_checks.UseCheckContext("user", user)

    checks = await use_checks.get_held_item_use_checks(context)

    assert {check.canonical_name for check in checks} == {
        "\u9999\u751c\u7389\u7c73",
        "\u5c55\u793a\u6728\u6846",
        "\u732b\u732b\u6846",
    }
    assert filter_mock.call_count == 1


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
async def test_utr_ticket_menu_shows_twenty_locked_eligible_fish(monkeypatch):
    locations = [
        SimpleNamespace(id="13", fish_pool=[f"十三鱼{i}" for i in range(1, 13)]),
        SimpleNamespace(id="14", fish_pool=[f"十四鱼{i}" for i in range(1, 13)]),
    ]
    monkeypatch.setattr(use_checks.ConfigManager, "get_locations", lambda: locations)
    collection = {
        fish_name: {"UR": 1}
        for location in locations
        for fish_name in location.fish_pool
    }
    collection["十三鱼1"]["UTR"] = 1
    collection["十四鱼1"]["UTR"] = 1
    user = SimpleNamespace(
        items=dict([_item("utr_select_ticket", "ticket", 2)]),
        collection=collection,
    )
    context = use_checks.UseCheckContext("user", user)

    state = await item_menu.get_utr_ticket_menu_state("user", context=context)

    assert state.ticket_count == 2
    assert len(state.options) == 20
    assert state.options[0].label == "13图 十三鱼2"
    assert state.options[0].command == "钓鱼使用 UTR自选券 十三鱼2"
    commands = {option.command for option in state.options}
    assert "钓鱼使用 UTR自选券 十三鱼1" not in commands
    assert "钓鱼使用 UTR自选券 十四鱼1" not in commands
    assert state.options[-1].label == "14图 十四鱼10"


def test_utr_ticket_menu_builds_two_pages_with_five_by_two_layout(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    options = [
        item_menu.UseItemMenuOption(
            label=f"13图 鱼{i}",
            command=f"钓鱼使用 UTR自选券 鱼{i}",
        )
        for i in range(20)
    ]

    messages = item_menu.build_qq_use_item_messages(
        options,
        title="选择 UTR",
        buttons_per_row=2,
    )

    assert len(messages) == 2
    for message in messages:
        keyboard = message[1][1]
        assert len(keyboard.content.rows) == 5
        assert all(len(row.buttons) == 2 for row in keyboard.content.rows)
        assert all(
            button.action.enter is True
            for row in keyboard.content.rows
            for button in row.buttons
        )
    assert messages[0][1][1].content.rows[0].buttons[0].action.data == (
        "钓鱼使用 UTR自选券 鱼0"
    )
    assert messages[1][0][1].endswith("（2/2）")
