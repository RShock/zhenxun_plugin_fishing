"""Isolation guarantees for the hidden -11 fishing scene."""

from datetime import datetime, timedelta

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.models import BuffEffect, FishingUser
from zhenxun.plugins.zhenxun_plugin_fishing.scene_instance import (
    get_scene_instance_id,
)
from zhenxun.plugins.zhenxun_plugin_fishing.shop.nest import do_nest
from zhenxun.plugins.zhenxun_plugin_fishing.items.potion_use import use_time_potion

SHADOW_USER_ID = "418648118"


def test_legacy_shadow_status_resolves_to_isolated_instance():
    assert get_scene_instance_id({"location_id": "11", "shadow_scene": True}) == "-11"


async def _prepare_shadow_session(db, *, corn: int = 0, potions: int = 0) -> None:
    user = await db.user_get(SHADOW_USER_ID)
    user.rod_level = 10
    user.hook_level = 3
    user.bait_id = "1"
    user.corn = corn
    await FishingUser.add_item(SHADOW_USER_ID, "1", "bait", 2000)
    if potions:
        await FishingUser.add_item(SHADOW_USER_ID, "time_potion", "potion", potions)
    now = datetime.now()
    await FishingUser.update_fishing_status(
        SHADOW_USER_ID,
        {
            "location_id": "11",
            "scene_instance_id": "-11",
            "shadow_scene": True,
            "start_time": (now - timedelta(minutes=10)).isoformat(),
            "last_settle_time": (now - timedelta(minutes=10)).isoformat(),
            "fish_caught": [],
            "bait_consumed": 0,
            "frame_pity": 0,
            "cat_frame_pity": 0,
            "utr_pity": 0,
            "cat_eaten_fish": [],
            "cat_gifts": {},
            "time_potions_used": 0,
        },
    )


@pytest.mark.asyncio
async def test_shadow_nest_does_not_modify_positive_map_11(db):
    await _prepare_shadow_session(db, corn=1)

    success, _ = await do_nest(SHADOW_USER_ID)

    assert success is True
    assert await db.buff_get_location_buff_count("-11") == 1
    assert await db.buff_get_location_buff_count("11") == 0


@pytest.mark.asyncio
async def test_shadow_settlement_uses_only_shadow_nest_but_keeps_map_weather(db):
    now = datetime.now()
    await db.buff_add_location_buff("11", BuffEffect.BUFF_TYPE_NEST, 8, value=5)
    await db.buff_add_location_buff("-11", BuffEffect.BUFF_TYPE_NEST, 8, value=5)
    await db.buff_add_location_buff(
        "11", BuffEffect.BUFF_TYPE_WEATHER_SOLAR_WIND, 8, value=2.5
    )

    buffs = await db.buff_get_active_buffs_for_fishing(
        SHADOW_USER_ID,
        "11",
        now - timedelta(minutes=1),
        now + timedelta(minutes=1),
        location_buff_target_id="-11",
    )

    nest_targets = [
        b.target_id for b in buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST
    ]
    assert nest_targets == ["-11"]
    assert any(
        b.target_id == "11" and b.buff_type == BuffEffect.BUFF_TYPE_WEATHER_SOLAR_WIND
        for b in buffs
    )


@pytest.mark.asyncio
async def test_time_potion_works_without_losing_shadow_isolation(db):
    await _prepare_shadow_session(db, potions=1)

    success, image = await use_time_potion(SHADOW_USER_ID)

    assert success is True
    assert isinstance(image, bytes)
    status = await FishingUser.get_status(SHADOW_USER_ID)
    assert status is not None
    assert status["location_id"] == "11"
    assert status["scene_instance_id"] == "-11"
    assert status["shadow_scene"] is True
    assert isinstance(status["time_potions_used"], list)
    assert len(status["time_potions_used"]) == 1
