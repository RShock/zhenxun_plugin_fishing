"""迭代四热点重构的兼容与集成测试。"""

from datetime import datetime, timedelta
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing import status_api
from zhenxun.plugins.zhenxun_plugin_fishing.render import fishing_scene, fishing_status


def test_public_render_signatures_remain_compatible():
    scene_params = inspect.signature(fishing_scene.render_fishing_scene).parameters
    status_params = inspect.signature(fishing_status.render_fishing_status).parameters

    assert list(scene_params)[:8] == [
        "location",
        "players",
        "current_user_id",
        "hints",
        "nest_speed_bonus",
        "bait_name",
        "bait_count",
        "fishing_power",
    ]
    assert list(status_params)[:10] == [
        "user_id",
        "location",
        "total_duration_min",
        "total_fish",
        "new_fish",
        "total_bait_consumed",
        "new_bait_consumed",
        "probabilities",
        "bait",
        "buff_messages",
    ]
    assert scene_params["weather_info"].default is None
    assert scene_params["scene_inverted"].default is False
    assert status_params["weather_info"].default is None


def test_shadow_scene_template_rotates_the_complete_card():
    template = (
        Path(fishing_scene.__file__).parent.parent / "templates" / "fishing_scene.html"
    ).read_text(encoding="utf-8")

    assert ".sw.scene-inverted { transform:rotate(180deg);" in template
    assert 'class="sw{% if scene_inverted %} scene-inverted{% endif %}"' in template


