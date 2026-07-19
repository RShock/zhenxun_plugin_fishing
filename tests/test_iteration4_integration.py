"""迭代四热点重构的兼容与集成测试。"""

from datetime import datetime, timedelta
import inspect
import json
from types import SimpleNamespace

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
    assert status_params["weather_info"].default is None


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
