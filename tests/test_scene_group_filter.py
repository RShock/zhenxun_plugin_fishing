from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot

from zhenxun.plugins.zhenxun_plugin_fishing.core import scene
from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser


def _user(user_id: str):
    return SimpleNamespace(nickname=user_id, skin_id="1")


async def test_official_only_group_filters_by_recorded_fishing_group(monkeypatch):
    monkeypatch.setattr(
        FishingUser,
        "get_location_fishers",
        AsyncMock(return_value=["viewer", "same", "other", "legacy"]),
    )

    statuses = {
        "viewer": {"location_id": "1"},
        "same": {"location_id": "1", "group_id": "OPEN_GROUP"},
        "other": {"location_id": "1", "group_id": "OTHER_GROUP"},
        "legacy": {"location_id": "1"},
    }
    monkeypatch.setattr(
        FishingUser,
        "get_status",
        AsyncMock(side_effect=lambda user_id: statuses[user_id]),
    )
    monkeypatch.setattr(
        FishingUser,
        "get_user",
        AsyncMock(side_effect=lambda user_id: _user(user_id)),
    )

    players = await scene.collect_scene_players(
        "1", "OPEN_GROUP", viewer_user_id="viewer"
    )

    assert [player["user_id"] for player in players] == ["viewer", "same"]


async def test_numeric_group_uses_onebot_member_list(monkeypatch):
    monkeypatch.setattr(
        FishingUser,
        "get_location_fishers",
        AsyncMock(return_value=["viewer", "member", "outsider"]),
    )
    monkeypatch.setattr(
        FishingUser,
        "get_user",
        AsyncMock(side_effect=lambda user_id: _user(user_id)),
    )
    get_status = AsyncMock(return_value={"group_id": "OTHER_GROUP"})
    monkeypatch.setattr(FishingUser, "get_status", get_status)

    bot = SimpleNamespace(
        call_api=AsyncMock(
            return_value=[{"user_id": "viewer"}, {"user_id": "member"}]
        )
    )
    monkeypatch.setattr(nonebot, "get_bot", lambda: bot)

    players = await scene.collect_scene_players(
        "1", "1054188847", viewer_user_id="viewer"
    )

    assert [player["user_id"] for player in players] == ["viewer", "member"]
    bot.call_api.assert_awaited_once_with(
        "get_group_member_list", group_id=1054188847
    )
    get_status.assert_not_awaited()


async def test_member_api_failure_never_falls_back_to_all_players(monkeypatch):
    monkeypatch.setattr(
        FishingUser,
        "get_location_fishers",
        AsyncMock(return_value=["viewer", "same", "other"]),
    )
    statuses = {
        "viewer": {"location_id": "1"},
        "same": {"location_id": "1", "group_id": "1054188847"},
        "other": {"location_id": "1", "group_id": "999999999"},
    }
    monkeypatch.setattr(
        FishingUser,
        "get_status",
        AsyncMock(side_effect=lambda user_id: statuses[user_id]),
    )
    monkeypatch.setattr(
        FishingUser,
        "get_user",
        AsyncMock(side_effect=lambda user_id: _user(user_id)),
    )

    bot = SimpleNamespace(call_api=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(nonebot, "get_bot", lambda: bot)

    players = await scene.collect_scene_players(
        "1", "1054188847", viewer_user_id="viewer"
    )

    assert [player["user_id"] for player in players] == ["viewer", "same"]