@pytest.mark.asyncio
async def test_scene_renderer_forwards_shadow_scene_flag(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing.core import scene

    now = datetime.now()
    location = SimpleNamespace(
        id="11",
        name="shadow-lake",
        difficulty=11,
        max_rarity="UTR",
        fish_pool=[],
    )
    user = SimpleNamespace(
        rod_level=11,
        hook_level=0,
        bait_id="0",
        achievements=["collect_scene_11"],
    )
    render_mock = AsyncMock(return_value=b"SHADOW_IMAGE")

    monkeypatch.setattr(scene, "collect_scene_players", AsyncMock(return_value=[]))
    monkeypatch.setattr(scene, "get_location_weather", AsyncMock(return_value={}))
    monkeypatch.setattr(
        scene.FishingWeather, "get_today_weather", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        scene.FishingBuff, "get_location_buff_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        scene.FishingBuff,
        "get_frame_buff_count_for_location",
        AsyncMock(return_value=0),
    )

    class _NoBuffQuery:
        async def first(self):
            return None

    monkeypatch.setattr(scene.FishingBuff, "filter", lambda **kwargs: _NoBuffQuery())
    monkeypatch.setattr(scene.FishingUser, "get_user", AsyncMock(return_value=user))
    monkeypatch.setattr(scene, "get_bait_info", AsyncMock(return_value=("", 0, 0)))
    monkeypatch.setattr(scene, "calculate_display_probabilities", lambda *a, **k: {})
    monkeypatch.setattr(
        scene.FishingUser,
        "get_status",
        AsyncMock(
            return_value={
                "location_id": "11",
                "start_time": now.isoformat(),
                "shadow_scene": True,
            }
        ),
    )
    monkeypatch.setattr(
        scene.FishingBuff,
        "get_active_buffs_for_fishing",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(scene, "render_fishing_scene", render_mock)

    assert await scene.render_scene("418648118", location) == b"SHADOW_IMAGE"
    assert render_mock.await_args.kwargs["scene_inverted"] is True


def test_scene_preparation_handles_defaults_and_boundary_weather(monkeypatch):
    monkeypatch.setattr(
        fishing_scene, "_find_weather_overlay", lambda _: "file:///rain.png"
    )

    default_weather = fishing_scene._build_weather_view(None)
    inactive = fishing_scene._build_weather_view(
        {
            "weather_type": "cat",
            "is_active": False,
            "start_time": datetime(2026, 1, 1, 23),
            "end_time": datetime(2026, 1, 2, 0),
        }
    )
    probabilities = fishing_scene._build_probability_items({"N": 0.5, "SSR": 0.125})

    assert (default_weather.name, default_weather.active) == ("晴天", True)
    assert inactive.time == "23点-24点"
    assert inactive.active is False
    assert inactive.overlay_uri == ""
    assert probabilities == [
        {"rk": "N", "color": "#9e9e9e", "pct": "50.0"},
        {"rk": "SSR", "color": "#ff9800", "pct": "12.5"},
    ]


def test_status_timeline_preserves_key_structure_and_clips_boundaries():
    start = datetime(2026, 1, 1, 10)
    buff = SimpleNamespace(
        buff_type="unknown_buff",
        value=0,
        start_time=start - timedelta(hours=1),
        end_time=start + timedelta(hours=3),
    )

    timeline = fishing_status._build_buff_timeline(
        [buff], start, start + timedelta(hours=1), start + timedelta(hours=2)
    )

    assert timeline is not None
    assert set(timeline) == {
        "rows",
        "time_markers",
        "legend",
        "fishing_start_pct",
        "current_time_pct",
    }
    assert timeline["fishing_start_pct"] == 0.0
    assert timeline["current_time_pct"] is None
    assert timeline["rows"] == [
        {
            "color": "#999999",
            "segments": [{"left_pct": 0.0, "width_pct": 100.0}],
        }
    ]
    assert fishing_status._build_buff_timeline([], start, start) is None


def test_status_timeline_includes_future_buffs_and_elapsed_overlay():
    """延后模式产生的未开始 buff 也应显示在时间轴上，且已过区间有 current_time_pct。"""
    now = datetime(2026, 1, 1, 12, 0)
    fishing_start = now - timedelta(hours=1)

    # 一个已经结束的 buff、一个正在生效的 buff、一个尚未开始的 buff（延后模式）
    past_buff = SimpleNamespace(
        buff_type="duoduo",
        value=2,
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(minutes=30),
    )
    active_buff = SimpleNamespace(
        buff_type="lucky_double",
        value=1,
        start_time=now - timedelta(minutes=30),
        end_time=now + timedelta(hours=4),
    )
    future_buff = SimpleNamespace(
        buff_type="flash",
        value=1,
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=6),
    )

    # end_time=None → 钓鱼状态模式：窗口 [fishing_start-1h, now+8h]
    timeline = fishing_status._build_buff_timeline(
        [past_buff, active_buff, future_buff],
        fishing_start,
        now,
    )

    assert timeline is not None
    # current_time_pct 应有值（用于已过区间蒙版宽度）
    assert timeline["current_time_pct"] is not None
    assert 0 < timeline["current_time_pct"] < 100

    # 收集所有 segment 的 left_pct，验证未来 buff 出现在时间轴后半段
    all_segments = []
    for row in timeline["rows"]:
        all_segments.extend(row["segments"])

    # 未来 buff 的 segment 的 left_pct 应大于 current_time_pct
    future_segments = [s for s in all_segments if s["left_pct"] > timeline["current_time_pct"]]
    assert len(future_segments) > 0, "未来 buff 应在时间轴中显示"


@pytest.mark.asyncio
async def test_status_and_scene_endpoints_keep_output_contract(monkeypatch):
    now = datetime.now()
    location = SimpleNamespace(
        id="lake", name="测试湖", difficulty=2, fish_pool=["鲫鱼"]
    )
    user = SimpleNamespace(
        user_id="u1",
        nickname=None,
        fishing_status={
            "location_id": "lake",
            "start_time": (now - timedelta(seconds=20)).isoformat(),
        },
        rod_level=1,
        hook_level=0,
        bait_id="0",
        items=None,
        achievements=["collect_scene_lake", 1],
        starry_score_accumulated=None,
        star_frames=None,
        starry_frames=None,
        s2_ticket_claimed=False,
        starry_exhibition=None,
        starry_fish=None,
    )
    snapshot = status_api._SceneSnapshot(
        locations=[location],
        users=[user],
        fisher_counts={"lake": 1},
        location_buffs={"lake": {}},
        weathers={"lake": {"type": "sunny"}},
        global_frame_count=0,
        starry_bonus_count=0,
    )
    monkeypatch.setattr(
        status_api, "_load_scene_snapshot", lambda: _async_value(snapshot)
    )
    monkeypatch.setattr(
        status_api, "_load_user_buffs", lambda users, at: _async_value({})
    )
    monkeypatch.setattr(
        status_api,
        "_cached_user_maps",
        lambda users, locations, mono: ({"u1": [""]}, {"u1": "000000000"}),
    )
    monkeypatch.setattr(
        status_api.ConfigManager, "get_fish", lambda _: SimpleNamespace(base_price=10)
    )
    monkeypatch.setattr(status_api.ConfigManager, "get_location", lambda _: location)
    status_api._cache_body = None

    status_data = json.loads(await status_api._get_status_json())
    scene_data = json.loads(await status_api._get_scene_json())

    assert set(status_data) == {"updated_at", "locations", "players"}
    assert status_data["locations"][0]["fish_prices"][0][0] == 10
    assert status_data["players"][0]["nickname"] == ""
    assert status_data["players"][0]["achievements"] == ["collect_scene_lake"]
    assert status_data["players"][0]["fishing_duration_seconds"] >= 0
    assert set(scene_data) == {"updated_at", "active_scenes"}
    assert scene_data["active_scenes"][0]["id"] == "lake"
    assert scene_data["active_scenes"][0]["fishers"] == 1


async def _async_value(value):
    return value
