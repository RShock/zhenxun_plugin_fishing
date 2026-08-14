from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.handlers import shop as shop_handler
from zhenxun.plugins.zhenxun_plugin_fishing.items.use_checks import (
    UseCheckContext,
    check_item_use,
)


@pytest.mark.asyncio
async def test_command_rejection_uses_shared_check_reason(monkeypatch):
    user = SimpleNamespace(
        items={"time_potion|potion": {"item_type": "potion", "count": 1}},
        bait_id="0",
        fishing_status=None,
        collection={},
        daily_counters={},
        character_slots=[None, None, None],
        corn=0,
        display_frames=0,
        cat_frames=0,
        star_frames=0,
    )
    expected = await check_item_use(
        UseCheckContext("user", user), "\u65f6\u5149\u836f\u6c34"
    )
    event = Mock()
    event.get_user_id.return_value = "user"
    event.sender = None
    bot = Mock()
    matcher = Mock()
    item_handler = AsyncMock()
    send_text = AsyncMock()
    monkeypatch.setattr(
        shop_handler, "get_or_create_user", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        shop_handler,
        "resolve_item_handler",
        Mock(return_value=(item_handler, False)),
    )
    monkeypatch.setattr(shop_handler, "_send_text", send_text)

    await shop_handler._.__wrapped__(
        bot,
        event,
        matcher,
        ("\u65f6\u5149\u836f\u6c34", None),
    )

    send_text.assert_awaited_once_with(
        matcher,
        expected.reason,
        "user",
        is_private=False,
    )
    item_handler.assert_not_awaited()
