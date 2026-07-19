import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.services.display_service import (
    calculate_display_income,
)
from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser


USER_ID = "test_starry_income_001"


class TestStarryFrameIncome:
    async def test_starry_frames_give_4x(self, db, monkeypatch):
        user = await db.user_get(USER_ID)
        user.upgraded_display_count = 2
        user.starry_frames = 1
        user.display_slots = 3

        async def fake_displays(_uid):
            return [
                {"fish_name": "A", "rarity": "UR", "slot": 1},
                {"fish_name": "B", "rarity": "SSR", "slot": 2},
                {"fish_name": "C", "rarity": "SR", "slot": 3},
            ]

        prices = {"A": 100, "B": 50, "C": 10}

        class FakeFish:
            def __init__(self, name):
                self.name = name

        def fake_get_fish_by_name(name):
            return FakeFish(name) if name in prices else None

        def fake_price(fish_data, rarity, weight):
            return prices[fish_data.name]

        monkeypatch.setattr(FishingUser, "get_user_displays", staticmethod(fake_displays))
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.services.display_service.ConfigManager.get_fish_by_name",
            fake_get_fish_by_name,
        )
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.services.display_service.calculate_fish_price",
            fake_price,
        )

        income = await calculate_display_income(USER_ID)
        # 100*4 + 50*3 + 10*2 = 400 + 150 + 20 = 570
        assert income == 570
