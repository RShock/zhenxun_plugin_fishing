from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.backpack import black_market
from zhenxun.plugins.zhenxun_plugin_fishing.items import potion_use, use_checks


@pytest.mark.asyncio
async def test_utr_preflight_rejects_already_unlocked_target(monkeypatch):
    target = SimpleNamespace(
        name="目标鱼",
        location_id="13",
        location_name="测试地图",
    )
    location = SimpleNamespace(id="13", fish_pool=["已解锁鱼", "目标鱼"])
    monkeypatch.setattr(use_checks, "_find_utr_target", lambda name: (name, target))
    monkeypatch.setattr(
        use_checks.ConfigManager, "get_location", lambda location_id: location
    )
    user = SimpleNamespace(
        items={
            "utr_select_ticket|ticket": {
                "item_type": "ticket",
                "count": 1,
            }
        },
        collection={
            "已解锁鱼": {"UR": 1, "UTR": 1},
            "目标鱼": {"UR": 1, "UTR": 1},
        },
    )
    context = use_checks.UseCheckContext("user", user)

    result = await use_checks.check_item_use(context, "UTR自选券", arg="目标鱼")

    assert result.usable is False
    assert "已解锁" in result.reason


@pytest.mark.asyncio
async def test_utr_runtime_recheck_does_not_consume_ticket(monkeypatch):
    target = SimpleNamespace(
        name="目标鱼",
        location_id="13",
        location_name="测试地图",
        numeric_id=1,
        scene_level=13,
    )
    monkeypatch.setattr(potion_use, "get_or_create_user", AsyncMock())
    monkeypatch.setattr(
        potion_use.FishingUser,
        "get_item",
        AsyncMock(return_value={"count": 1}),
    )
    monkeypatch.setattr(
        potion_use.FishingUser,
        "get_user_collected",
        AsyncMock(return_value={("目标鱼", "UTR")}),
    )
    remove_item = AsyncMock(return_value=True)
    monkeypatch.setattr(potion_use.FishingUser, "remove_item", remove_item)
    monkeypatch.setattr(black_market, "find_fish_target", lambda name, rarity: target)

    success, message = await potion_use.use_utr_select_ticket("user", arg="目标鱼")

    assert success is False
    assert "已解锁" in message
    remove_item.assert_not_awaited()
