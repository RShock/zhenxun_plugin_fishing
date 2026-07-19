"""时光药水从公开物品入口到收杆结算的行为测试。"""

from datetime import datetime, timedelta

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.core.actions import stop_fishing
from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser
from zhenxun.plugins.zhenxun_plugin_fishing.shop.potion_use import use_time_potion


async def _start_fishing_with_supplies(user_id: str, potion_count: int = 1) -> None:
    user, _ = await FishingUser.get_or_create_user(user_id, "测试用户")
    user.rod_level = 5
    user.hook_level = 3
    user.bait_id = "1"
    await user.save()
    await FishingUser.add_item(user_id, "1", "bait", 1000)
    await FishingUser.add_item(user_id, "time_potion", "potion", potion_count)

    now = datetime.now()
    await FishingUser.update_fishing_status(
        user_id,
        {
            "location_id": "1",
            "start_time": (now - timedelta(minutes=10)).isoformat(),
            "last_settle_time": (now - timedelta(minutes=10)).isoformat(),
            "fish_caught": [],
            "bait_consumed": 0,
            "frame_pity": 0,
            "cat_frame_pity": 0,
            "utr_pity": 0,
            "cat_eaten_fish": [],
            "cat_gifts": {},
        },
    )


@pytest.mark.asyncio
async def test_time_potion_persists_progress_then_end_fishing_applies_rewards(db):
    user_id = "time-potion-flow"
    await _start_fishing_with_supplies(user_id)

    success, image = await use_time_potion(user_id)

    assert success is True
    assert isinstance(image, bytes)
    assert await FishingUser.get_item(user_id, "time_potion", "potion") is None
    bait_after_potion = await FishingUser.get_item(user_id, "1", "bait")
    assert bait_after_potion is not None
    assert bait_after_potion["count"] < 1000

    persisted_status = await FishingUser.get_status(user_id)
    assert persisted_status is not None
    assert persisted_status["fish_caught"]
    assert datetime.fromisoformat(persisted_status["last_settle_time"]) <= datetime.now()

    # 经过一个可结算时段后，从公开收杆入口完成会话并落库奖励。
    persisted_status["last_settle_time"] = (
        datetime.now() - timedelta(hours=2)
    ).isoformat()
    await FishingUser.update_fishing_status(user_id, persisted_status)
    result, messages, is_last_stop = await stop_fishing(user_id, gm_mode=True)

    assert result is not None
    assert isinstance(messages, list)
    assert is_last_stop is False
    assert await FishingUser.get_status(user_id) is None
    collected = await FishingUser.get_user_collected_with_count(user_id)
    assert sum(collected.values()) > 0
    backpack = await FishingUser.get_user_fish(user_id)
    assert sum(fish["count"] for fish in backpack) > 0


@pytest.mark.asyncio
async def test_time_potion_rejection_keeps_inventory_and_state(db):
    user_id = "time-potion-no-fishing"
    await FishingUser.add_item(user_id, "time_potion", "potion", 2)

    success, message = await use_time_potion(user_id, 2)

    assert success is False
    assert "还没有在钓鱼" in message
    potion = await FishingUser.get_item(user_id, "time_potion", "potion")
    assert potion == {"item_id": "time_potion", "item_type": "potion", "count": 2}
    assert await FishingUser.get_status(user_id) is None
