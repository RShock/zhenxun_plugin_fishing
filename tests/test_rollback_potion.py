"""回档药水重新结算时间锚点的专用回归测试。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.core import actions
from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser
from zhenxun.plugins.zhenxun_plugin_fishing.render import fishing_status
from zhenxun.plugins.zhenxun_plugin_fishing.items.potion_use import use_rollback_potion


@pytest.mark.asyncio
async def test_fishing_status_omits_accumulated_starry_score(monkeypatch):
    captured = {}

    def capture_template(template, **context):
        captured["template"] = template
        captured["context"] = context
        return "<html></html>"

    monkeypatch.setattr(fishing_status, "render_template", capture_template)
    monkeypatch.setattr(
        fishing_status, "render_html", AsyncMock(return_value=b"STATUS_IMAGE")
    )
    monkeypatch.setattr(fishing_status, "save_debug_output", lambda *args: None)

    result = await fishing_status.render_fishing_status(
        user_id="starry-score-user",
        location=SimpleNamespace(id="1", name="测试湖", difficulty=1),
        total_duration_min=1,
        total_fish=[],
        new_fish=[],
        total_bait_consumed=0,
        new_bait_consumed=0,
        probabilities={},
    )

    assert result == b"STATUS_IMAGE"
    assert captured["template"] == "fishing_status.html"
    assert "starry_score_accumulated" not in captured["context"]
    template = (
        Path(fishing_status.__file__).parent.parent
        / "templates"
        / "fishing_status.html"
    ).read_text(encoding="utf-8")
    assert "星空鱼分数" not in template


@pytest.mark.asyncio
async def test_rollback_potion_resettles_from_original_start_time(db, monkeypatch):
    user_id = "rollback-potion-full-period"
    user, _ = await FishingUser.get_or_create_user(user_id, "回档测试用户")
    user.frame_pity_counter = 11
    user.cat_frame_pity_counter = 12
    user.utr_pity_counter = 13
    await user.save()
    await FishingUser.add_item(user_id, "回档药水", "potion", 1)
    await FishingUser.add_item(user_id, "1", "bait", 10)

    original_start = (datetime.now() - timedelta(hours=3)).isoformat()
    await FishingUser.update_fishing_status(
        user_id,
        {
            "location_id": "1",
            "start_time": original_start,
            "last_settle_time": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "fish_caught": [{"fish_id": "小鲫鱼", "rarity": "N", "count": 9}],
            "bait_consumed": 9,
            "bait_usage_log": {"1": 9},
            "frame_pity": 99,
            "cat_frame_pity": 98,
            "utr_pity": 97,
            "cat_eaten_fish": [{"fish_id": "草鱼", "rarity": "R", "count": 1}],
            "cat_gifts": {"gold": 100},
            "time_potions_used": 3,
            "shadow_scene": True,
        },
    )

    observed_status = None

    async def fake_check_fishing_status(called_user_id):
        nonlocal observed_status
        assert called_user_id == user_id
        observed_status = await FishingUser.get_status(user_id)
        return b"RESETTLED_IMAGE", object()

    check_mock = AsyncMock(side_effect=fake_check_fishing_status)
    stop_mock = AsyncMock(side_effect=AssertionError("回档药水不应调用收杆"))
    get_daily_mock = AsyncMock(
        side_effect=AssertionError("回档药水不应读取每日状态次数")
    )
    increment_daily_mock = AsyncMock(
        side_effect=AssertionError("回档药水不应写入每日状态次数")
    )
    monkeypatch.setattr(actions, "check_fishing_status", check_mock)
    monkeypatch.setattr(actions, "stop_fishing", stop_mock)
    monkeypatch.setattr(FishingUser, "get_status_count", get_daily_mock)
    monkeypatch.setattr(FishingUser, "increment_status_count", increment_daily_mock)

    success, image = await use_rollback_potion(user_id)

    assert success is True
    assert image == b"RESETTLED_IMAGE"
    check_mock.assert_awaited_once_with(user_id)
    stop_mock.assert_not_awaited()
    get_daily_mock.assert_not_awaited()
    increment_daily_mock.assert_not_awaited()
    assert observed_status is not None
    assert observed_status["start_time"] == original_start
    assert observed_status["last_settle_time"] == original_start
    assert observed_status["fish_caught"] == []
    assert observed_status["bait_consumed"] == 0
    assert observed_status["frame_pity"] == 11
    assert observed_status["cat_frame_pity"] == 12
    assert observed_status["utr_pity"] == 13
    assert observed_status["cat_eaten_fish"] == []
    assert observed_status["time_potions_used"] == 0
    assert observed_status["shadow_scene"] is True
    assert observed_status["bait_usage_log"] == {}
    # 回档应按 bait_usage_log 退还鱼饵，避免重新结算时重复扣除
    bait_item = await FishingUser.get_item(user_id, "1", "bait")
    assert bait_item is not None
    assert bait_item["count"] == 19  # 10 原有 + 9 退还
    assert await FishingUser.get_item(user_id, "回档药水", "potion") is None
    refunded = await FishingUser.get_item(user_id, "time_potion", "potion")
    assert refunded == {"item_id": "time_potion", "item_type": "potion", "count": 3}


@pytest.mark.asyncio
async def test_rollback_potion_only_rolls_back_last_24h(db, monkeypatch):
    """会话超过 24h 时，回档药水只回溯最近 24 小时的鱼获。

    验证：
    - 24h 前的鱼获保留（catch_time 早于截止点）
    - 24h 内的鱼获被移除
    - last_settle_time 设为 24h 前（不是 start_time）
    - 鱼饵按比例退还（不是全额）
    - 时光药水不退还（会话 > 24h）
    """
    user_id = "rollback-potion-24h-limit"
    user, _ = await FishingUser.get_or_create_user(user_id, "24h回档测试")
    user.frame_pity_counter = 50
    user.cat_frame_pity_counter = 5
    user.utr_pity_counter = 30
    await user.save()
    await FishingUser.add_item(user_id, "回档药水", "potion", 1)
    await FishingUser.add_item(user_id, "1", "bait", 10)

    now = datetime.now()
    start_30h_ago = (now - timedelta(hours=30)).isoformat()
    fish_25h_ago = (now - timedelta(hours=25)).isoformat()
    fish_1h_ago = (now - timedelta(hours=1)).isoformat()
    cutoff_24h_ago = (now - timedelta(hours=24)).isoformat()

    await FishingUser.update_fishing_status(
        user_id,
        {
            "location_id": "1",
            "start_time": start_30h_ago,
            "last_settle_time": fish_1h_ago,
            # 25h前的鱼（保留）+ 1h前的鱼（移除）
            "fish_caught": [
                {"fish_id": "小鲫鱼", "rarity": "N", "count": 5, "catch_time": fish_25h_ago},
                {"fish_id": "鲤鱼", "rarity": "R", "count": 3, "catch_time": fish_1h_ago},
            ],
            "bait_consumed": 8,
            "bait_usage_log": {"1": 8},
            "frame_pity": 50,
            "cat_frame_pity": 5,
            "utr_pity": 30,
            "cat_eaten_fish": [
                {"fish_id": "草鱼", "rarity": "R", "count": 1, "catch_time": fish_25h_ago},
                {"fish_id": "麦穗鱼", "rarity": "N", "count": 2, "catch_time": fish_1h_ago},
            ],
            "cat_gifts": {"gold": 100},
            "time_potions_used": 2,
        },
    )

    observed_status = None

    async def fake_check_fishing_status(called_user_id):
        nonlocal observed_status
        observed_status = await FishingUser.get_status(user_id)
        return b"PARTIAL_RESETTLED_IMAGE", object()

    check_mock = AsyncMock(side_effect=fake_check_fishing_status)
    stop_mock = AsyncMock(side_effect=AssertionError("回档药水不应调用收杆"))
    monkeypatch.setattr(actions, "check_fishing_status", check_mock)
    monkeypatch.setattr(actions, "stop_fishing", stop_mock)

    success, image = await use_rollback_potion(user_id)

    assert success is True
    assert image == b"PARTIAL_RESETTLED_IMAGE"
    check_mock.assert_awaited_once_with(user_id)
    stop_mock.assert_not_awaited()
    assert observed_status is not None

    # start_time 保持不变
    assert observed_status["start_time"] == start_30h_ago

    # last_settle_time 应为 24h 前（不是 start_time）
    observed_last_settle = datetime.fromisoformat(observed_status["last_settle_time"])
    expected_cutoff = now - timedelta(hours=24)
    delta = abs((observed_last_settle - expected_cutoff).total_seconds())
    assert delta < 5, f"last_settle_time 偏差过大: {delta}s"

    # 25h 前的鱼获保留
    kept_fish = observed_status["fish_caught"]
    assert len(kept_fish) == 1
    assert kept_fish[0]["fish_id"] == "小鲫鱼"
    assert kept_fish[0]["count"] == 5

    # 25h 前的猫吃鱼保留
    kept_cat_eaten = observed_status["cat_eaten_fish"]
    assert len(kept_cat_eaten) == 1
    assert kept_cat_eaten[0]["fish_id"] == "草鱼"

    # 时光药水不退还（会话 > 24h）
    assert observed_status["time_potions_used"] == 2
    time_potion_item = await FishingUser.get_item(user_id, "time_potion", "potion")
    assert time_potion_item is None  # 没有退还

    # 鱼饵按比例退还：被移除鱼数=3+2=5，总鱼数=5+3+1+2=11，比例≈0.4545
    # refund = round(8 * 0.4545) = round(3.636) = 4
    # new_bait_usage_log = {"1": 8 - 4} = {"1": 4}
    assert observed_status["bait_usage_log"] == {"1": 4}
    bait_item = await FishingUser.get_item(user_id, "1", "bait")
    assert bait_item is not None
    assert bait_item["count"] == 14  # 10 原有 + 4 退还

    # 回档药水已消耗
    assert await FishingUser.get_item(user_id, "回档药水", "potion") is None
