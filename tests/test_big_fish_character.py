from zhenxun.plugins.zhenxun_plugin_fishing.backpack.view import (
    build_character_item_inventory,
)
from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
from zhenxun.plugins.zhenxun_plugin_fishing.handlers.shop import (
    _parse_use_item_arguments,
)
from zhenxun.plugins.zhenxun_plugin_fishing.items.character_use import use_big_fish
from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
    _BIG_FISH_RARITIES,
    BIG_FISH_ITEM_ID,
    BIG_FISH_ITEM_TYPE,
    BIG_FISH_REWARD_KEY,
    _has_completed_big_fish_collection,
    _is_big_fish_target_location,
    grant_big_fish_reward,
)


def _target_fish_names() -> list[str]:
    names: list[str] = []
    for location in ConfigManager.get_locations():
        if not _is_big_fish_target_location(location):
            continue
        names.extend(location.fish_pool)
    return names


def _complete_collection() -> dict[str, dict[str, int]]:
    return {
        fish_name: {rarity: 1 for rarity in _BIG_FISH_RARITIES}
        for fish_name in _target_fish_names()
    }


class TestBigFishReward:
    async def test_missing_one_utr_does_not_grant(self, db):
        user = await db.user_get("big_fish_missing")
        user.collection = _complete_collection()
        first_fish = _target_fish_names()[0]
        del user.collection[first_fish]["UTR"]

        assert not await grant_big_fish_reward(user.user_id)
        assert BIG_FISH_REWARD_KEY not in user.achievements
        assert f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}" not in user.items

    async def test_complete_1_to_10_and_s1_grants_once(self, db):
        user = await db.user_get("big_fish_complete")
        user.collection = _complete_collection()

        assert await grant_big_fish_reward(user.user_id)
        assert BIG_FISH_REWARD_KEY in user.achievements
        item = user.items[f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}"]
        assert item == {"item_type": BIG_FISH_ITEM_TYPE, "count": 1}

        assert not await grant_big_fish_reward(user.user_id)
        assert user.items[f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}"]["count"] == 1

    async def test_used_reward_is_not_reissued(self, db):
        user = await db.user_get("big_fish_used")
        user.collection = _complete_collection()
        assert await grant_big_fish_reward(user.user_id)
        assert (await use_big_fish(user.user_id))[0]
        assert f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}" not in user.items

        assert not await grant_big_fish_reward(user.user_id)
        assert f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}" not in user.items

    def test_target_set_is_exactly_1_to_10_and_s1(self):
        target_ids = {
            str(location.id).upper()
            for location in ConfigManager.get_locations()
            if _is_big_fish_target_location(location)
        }
        assert target_ids == {str(index) for index in range(1, 11)} | {"S1"}
        complete_set = {
            (fish_name, rarity)
            for fish_name in _target_fish_names()
            for rarity in _BIG_FISH_RARITIES
        }
        assert _has_completed_big_fish_collection(complete_set)


class TestBigFishUse:
    @staticmethod
    def _give(user, count: int = 1) -> None:
        user.items[f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}"] = {
            "item_type": BIG_FISH_ITEM_TYPE,
            "count": count,
        }

    async def test_empty_team_uses_first_slot(self, db):
        user = await db.user_get("big_fish_slot_1")
        self._give(user)

        success, message = await use_big_fish(user.user_id)

        assert success
        assert message == "大肥鱼被放在了队伍第1位！"
        assert user.character_slots == [BIG_FISH_ITEM_ID, None, None]
        assert f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}" not in user.items

    async def test_partial_team_uses_first_empty_slot(self, db):
        user = await db.user_get("big_fish_first_empty")
        user.character_slots = ["A", None, "C"]
        self._give(user)

        success, message = await use_big_fish(user.user_id)

        assert success
        assert message == "大肥鱼被放在了队伍第2位！"
        assert user.character_slots == ["A", BIG_FISH_ITEM_ID, "C"]

    async def test_full_team_requires_position_without_consuming(self, db):
        user = await db.user_get("big_fish_full")
        user.character_slots = ["A", "B", "C"]
        self._give(user)

        success, message = await use_big_fish(user.user_id)

        assert not success
        assert "钓鱼使用 大肥鱼 1/2/3" in message
        assert user.character_slots == ["A", "B", "C"]
        assert user.items[f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}"]["count"] == 1

    async def test_full_team_can_replace_requested_slot(self, db):
        user = await db.user_get("big_fish_replace")
        user.character_slots = ["A", "B", "C"]
        self._give(user)

        success, message = await use_big_fish(user.user_id, arg="2")

        assert success
        assert message == "大肥鱼被放在了队伍第2位！"
        assert user.character_slots == ["A", BIG_FISH_ITEM_ID, "C"]
        assert f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}" not in user.items

    async def test_invalid_position_does_not_consume(self, db):
        user = await db.user_get("big_fish_invalid")
        self._give(user)

        success, message = await use_big_fish(user.user_id, arg="4")

        assert not success
        assert message == "角色位置只能是1、2或3！"
        assert user.character_slots == [None, None, None]
        assert user.items[f"{BIG_FISH_ITEM_ID}|{BIG_FISH_ITEM_TYPE}"]["count"] == 1


class TestBigFishBackpackAndParsing:
    def test_position_is_not_parsed_as_count(self):
        assert _parse_use_item_arguments(BIG_FISH_ITEM_ID, "2") == (1, "2")
        assert _parse_use_item_arguments("闪光药水", "2") == (2, "")

    def test_unused_character_item_stays_in_props_inventory(self):
        rows = build_character_item_inventory(
            [
                {
                    "item_id": BIG_FISH_ITEM_ID,
                    "item_type": BIG_FISH_ITEM_TYPE,
                    "count": 1,
                }
            ]
        )
        assert rows == [
            {"item_id": BIG_FISH_ITEM_ID, "name": BIG_FISH_ITEM_ID, "count": 1}
        ]

    async def test_character_slots_render_as_text(self, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.render import backpack as module

        captured: dict[str, str] = {}

        async def capture_html(html: str, width: int = 300) -> bytes:
            captured["html"] = html
            return b"rendered"

        monkeypatch.setattr(module, "render_html", capture_html)
        result = await module.render_backpack(
            "render_big_fish",
            [],
            0,
            character_slots=[BIG_FISH_ITEM_ID, None, None],
            character_item_list=[{"name": BIG_FISH_ITEM_ID, "count": 1}],
        )

        assert result == b"rendered"
        html = captured["html"]
        character_block = html.split("👥 角色", 1)[1].split("🎒 道具", 1)[0]
        assert "第1位：" in character_block
        assert BIG_FISH_ITEM_ID in character_block
        assert character_block.count("character-slot") == 3
        assert "<img" not in character_block

    def test_model_has_three_slot_column_migration(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser

        assert hasattr(FishingUser, "character_slots")
        assert any(
            "ADD COLUMN character_slots" in sql for sql in FishingUser._run_script()
        )
