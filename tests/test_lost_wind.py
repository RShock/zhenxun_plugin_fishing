from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.models import BuffEffect, FishingBuffCalculator
from zhenxun.plugins.zhenxun_plugin_fishing.weather_service import get_location_weather


@pytest.fixture
def unlocked_user(db):
    return "user_unlocked"


@pytest.fixture
def locked_user(db):
    return "user_locked"


@pytest.fixture
def the_location():
    return "1"


@pytest.fixture
def now():
    return datetime.now()


class TestLostWindBuffFiltering:
    @pytest.mark.asyncio
    async def test_unlocked_user_keeps_lost_wind(
        self, db, unlocked_user, the_location, now
    ):
        await db.mark_lost_wind_unlocked(unlocked_user, the_location)
        lost_buff = await db.buff_add_location_buff(
            the_location, "weather_lost_wind", 24, 1, "迷途风：UTR概率1%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        buffs = await db.buff_get_active_buffs_for_fishing(
            unlocked_user, the_location, window_start, window_end
        )
        assert lost_buff in buffs

    @pytest.mark.asyncio
    async def test_locked_user_filters_lost_wind(
        self, db, locked_user, the_location, now
    ):
        await db.buff_add_location_buff(
            the_location, "weather_lost_wind", 24, 1, "迷途风：UTR概率1%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        buffs = await db.buff_get_active_buffs_for_fishing(
            locked_user, the_location, window_start, window_end
        )
        assert all(b.buff_type != "weather_lost_wind" for b in buffs)

    @pytest.mark.asyncio
    async def test_no_lost_wind_no_crash(
        self, db, locked_user, the_location, now
    ):
        await db.buff_add_location_buff(
            the_location, "weather_rain", 24, 10, "雨天：上鱼速度+10%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        buffs = await db.buff_get_active_buffs_for_fishing(
            locked_user, the_location, window_start, window_end
        )
        assert len(buffs) == 1
        assert buffs[0].buff_type == "weather_rain"

    @pytest.mark.asyncio
    async def test_lost_wind_other_loc_not_filtered(
        self, db, locked_user, the_location, now
    ):
        await db.mark_lost_wind_unlocked(locked_user, the_location)
        other_loc = "2"
        await db.buff_add_location_buff(
            other_loc, "weather_lost_wind", 24, 1, "迷途风：UTR概率1%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        buffs = await db.buff_get_active_buffs_for_fishing(
            locked_user, other_loc, window_start, window_end
        )
        assert not any(b.buff_type == "weather_lost_wind" for b in buffs)


class TestLostWindEffect:
    @pytest.mark.asyncio
    async def test_unlocked_user_gets_weather_lost_wind_effect(
        self, db, unlocked_user, the_location, now
    ):
        await db.mark_lost_wind_unlocked(unlocked_user, the_location)
        lost_buff = await db.buff_add_location_buff(
            the_location, "weather_lost_wind", 24, 1, "迷途风：UTR概率1%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)
        buffs = await db.buff_get_active_buffs_for_fishing(
            unlocked_user, the_location, window_start, window_end
        )
        assert lost_buff in buffs

        effects = FishingBuffCalculator.get_effects_at_time(
            buffs, lost_buff.start_time, 5, 0, 1
        )
        assert effects["weather_lost_wind"] is True

    @pytest.mark.asyncio
    async def test_locked_user_gets_no_weather_lost_wind_effect(
        self, db, locked_user, the_location, now
    ):
        await db.buff_add_location_buff(
            the_location, "weather_lost_wind", 24, 1, "迷途风：UTR概率1%"
        )
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)
        buffs = await db.buff_get_active_buffs_for_fishing(
            locked_user, the_location, window_start, window_end
        )
        assert all(b.buff_type != "weather_lost_wind" for b in buffs)

        effects = FishingBuffCalculator.get_effects_at_time(
            buffs, now, 5, 0, 1
        )
        assert effects["weather_lost_wind"] is False


class TestWeatherVisibility:
    @pytest.mark.asyncio
    async def test_unlocked_user_sees_lost_wind_weather(self, db, monkeypatch):
        user_id = "u1"
        location_id = "1"
        await db.mark_lost_wind_unlocked(user_id, location_id)

        fake_weather = MagicMock()
        fake_weather.location_id = location_id
        fake_weather.weather_type = "lost_wind"
        fake_weather.start_time = datetime.now() - timedelta(hours=1)
        fake_weather.end_time = datetime.now() + timedelta(hours=23)

        with patch(
            "zhenxun.plugins.zhenxun_plugin_fishing.weather_service.FishingWeather.get_today_weather",
            AsyncMock(return_value=fake_weather),
        ):
            info = await get_location_weather(location_id, user_id)
            assert info["weather_type"] == "lost_wind"
            assert info["is_active"] is True

    @pytest.mark.asyncio
    async def test_locked_user_sees_sunny_instead_of_lost_wind(
        self, db, monkeypatch
    ):
        user_id = "u2"
        location_id = "1"

        fake_weather = MagicMock()
        fake_weather.location_id = location_id
        fake_weather.weather_type = "lost_wind"
        fake_weather.start_time = datetime.now() - timedelta(hours=1)
        fake_weather.end_time = datetime.now() + timedelta(hours=23)

        with patch(
            "zhenxun.plugins.zhenxun_plugin_fishing.weather_service.FishingWeather.get_today_weather",
            AsyncMock(return_value=fake_weather),
        ):
            info = await get_location_weather(location_id, user_id)
            assert info["weather_type"] == "sunny"
            assert info["is_active"] is False

    @pytest.mark.asyncio
    async def test_no_user_context_always_sunny_for_lost_wind(self, monkeypatch):
        location_id = "1"

        fake_weather = MagicMock()
        fake_weather.location_id = location_id
        fake_weather.weather_type = "lost_wind"
        fake_weather.start_time = datetime.now() - timedelta(hours=1)
        fake_weather.end_time = datetime.now() + timedelta(hours=23)

        with patch(
            "zhenxun.plugins.zhenxun_plugin_fishing.weather_service.FishingWeather.get_today_weather",
            AsyncMock(return_value=fake_weather),
        ):
            info = await get_location_weather(location_id, user_id=None)
            assert info["weather_type"] == "sunny"
            assert info["is_active"] is False
