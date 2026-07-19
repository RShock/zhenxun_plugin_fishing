import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.config import (
    ConfigManager,
    calculate_fish_price,
    generate_fish_numeric_id,
)

from zhenxun.plugins.zhenxun_plugin_fishing.backpack import (
    black_market_exchange,
    gift_fish,
    render_white_market_records,
    lock_fish,
    sell_fish,
    unlock_fish,
    white_market_exchange,
)
from zhenxun.plugins.zhenxun_plugin_fishing.backpack.selection import (
    is_likely_misfire,
    parse_fish_selection,
)
from zhenxun.plugins.zhenxun_plugin_fishing.backpack.black_market import (
    _maybe_randomize_same_rarity_target,
    can_exchange,
    extract_market_exchange_input,
    find_fish_target,
    parse_black_market_exchange,
    parse_market_exchange,
    should_parse_market_exchange,
)
from zhenxun.plugins.zhenxun_plugin_fishing.fishing import start_fishing, stop_fishing

USER_ID = "test_user_001"
TARGET_ID = "test_user_002"


async def _setup_user_with_fish(db, user_id, rod_level=5):
    user = await db.user_get(user_id)
    user.rod_level = rod_level
    await start_fishing(user_id, "1", "TestUser")
    await stop_fishing(user_id, gm_mode=True)
    return await db.backpack_get_user_fish(user_id)


class TestCatParkNumericId:
    async def test_old_s1_backpack_id_is_normalized(self, db):
        user = await db.user_get(USER_ID)
        user.backpack = {
            "S101": {
                "fish_name": "橘座鲫鱼",
                "rarity": "N",
                "count": 2,
                "locked": False,
            }
        }
        await user.save(update_fields=["backpack"])

        fish_list = await db.backpack_get_user_fish(USER_ID)

        assert fish_list[0]["numeric_id"] == "s101"
        assert "s101" in (await db.user_get(USER_ID)).backpack

    async def test_old_s1_id_lookup_still_works(self, db):
        await db.backpack_add_fish(USER_ID, "橘座鲫鱼", "N", "S101", count=1)

        fish = await db.backpack_get_fish_by_numeric_id(USER_ID, "S101")

        assert fish["numeric_id"] == "s101"

    async def test_old_negative_s1_id_lookup_still_works(self, db):
        await db.backpack_add_fish(USER_ID, "橘座鲫鱼", "N", "-101", count=1)

        fish = await db.backpack_get_fish_by_numeric_id(USER_ID, "-101")

        assert fish["numeric_id"] == "s101"

    async def test_collection_is_object_mapping(self, db):
        user = await db.user_get(USER_ID)
        user.collection = {"橘座鲫鱼|N": 2}

        collected = await db.collection_get_user_collected(USER_ID)

        assert ("橘座鲫鱼", "N") in collected
        assert user.collection == {"橘座鲫鱼": {"N": 2}}


