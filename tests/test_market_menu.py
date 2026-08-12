from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.backpack import black_market
from zhenxun.plugins.zhenxun_plugin_fishing.backpack.black_market import (
    FishTarget,
    MarketMenuOption,
)
from zhenxun.plugins.zhenxun_plugin_fishing.handlers import market_menu

BLACK_MARKET = chr(0x9ED1) + chr(0x5546)
WHITE_MARKET_EXCHANGE = chr(0x767D) + chr(0x5546) + chr(0x4EA4) + chr(0x6362)


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
    monkeypatch.setitem(sys.modules, "nonebot.adapters.qq.models.common", common_module)


def _fish(
    name: str,
    rarity: str,
    location_id: str,
    scene_level: int,
    numeric_id: str,
) -> FishTarget:
    return FishTarget(
        name=name,
        rarity=rarity,
        location_id=location_id,
        location_name=f"Location{location_id}",
        scene_level=scene_level,
        fish_index=1,
        numeric_id=numeric_id,
    )


@pytest.mark.asyncio
async def test_black_market_menu_filters_and_sorts(monkeypatch):
    source_utr = _fish("SourceUTR", "UTR", "3", 3, "311")
    source_ur = _fish("SourceUR", "UR", "2", 2, "214")
    same_map_utr = _fish("SameMapUTR", "UTR", "3", 2, "321")
    cross_map_utr = _fish("CrossMapUTR", "UTR", "1", 1, "121")
    same_map_ur = _fish("SameMapUR", "UR", "2", 1, "224")
    collected_ur = _fish("CollectedUR", "UR", "2", 1, "234")
    invalid_high_scene = _fish("HighSceneUR", "UR", "4", 4, "414")

    monkeypatch.setattr(
        black_market.FishingUser,
        "get_user_fish",
        AsyncMock(
            return_value=[
                {
                    "numeric_id": source_utr.numeric_id,
                    "fish_name": source_utr.name,
                    "rarity": source_utr.rarity,
                    "count": 1,
                },
                {
                    "numeric_id": source_ur.numeric_id,
                    "fish_name": source_ur.name,
                    "rarity": source_ur.rarity,
                    "count": 1,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        black_market.FishingUser,
        "get_user_collected",
        AsyncMock(return_value={(collected_ur.name, collected_ur.rarity)}),
    )
    by_id = {
        source_utr.numeric_id: source_utr,
        source_ur.numeric_id: source_ur,
    }
    monkeypatch.setattr(
        black_market,
        "find_fish_target_by_numeric_id",
        lambda numeric_id: by_id.get(numeric_id),
    )
    targets = {
        "UTR": [source_utr, same_map_utr, cross_map_utr],
        "UR": [source_ur, same_map_ur, collected_ur, invalid_high_scene],
    }
    monkeypatch.setattr(
        black_market,
        "_iter_fish_targets",
        lambda rarity: iter(targets[rarity]),
    )

    options = await black_market.get_black_market_menu_options("user")

    assert [(item.source.name, item.target.name) for item in options] == [
        ("SourceUTR", "SameMapUTR"),
        ("SourceUR", "SameMapUR"),
        ("SourceUTR", "CrossMapUTR"),
    ]
    assert all(item.source.rarity == item.target.rarity for item in options)
    assert all("CollectedUR" not in item.command for item in options)
    assert options[0].command == f"{BLACK_MARKET} SourceUTRUTR SameMapUTRUTR"


@pytest.mark.asyncio
async def test_white_market_menu_only_uses_current_eligibility(monkeypatch):
    payment = _fish("Payment", "UR", "2", 2, "214")
    same_map = _fish("SameTarget", "UTR", "2", 2, "225")
    cross_map = _fish("CrossTarget", "UTR", "1", 1, "125")
    eligibility = SimpleNamespace(
        exhausted=False,
        payments=(
            SimpleNamespace(
                numeric_id=payment.numeric_id,
                fish_name=payment.name,
                rarity=payment.rarity,
                targets=(
                    SimpleNamespace(
                        numeric_id=cross_map.numeric_id,
                        fish_name=cross_map.name,
                        rarity=cross_map.rarity,
                    ),
                    SimpleNamespace(
                        numeric_id=same_map.numeric_id,
                        fish_name=same_map.name,
                        rarity=same_map.rarity,
                    ),
                ),
            ),
        ),
    )
    service = sys.modules[
        "zhenxun.plugins.zhenxun_plugin_fishing.services.white_market_service"
    ]
    monkeypatch.setattr(
        service,
        "get_white_market_eligibility",
        AsyncMock(return_value=eligibility),
    )
    by_id = {
        payment.numeric_id: payment,
        same_map.numeric_id: same_map,
        cross_map.numeric_id: cross_map,
    }
    monkeypatch.setattr(
        black_market,
        "find_fish_target_by_numeric_id",
        lambda numeric_id: by_id.get(numeric_id),
    )

    options = await black_market.get_white_market_menu_options("user")

    assert [item.target.name for item in options] == ["SameTarget", "CrossTarget"]
    assert options[0].command == f"{WHITE_MARKET_EXCHANGE} PaymentUR SameTargetUTR"


def test_market_menu_splits_ten_options_into_two_proactive_messages(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    source = _fish("Source", "UR", "2", 2, "214")
    options = [
        MarketMenuOption(
            source=source,
            target=_fish(f"Target{i}", "UR", "2", 1, f"2{i}4"),
            command=f"{BLACK_MARKET} SourceUR Target{i}UR",
        )
        for i in range(10)
    ]

    messages = market_menu.build_qq_market_messages(options)

    assert len(messages) == 2
    for message in messages:
        keyboard = message[1][1]
        assert len(keyboard.content.rows) == 5
        for row in keyboard.content.rows:
            assert len(row.buttons) == 1
            assert row.buttons[0].action.enter is True
            assert row.buttons[0].action.type == 2
    assert messages[0][1][1].content.rows[0].buttons[0].action.data == (
        f"{BLACK_MARKET} SourceUR Target0UR"
    )


@pytest.mark.asyncio
async def test_market_menu_uses_fully_proactive_send(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    option = MarketMenuOption(
        source=_fish("Source", "UR", "2", 2, "214"),
        target=_fish("Target", "UR", "2", 1, "224"),
        command=f"{BLACK_MARKET} SourceUR TargetUR",
    )
    send_to_group = AsyncMock()
    bot = SimpleNamespace(send_to_group=send_to_group)
    event = SimpleNamespace(group_openid="group-open-id", author=object())

    sent = await market_menu.try_send_market_menu(
        bot,
        event,
        options=[option],
    )

    assert sent is True
    send_to_group.assert_awaited_once()
    assert send_to_group.await_args.kwargs.keys() == {"group_openid", "message"}
    assert send_to_group.await_args.kwargs["group_openid"] == "group-open-id"


def test_market_menu_with_no_options_builds_no_messages():
    assert market_menu.build_qq_market_messages([]) == []


def test_market_menu_with_five_options_builds_one_message(monkeypatch):
    _install_fake_qq_adapter(monkeypatch)
    source = _fish("Source", "UR", "2", 2, "214")
    options = [
        MarketMenuOption(
            source=source,
            target=_fish(f"Target{i}", "UR", "2", 1, f"2{i}4"),
            command=f"{BLACK_MARKET} SourceUR Target{i}UR",
        )
        for i in range(5)
    ]

    messages = market_menu.build_qq_market_messages(options)

    assert len(messages) == 1
    assert messages[0][0] == ("markdown", "\u200b")
    keyboard = messages[0][1][1]
    assert len(keyboard.content.rows) == 5


def test_button_label_contains_both_rarities_and_ascii_separator():
    option = MarketMenuOption(
        source=_fish("GoldFish", "UTR", "2", 2, "214"),
        target=_fish("SilverFish", "UTR", "2", 1, "224"),
        command=f"{BLACK_MARKET} GoldFishUTR SilverFishUTR",
    )

    label = market_menu._button_label(option)

    assert len(label) <= 10
    assert label.count("UTR") == 2
    assert ">" in label
    assert "?" not in label


@pytest.mark.asyncio
async def test_empty_market_menu_does_not_send(monkeypatch):
    send_to_group = AsyncMock()
    bot = SimpleNamespace(send_to_group=send_to_group)
    event = SimpleNamespace(group_openid="group-open-id", author=object())

    sent = await market_menu.try_send_market_menu(
        bot,
        event,
        options=[],
    )

    assert sent is False
    send_to_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_black_market_without_options_uses_legacy_text(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing.handlers import backpack

    monkeypatch.setattr(
        backpack, "_ensure_user", AsyncMock(return_value=("user", None))
    )
    monkeypatch.setattr(backpack, "_is_private_chat", lambda _event: False)
    monkeypatch.setattr(
        backpack, "get_black_market_menu_options", AsyncMock(return_value=[])
    )
    send_menu = AsyncMock(return_value=True)
    monkeypatch.setattr(backpack, "try_send_market_menu", send_menu)
    exchange = AsyncMock(return_value=(False, "legacy usage", True))
    monkeypatch.setattr(backpack, "black_market_exchange", exchange)
    send_text = AsyncMock()
    monkeypatch.setattr(backpack, "_send_text", send_text)
    event = SimpleNamespace(get_plaintext=lambda: BLACK_MARKET)

    handler = getattr(
        backpack._handle_black_market, "__wrapped__", backpack._handle_black_market
    )
    matcher = SimpleNamespace()
    await handler(SimpleNamespace(), event, matcher, group=("",))

    send_menu.assert_not_awaited()
    exchange.assert_awaited_once_with("user", "")
    send_text.assert_awaited_once_with(
        matcher, "legacy usage", "user", is_private=False
    )


@pytest.mark.asyncio
async def test_white_market_without_options_uses_legacy_image(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing.handlers import backpack

    matcher = SimpleNamespace()
    monkeypatch.setattr(
        backpack, "_ensure_user", AsyncMock(return_value=("user", None))
    )
    monkeypatch.setattr(backpack, "_is_private_chat", lambda _event: False)
    monkeypatch.setattr(
        backpack, "get_white_market_menu_options", AsyncMock(return_value=[])
    )
    send_menu = AsyncMock(return_value=True)
    monkeypatch.setattr(backpack, "try_send_market_menu", send_menu)
    monkeypatch.setattr(
        backpack, "render_white_market_records", AsyncMock(return_value=b"image")
    )
    send_image = AsyncMock()
    monkeypatch.setattr(backpack, "_send_image", send_image)

    await backpack._handle_white_market(SimpleNamespace(), SimpleNamespace(), matcher)

    send_menu.assert_not_awaited()
    send_image.assert_awaited_once_with(
        matcher, b"image", user_id="user", is_private=False
    )


@pytest.mark.asyncio
async def test_white_market_with_options_does_not_render_legacy_image(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing.handlers import backpack

    option = MarketMenuOption(
        source=_fish("Payment", "UR", "2", 2, "214"),
        target=_fish("Target", "UTR", "1", 1, "125"),
        command=f"{WHITE_MARKET_EXCHANGE} PaymentUR TargetUTR",
    )
    monkeypatch.setattr(
        backpack, "_ensure_user", AsyncMock(return_value=("user", None))
    )
    monkeypatch.setattr(backpack, "_is_private_chat", lambda _event: False)
    monkeypatch.setattr(
        backpack, "get_white_market_menu_options", AsyncMock(return_value=[option])
    )
    send_menu = AsyncMock(return_value=True)
    monkeypatch.setattr(backpack, "try_send_market_menu", send_menu)
    render_image = AsyncMock(return_value=b"image")
    monkeypatch.setattr(backpack, "render_white_market_records", render_image)
    send_image = AsyncMock()
    monkeypatch.setattr(backpack, "_send_image", send_image)

    bot = SimpleNamespace()
    event = SimpleNamespace()
    matcher = SimpleNamespace()
    await backpack._handle_white_market(bot, event, matcher)

    send_menu.assert_awaited_once_with(bot, event, options=[option])
    render_image.assert_not_awaited()
    send_image.assert_not_awaited()
