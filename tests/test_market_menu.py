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

    messages = market_menu.build_qq_market_messages(BLACK_MARKET, options)

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
        title=BLACK_MARKET,
        options=[option],
        empty_text="None",
    )

    assert sent is True
    send_to_group.assert_awaited_once()
    assert send_to_group.await_args.kwargs.keys() == {"group_openid", "message"}
    assert send_to_group.await_args.kwargs["group_openid"] == "group-open-id"