class TestSellFish:
    async def test_sell_by_rarity(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        assert len(fish_list) > 0
        ok, msg = await sell_fish(USER_ID, "N")
        assert isinstance(ok, bool)

    async def test_sell_by_numeric_id(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await sell_fish(USER_ID, fish_list[0]["numeric_id"])
        assert isinstance(ok, bool)

    async def test_sell_no_fish_input(self, db):
        ok, msg = await sell_fish(USER_ID, None)
        assert ok is False

    async def test_sell_nonexistent_fish(self, db):
        ok, msg = await sell_fish(USER_ID, "99999")
        assert ok is False

    async def test_sell_locked_fish(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        await lock_fish(USER_ID, fish["numeric_id"])
        ok, msg = await sell_fish(USER_ID, fish["numeric_id"])
        assert ok is False

    async def test_sell_locked_by_rarity(self, db):
        """卖鱼[n] 不应出售已锁定的鱼（测试按稀有度卖鱼时锁定过滤）"""
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        target = fish_list[0]
        await lock_fish(USER_ID, target["numeric_id"])
        locked = await db.backpack_get_fish_by_numeric_id(USER_ID, target["numeric_id"])
        assert locked["locked"] is True
        rarity_letter = target["rarity"]
        ok, msg = await sell_fish(USER_ID, rarity_letter.lower())
        remaining = await db.backpack_get_user_fish(USER_ID)
        remaining_ids = {f["numeric_id"] for f in remaining}
        assert target["numeric_id"] in remaining_ids, (
            f"锁定的鱼({target['rarity']})被卖掉了！msg={msg}"
        )

    async def test_sell_locked_ur_two_locations(self, db):
        """模拟：鲢鱼UR从两个不同钓场获得(不同numeric_id)，锁住其中一个，卖鱼ur不应卖掉已锁的"""
        await db.backpack_add_fish(USER_ID, "鲢鱼", "UR", "235", count=1)
        await db.backpack_add_fish(USER_ID, "鲢鱼", "UR", "345", count=1)
        fish_list = await db.backpack_get_user_fish(USER_ID)
        lianyu = [f for f in fish_list if f["fish_name"] == "鲢鱼"]
        assert len(lianyu) == 2, f"应该有2条鲢鱼UR条目，实际: {len(lianyu)}"
        await lock_fish(USER_ID, "235")
        locked = await db.backpack_get_fish_by_numeric_id(USER_ID, "235")
        assert locked is not None, "235应该存在"
        assert locked["locked"] is True, "235应该已被锁定"
        ok, msg = await sell_fish(USER_ID, "ur")
        remaining = await db.backpack_get_user_fish(USER_ID)
        remaining_ids = {f["numeric_id"] for f in remaining}
        assert "235" in remaining_ids, f"锁定的鲢鱼UR(235)被卖掉了！msg={msg}"
        assert "345" not in remaining_ids, "未锁的鲢鱼UR(345)应该被卖掉"

    async def test_sell_gives_gold(self, db):
        user_before = await db.user_get(USER_ID)
        gold_before = user_before.gold
        await _setup_user_with_fish(db, USER_ID)
        user_after_fish = await db.user_get(USER_ID)
        gold_after_fish = user_after_fish.gold
        await sell_fish(USER_ID, "N")
        user_after_sell = await db.user_get(USER_ID)
        assert user_after_sell.gold >= gold_after_fish

    async def test_sell_by_wildcard_rarity(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        assert len(fish_list) > 0
        ok, msg = await sell_fish(USER_ID, "**1")
        assert isinstance(ok, bool)

    async def test_sell_by_rarity_and_id(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await sell_fish(USER_ID, f"N,{fish_list[0]['numeric_id']}")
        assert isinstance(ok, bool)

    async def test_sell_by_all(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await sell_fish(USER_ID, "全部")
        assert ok is True


class TestLockFish:
    async def test_lock_fish(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        ok, msg = await lock_fish(USER_ID, fish["numeric_id"])
        assert ok is True
        updated = await db.backpack_get_fish_by_numeric_id(USER_ID, fish["numeric_id"])
        assert updated["locked"] is True

    async def test_lock_already_locked(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        await lock_fish(USER_ID, fish["numeric_id"])
        ok, msg = await lock_fish(USER_ID, fish["numeric_id"])
        assert ok is True
        updated = await db.backpack_get_fish_by_numeric_id(USER_ID, fish["numeric_id"])
        assert updated["locked"] is True

    async def test_unlock_fish(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        await lock_fish(USER_ID, fish["numeric_id"])
        ok, msg = await unlock_fish(USER_ID, fish["numeric_id"])
        assert ok is True
        updated = await db.backpack_get_fish_by_numeric_id(USER_ID, fish["numeric_id"])
        assert updated["locked"] is False

    async def test_lock_nonexistent_fish(self, db):
        ok, msg = await lock_fish(USER_ID, "99999")
        assert ok is False

    async def test_lock_by_rarity_sr(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        ok, msg = await lock_fish(USER_ID, "SR")
        assert isinstance(ok, bool)

    async def test_lock_by_wildcard_rarity(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        ok, msg = await lock_fish(USER_ID, "**3")
        assert isinstance(ok, bool)

    async def test_lock_all(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await lock_fish(USER_ID, "全部")
        assert ok is True

    async def test_unlock_all(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        await lock_fish(USER_ID, "全部")
        ok, msg = await unlock_fish(USER_ID, "全部")
        assert ok is True

    async def test_lock_batch_ids(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if len(fish_list) < 2:
            pytest.skip("Not enough fish")
        id1 = fish_list[0]["numeric_id"]
        id2 = fish_list[1]["numeric_id"]
        ok, msg = await lock_fish(USER_ID, f"{id1},{id2}")
        assert isinstance(ok, bool)

    async def test_lock_mixed_rarity_and_id(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await lock_fish(USER_ID, f"SR,{fish_list[0]['numeric_id']}")
        assert isinstance(ok, bool)

    async def test_lock_wildcard_and_id(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await lock_fish(USER_ID, f"**3,{fish_list[0]['numeric_id']}")
        assert isinstance(ok, bool)

    async def test_lock_s1_wildcard(self, db):
        """锁鱼 S1** 应锁定猫猫乐园全部鱼，不影响普通图。"""
        user = await db.user_get(USER_ID)
        user.backpack = {
            "s101": {"fish_name": "橘座鲫鱼", "rarity": "N", "count": 1, "locked": False},
            "s102": {"fish_name": "暹罗鳊鱼", "rarity": "R", "count": 1, "locked": False},
            "111": {"fish_name": "小鲫鱼", "rarity": "N", "count": 1, "locked": False},
        }
        await user.save(update_fields=["backpack"])

        ok, msg = await lock_fish(USER_ID, "S1**")
        assert ok is True
        backpack = (await db.user_get(USER_ID)).backpack
        assert backpack["s101"]["locked"] is True
        assert backpack["s102"]["locked"] is True
        assert backpack["111"]["locked"] is False

    async def test_unlock_s1_wildcard(self, db):
        """解锁 S1** 应解锁猫猫乐园全部鱼，不影响普通图。"""
        user = await db.user_get(USER_ID)
        user.backpack = {
            "s101": {"fish_name": "橘座鲫鱼", "rarity": "N", "count": 1, "locked": True},
            "s102": {"fish_name": "暹罗鳊鱼", "rarity": "R", "count": 1, "locked": True},
            "111": {"fish_name": "小鲫鱼", "rarity": "N", "count": 1, "locked": True},
        }
        await user.save(update_fields=["backpack"])

        ok, msg = await unlock_fish(USER_ID, "S1**")
        assert ok is True
        backpack = (await db.user_get(USER_ID)).backpack
        assert backpack["s101"]["locked"] is False
        assert backpack["s102"]["locked"] is False
        assert backpack["111"]["locked"] is True

    async def test_lock_normal_map_wildcard(self, db):
        """锁鱼 1** 应锁定地图1全部鱼。"""
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        ok, msg = await lock_fish(USER_ID, "1**")
        assert ok is True

    async def test_lock_s1_wildcard_no_match(self, db):
        """背包无猫猫乐园鱼时，锁鱼 S1** 应返回失败。"""
        user = await db.user_get(USER_ID)
        user.backpack = {
            "111": {"fish_name": "小鲫鱼", "rarity": "N", "count": 1, "locked": False},
        }
        await user.save(update_fields=["backpack"])

        ok, msg = await lock_fish(USER_ID, "S1**")
        assert ok is False


class TestParseLocationWildcard:
    def test_parse_s1_wildcard(self):
        sel = parse_fish_selection("S1**")
        assert sel.location_prefixes == ["s1"]
        assert sel.is_empty() is False

    def test_parse_lowercase_s1_wildcard(self):
        sel = parse_fish_selection("s1**")
        assert sel.location_prefixes == ["s1"]

    def test_parse_normal_map_wildcard(self):
        sel = parse_fish_selection("1**")
        assert sel.location_prefixes == ["1"]

    def test_parse_mixed_wildcard_and_rarity(self):
        sel = parse_fish_selection("S1** SR")
        assert sel.location_prefixes == ["s1"]
        assert sel.rarity_letters == ["SR"]

    def test_parse_mixed_wildcard_and_id(self):
        sel = parse_fish_selection("S1**,s101")
        assert sel.location_prefixes == ["s1"]
        assert sel.numeric_ids == ["s101"]

    def test_rarity_index_not_confused_with_wildcard(self):
        """**3 应解析为稀有度索引，不是位置通配符。"""
        sel = parse_fish_selection("**3")
        assert sel.rarity_precise == ["SR"]
        assert sel.location_prefixes == []

    def test_misfire_not_triggered_for_wildcard(self):
        assert is_likely_misfire("S1**") is False

    def test_misfire_not_triggered_for_wildcard_with_chinese(self):
        assert is_likely_misfire("猫猫乐园S1**") is False


class TestGiftFish:
    def _first_location_fish(self, rarity: str = "N") -> tuple[str, str]:
        location = ConfigManager.get_location("1")
        assert location is not None
        fish_name = location.fish_pool[0]
        numeric_id = generate_fish_numeric_id(location.id, 1, rarity)
        return fish_name, numeric_id

    def _utr_price(self, fish_name: str) -> int:
        fish_data = ConfigManager.get_fish(fish_name)
        assert fish_data is not None
        return calculate_fish_price(fish_data, "UTR", 0)

    async def test_gift_fish(self, db):
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        ok, msg = await gift_fish(USER_ID, TARGET_ID, fish["numeric_id"])
        assert isinstance(ok, bool)

    async def test_gift_locked_fish(self, db):
        """锁定的鱼也可以赠送（锁定仅防止误卖，不阻止赠送）"""
        fish_list = await _setup_user_with_fish(db, USER_ID)
        if not fish_list:
            pytest.skip("No fish caught")
        fish = fish_list[0]
        await lock_fish(USER_ID, fish["numeric_id"])
        ok, msg = await gift_fish(USER_ID, TARGET_ID, fish["numeric_id"])
        assert ok is True

    async def test_gift_nonexistent_fish(self, db):
        ok, msg = await gift_fish(USER_ID, TARGET_ID, "99999")
        assert ok is False

    async def test_gift_utr_unlock_does_not_count_daily_limit(self, db):
        fish_name, numeric_id = self._first_location_fish("UTR")
        await db.backpack_add_fish(USER_ID, fish_name, "UTR", numeric_id, count=1)
        user_before = await db.user_get(USER_ID)
        gold_before = user_before.gold

        ok, msg = await gift_fish(USER_ID, TARGET_ID, numeric_id)

        assert ok is True
        gift_count = await db.user_get_gift_count(USER_ID)
        assert gift_count == 0
        user_after = await db.user_get(USER_ID)
        assert user_after.gold - gold_before == self._utr_price(fish_name)
        target_fish = await db.backpack_get_fish_by_numeric_id(TARGET_ID, numeric_id)
        assert target_fish is None
        collected = await db.collection_get_user_collected(TARGET_ID)
        assert (fish_name, "UTR") in collected

    async def test_gift_utr_already_unlocked_counts_daily_limit(self, db):
        fish_name, numeric_id = self._first_location_fish("UTR")
        await db.collection_mark_collected(TARGET_ID, fish_name, "UTR", 1)
        await db.backpack_add_fish(USER_ID, fish_name, "UTR", numeric_id, count=1)
        user_before = await db.user_get(USER_ID)
        gold_before = user_before.gold

        ok, msg = await gift_fish(USER_ID, TARGET_ID, numeric_id)

        assert ok is True
        gift_count = await db.user_get_gift_count(USER_ID)
        assert gift_count == 1
        user_after = await db.user_get(USER_ID)
        assert user_after.gold == gold_before
        collected = await db.collection_get_user_collected_with_count(TARGET_ID)
        assert collected[(fish_name, "UTR")] == 2


class TestBlackMarketExchange:
    def test_parse_compact_and_spaced_input(self):
        assert parse_black_market_exchange("鲤鱼UR 草鱼SSR") == (
            "鲤鱼",
            "UR",
            "草鱼",
            "SSR",
        )
        assert parse_black_market_exchange("鲤鱼UR草鱼SSR") == (
            "鲤鱼",
            "UR",
            "草鱼",
            "SSR",
        )
        assert parse_black_market_exchange("鲤鱼 UR 草鱼 SSR") == (
            "鲤鱼",
            "UR",
            "草鱼",
            "SSR",
        )

    def test_market_exchange_prefix_and_trigger_detection(self):
        assert extract_market_exchange_input("黑商交换 鲤鱼UR草鱼SSR") == "鲤鱼UR草鱼SSR"
        assert extract_market_exchange_input("白商 鲤鱼UR草鱼SSR") == "鲤鱼UR草鱼SSR"
        assert should_parse_market_exchange("鲤鱼UR草鱼SSR") is True
        assert should_parse_market_exchange("123 456 ") is True
        assert should_parse_market_exchange("只是聊一下黑商") is False

    def test_market_exchange_id_parse_requires_two_three_digit_ids(self):
        parsed = parse_market_exchange("111 112 ")
        assert parsed.should_reply is True
        assert parsed.parsed is not None

        failed = parse_market_exchange("111 999 ")
        assert failed.should_reply is True
        assert failed.parsed is None
        assert failed.reason == "parse_failed"

        silent = parse_market_exchange("随便看看")
        assert silent.should_reply is False
        assert silent.reason == "not_exchange_like"

    def test_can_exchange_allows_same_scene_and_rarity(self):
        source = find_fish_target("小鲫鱼", "N")
        target = find_fish_target("小鲫鱼", "N")
        assert source is not None and target is not None
        assert can_exchange(source, target) is True

    def test_can_exchange_higher_scene_same_rarity(self):
        source = find_fish_target("橘座鲫鱼", "UR")
        target = find_fish_target("小鲫鱼", "UR")
        assert source is not None and target is not None
        assert source.scene_level > target.scene_level
        assert can_exchange(source, target) is True

    async def test_black_exchange_empty_input_replies_usage(self, db):
        ok, msg, should_reply = await black_market_exchange(USER_ID, "")

        assert ok is False
        assert should_reply is True
        assert "黑商用法" in msg
        assert "黑商交换" in msg

    async def test_black_exchange_non_exchange_like_input_stays_silent(self, db):
        ok, msg, should_reply = await black_market_exchange(USER_ID, "只是聊一下黑商")

        assert ok is False
        assert msg == ""
        assert should_reply is False

    async def test_black_exchange_same_scene_and_rarity_allowed(self, db, monkeypatch):
        source = find_fish_target("小鲫鱼", "N")
        target = find_fish_target("小鲫鱼", "N")
        assert source is not None and target is not None
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.backpack.black_market.random.random",
            lambda: 0.9,
        )
        await db.backpack_add_fish(USER_ID, source.name, source.rarity, source.numeric_id, count=1)

        ok, msg, should_reply = await black_market_exchange(
            USER_ID,
            f"{source.name} {source.rarity} {target.name} {target.rarity}",
        )

        assert ok is True
        assert should_reply is True
        displays = await db.display_get_user_displays(USER_ID)
        assert displays[0]["fish_name"] == target.name
        assert displays[0]["rarity"] == target.rarity

    async def test_exchange_locked_fish_allowed_and_once_per_day(self, db):
        source = find_fish_target("小鲫鱼", "UR")
        target = find_fish_target("小鲫鱼", "N")
        assert source is not None and target is not None
        await db.backpack_add_fish(USER_ID, source.name, source.rarity, source.numeric_id, count=2)
        await lock_fish(USER_ID, source.numeric_id)

        ok, msg, should_reply = await black_market_exchange(USER_ID, f"{source.name} {source.rarity} {target.name} {target.rarity}")

        assert ok is True
        assert should_reply is True
        remaining = await db.backpack_get_fish_by_numeric_id(USER_ID, source.numeric_id)
        assert remaining["count"] == 1
        second_ok, second_msg, second_should_reply = await black_market_exchange(
            USER_ID,
            f"{source.name} {source.rarity} {target.name} {target.rarity}",
        )
        assert second_ok is False
        assert second_should_reply is True
        assert "今天已经" in second_msg

    def test_same_rarity_random_excludes_target_and_source(self, monkeypatch):
        source = find_fish_target("小鲫鱼", "UR")
        target = find_fish_target("草鱼", "UR")
        assert source is not None and target is not None
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.backpack.black_market.random.random",
            lambda: 0.1,
        )
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.backpack.black_market.random.choice",
            lambda seq: seq[0],
        )

        actual, randomized = _maybe_randomize_same_rarity_target(source, target)

        assert randomized is True
        assert actual.rarity == target.rarity
        assert actual.location_id == target.location_id
        assert actual.numeric_id not in {source.numeric_id, target.numeric_id}

    async def test_same_source_target_record_is_removed_from_active_list(self, db):
        fish = find_fish_target("小鲫鱼", "N")
        assert fish is not None
        await db.exchange_create_black_record(USER_ID, fish, fish)

        records = await db.exchange_list_active_records()

        assert records == []

    async def test_black_record_and_white_market_reverse(self, db):
        black_source = find_fish_target("小鲫鱼", "UR")
        black_target = find_fish_target("小鲫鱼", "N")
        assert black_source is not None and black_target is not None
        await db.backpack_add_fish(USER_ID, black_source.name, black_source.rarity, black_source.numeric_id, count=1)

        ok, msg, should_reply = await black_market_exchange(
            USER_ID,
            f"{black_source.name} {black_source.rarity} {black_target.name} {black_target.rarity}",
        )
        assert ok is True
        assert should_reply is True

        # 白商列表渲染为图片字节
        image = await render_white_market_records(TARGET_ID)
        assert isinstance(image, bytes)
        assert image == b"FAKE_IMAGE_BYTES"

        # 确认活跃记录存在
        records = await db.exchange_list_active_records()
        assert len(records) == 1

        await db.backpack_add_fish(TARGET_ID, black_target.name, black_target.rarity, black_target.numeric_id, count=1)
        white_ok, white_msg, white_should_reply = await white_market_exchange(
            TARGET_ID,
            f"{black_target.name} {black_target.rarity} {black_source.name} {black_source.rarity}",
        )

        assert white_ok is True
        assert white_should_reply is True
        assert "已失效" in white_msg
        records = await db.exchange_list_active_records()
        assert records == []
        gift_count = await db.user_get_gift_count(TARGET_ID)
        assert gift_count == 1

    async def test_white_market_filter_uncollected(self, db):
        """已解锁的鱼不显示在白商列表中。"""
        black_source = find_fish_target("小鲫鱼", "UR")
        black_target = find_fish_target("小鲫鱼", "N")
        assert black_source is not None and black_target is not None
        await db.backpack_add_fish(USER_ID, black_source.name, black_source.rarity, black_source.numeric_id, count=1)

        ok, msg, should_reply = await black_market_exchange(
            USER_ID,
            f"{black_source.name} {black_source.rarity} {black_target.name} {black_target.rarity}",
        )
        assert ok is True
        assert should_reply is True

        # TARGET_ID 已解锁来源鱼（白商可获得鱼），应被过滤
        await db.collection_mark_collected(TARGET_ID, black_source.name, black_source.rarity, 1)
        image = await render_white_market_records(TARGET_ID)
        assert isinstance(image, bytes)
