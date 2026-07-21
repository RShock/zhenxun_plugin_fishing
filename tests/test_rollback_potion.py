"""回档药水重新结算时间锚点的专用回归测试。"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.core import actions
from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser
from zhenxun.plugins.zhenxun_plugin_fishing.shop.potion_use import use_rollback_potion


@pytest.mark.asyncio
async def test_rollback_potion_resettles_from_original_start_time(db, monkeypatch):
    user_id = "rollback-potion-full-period"
    user, _ = await FishingUser.get_or_create_user(user_id, "回档测试用户")
    user.frame_pity_counter = 11
    user.cat_frame_pity_counter = 12
    user.utr_pity_counter = 13
    await user.save()
    await FishingUser.add_item(user_id, "回档药水", "potion", 1)

    original_start = (datetime.now() - timedelta(hours=3)).isoformat()
    await FishingUser.update_fishing_status(
        user_id,
        {
            "location_id": "1",
            "start_time": original_start,
            "last_settle_time": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "fish_caught": [{"fish_id": "小鲫鱼", "rarity": "N", "count": 9}],
            "bait_consumed": 9,
            "frame_pity": 99,
            "cat_frame_pity": 98,
            "utr_pity": 97,
            "cat_eaten_fish": [{"fish_id": "草鱼", "rarity": "R", "count": 1}],
            "cat_gifts": {"gold": 100},
        },
    )

    observed_status = None

    async def fake_check_fishing_status(called_user_id):
        nonlocal observed_status
        assert called_user_id == user_id
        observed_status = await FishingUser.get_status(user_id)
        return b"RESETTLED_IMAGE", object()

    check_mock = AsyncMock(side_effect=fake_check_fishing_status)
    monkeypatch.setattr(actions, "check_fishing_status", check_mock)

    success, image = await use_rollback_potion(user_id)

    assert success is True
    assert image == b"RESETTLED_IMAGE"
    check_mock.assert_awaited_once_with(user_id)
    assert observed_status is not None
    assert observed_status["start_time"] == original_start
    assert observed_status["last_settle_time"] == original_start
    assert observed_status["fish_caught"] == []
    assert observed_status["bait_consumed"] == 0
    assert observed_status["frame_pity"] == 11
    assert observed_status["cat_frame_pity"] == 12
    assert observed_status["utr_pity"] == 13
    assert observed_status["cat_eaten_fish"] == []
    assert await FishingUser.get_item(user_id, "回档药水", "potion") is None
