"""公告系统：群发间隔与星空艇播报条件。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_broadcast_sleeps_between_groups():
    from zhenxun.plugins.zhenxun_plugin_fishing.services import announcement_service as svc

    bot = MagicMock()
    # None 表示路由层拒绝/不可用；成功发送应返回消息结果。
    bot.call_api = AsyncMock(return_value={"message_id": 1})
    sleep = AsyncMock()

    with (
        patch.object(svc.FishingActiveGroup, "get_active_group_ids", AsyncMock(return_value=["1", "2", "3"])),
        patch.object(svc, "get_bot", return_value=bot),
        patch.object(svc.asyncio, "sleep", sleep),
    ):
        success, fail = await svc.broadcast_to_active_groups("hello")

    assert success == 3
    assert fail == 0
    assert bot.call_api.await_count == 3
    # 3 个群只 sleep 2 次（最后一组后不再 sleep）
    assert sleep.await_count == 2
    sleep.assert_awaited_with(0.3)


@pytest.mark.asyncio
async def test_starry_announce_regular_layer():
    from zhenxun.plugins.zhenxun_plugin_fishing.services import announcement_service as svc

    auto = AsyncMock()
    with patch.object(svc, "auto_announce", auto):
        # 该函数只在建设成功后调用，因此每次调用都应公告。
        await svc.announce_starry_ship_build("u2", "乙", 3)
        auto.assert_awaited_once()
        msg = auto.await_args.args[0]
        assert "乙" in msg
        assert "+15%" in msg
        assert "迷途风" not in msg


@pytest.mark.asyncio
async def test_starry_announce_max_layer_only_on_tenth():
    from zhenxun.plugins.zhenxun_plugin_fishing.services import announcement_service as svc

    auto = AsyncMock()
    with patch.object(svc, "auto_announce", auto):
        await svc.announce_starry_ship_build("u3", "丙", 10)
        auto.assert_awaited_once()
        msg = auto.await_args.args[0]
        assert "丙" in msg
        assert "10 层上限" in msg
        assert "迷途风" in msg
