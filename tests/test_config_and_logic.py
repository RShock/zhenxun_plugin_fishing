from datetime import datetime, timedelta

from zhenxun.plugins.zhenxun_plugin_fishing.config import (
    ConfigManager,
    calculate_fish_price,
    generate_fish_numeric_id,
    get_display_probabilities,
    get_rarity_probabilities,
    get_rarity_probabilities_full,
)
from zhenxun.plugins.zhenxun_plugin_fishing.constants import RARITY_DISTRIBUTION
from zhenxun.plugins.zhenxun_plugin_fishing.core import engine as fishing_engine
from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
    _try_append_starry_meteor_fish,
)
from zhenxun.plugins.zhenxun_plugin_fishing.fishing import (
    _apply_duoduo,
    _cap_rarity,
    _catch_fish_with_buffs,
    _compute_duoduo_quantity,
)
from zhenxun.plugins.zhenxun_plugin_fishing.models import (
    BuffEffect,
    FishingBuffCalculator,
)


class TestConfigManager:
    def test_get_locations(self):
        locations = ConfigManager.get_locations()
        assert len(locations) > 0
        assert locations[0].id == "1"
        assert locations[0].name == "乡间浅溪"

    def test_get_location_by_id(self):
        loc = ConfigManager.get_location("1")
        assert loc is not None
        assert loc.name == "乡间浅溪"

    def test_cat_park_max_rarity_is_ur(self):
        location = ConfigManager.get_location("S1")
        assert location is not None
        assert location.max_rarity == "UR"

    def test_get_location_not_found(self):
        loc = ConfigManager.get_location("999")
        assert loc is None

    def test_get_fish(self):
        fish = ConfigManager.get_fish("小鲫鱼")
        assert fish is not None
        assert fish.id == "小鲫鱼"
        assert fish.base_price > 0

    def test_get_fish_not_found(self):
        fish = ConfigManager.get_fish("不存在的鱼")
        assert fish is None

    def test_get_shop(self):
        shop = ConfigManager.get_shop()
        assert shop is not None
        assert len(shop.baits) > 0
        assert len(shop.potions) > 0

    def test_get_bait(self):
        bait = ConfigManager.get_bait(1)
        assert bait is not None
        assert bait.name == "蚯蚓鱼饵"

    def test_calculate_fishing_interval(self):
        interval = ConfigManager.calculate_fishing_interval(0, 0)
        assert interval > 0
        interval_with_hook = ConfigManager.calculate_fishing_interval(5, 0)
        assert interval_with_hook < interval

    def test_get_rod_upgrade_price(self):
        price = ConfigManager.get_rod_upgrade_price(0)
        assert price > 0
        price_10 = ConfigManager.get_rod_upgrade_price(10)
        assert price_10 > 0
        price_max = ConfigManager.get_rod_upgrade_price(20)
        assert price_max == 0


class TestNumericId:
    def test_generate_fish_numeric_id(self):
        nid = generate_fish_numeric_id("1", 3, "SR")
        assert nid == "133"

    def test_generate_fish_numeric_id_different_rarity(self):
        nid_n = generate_fish_numeric_id("1", 1, "N")
        nid_sr = generate_fish_numeric_id("1", 1, "SR")
        assert nid_n != nid_sr

    def test_generate_s1_fish_numeric_id(self):
        nid = generate_fish_numeric_id("S1", 0, "N")
        assert nid == "s101"


class TestRarityProbabilities:
    def test_basic_probabilities(self):
        probs = get_rarity_probabilities(0, 0)
        assert "N" in probs
        assert "R" in probs
        assert "SR" in probs
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01

    def test_higher_rod_more_rare(self):
        probs_low = get_rarity_probabilities(1, 1)
        probs_high = get_rarity_probabilities(5, 1)
        assert probs_high.get("SSR", 0) >= probs_low.get("SSR", 0)


class TestCatchFish:
    def test_catch_fish_returns_fish(self):
        fish_pool = ["小鲫鱼", "麦穗鱼", "白条鱼"]
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            fish_pool, 5, 1
        )
        assert fish is not None
        assert rarity is not None
        assert rarity in ["N", "R", "SR", "SSR", "UR", "UTR"]
        assert quantity >= 1

    def test_catch_fish_frame_pity(self):
        fish_pool = ["小鲫鱼", "麦穗鱼", "白条鱼"]
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            fish_pool, 5, 1, frame_pity=150
        )
        assert fish is not None
        assert fish.id == "展示木框"
        assert quantity == 1

    def test_starry_location_does_not_drop_frame_on_pity(self):
        location = ConfigManager.get_location("11")
        assert location is not None
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            location.fish_pool,
            10,
            location.difficulty,
            frame_pity=150,
            location=location,
        )
        assert fish is not None
        assert fish.id != "展示木框"
        assert quantity == 1

    def test_starry_location_appends_meteor_fish_at_one_percent(self, monkeypatch):
        location = ConfigManager.get_location("11")
        fish = ConfigManager.get_fish(location.fish_pool[0])
        meteor_numbers = []
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.random",
            lambda: 0.009,
        )
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.randint",
            lambda start, end: start,
        )

        _try_append_starry_meteor_fish(location, fish, "N", meteor_numbers)

        assert meteor_numbers == [0]

    def test_starry_meteor_fish_doubled_by_duoduo_same_id(self, monkeypatch):
        """真多多后置：掉落流星鱼后复制为两条相同编号。"""
        location = ConfigManager.get_location("11")
        fish = ConfigManager.get_fish(location.fish_pool[0])
        meteor_numbers = []
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.random",
            lambda: 0.0,
        )
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.randint",
            lambda start, end: 123456,
        )

        _try_append_starry_meteor_fish(
            location,
            fish,
            "N",
            meteor_numbers,
            effects={"duoduo_count": 1},
        )

        assert meteor_numbers == [123456, 123456]

    def test_starry_meteor_fish_not_doubled_without_duoduo(self, monkeypatch):
        """无多多时流星鱼只掉 1 条。"""
        location = ConfigManager.get_location("11")
        fish = ConfigManager.get_fish(location.fish_pool[0])
        meteor_numbers = []
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.random",
            lambda: 0.0,
        )
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system.random.randint",
            lambda start, end: 654321,
        )

        _try_append_starry_meteor_fish(
            location,
            fish,
            "N",
            meteor_numbers,
            effects={"duoduo_count": 0},
        )

        assert meteor_numbers == [654321]

    def test_cap_rarity(self):
        assert _cap_rarity(5, "UR") == "UR"
        assert _cap_rarity(0, "UR") == "N"
        assert _cap_rarity(4, "UR") == "UR"
        assert _cap_rarity(7, "UR") == "UR"

    def test_pity_frame_not_doubled_by_duoduo(self):
        """保底展示木框不应被多多药水翻倍。"""
        fish_pool = ["小鲫鱼", "麦穗鱼", "白条鱼"]
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            fish_pool, 5, 1, frame_pity=150, duoduo_count=2
        )
        assert fish is not None
        assert fish.id == "展示木框"
        assert quantity == 1

    def test_pity_frame_not_doubled_by_cat_park_double(self):
        """保底展示木框不应被猫乐园双倍概率翻倍。"""
        fish_pool = ["小鲫鱼", "麦穗鱼", "白条鱼"]
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            fish_pool, 5, 1, frame_pity=150, cat_park_double_rate=0.10
        )
        assert fish is not None
        assert fish.id == "展示木框"
        assert quantity == 1

    def test_pity_frame_not_doubled_by_both(self):
        """保底展示木框不应被多多+猫乐园双倍联合翻倍。"""
        fish_pool = ["小鲫鱼", "麦穗鱼", "白条鱼"]
        fish, rarity, quantity, frame_pity, utr_pity = _catch_fish_with_buffs(
            fish_pool, 5, 1, frame_pity=150,
            duoduo_count=1, cat_park_double_rate=0.10,
        )
        assert fish is not None
        assert fish.id == "展示木框"
        assert quantity == 1


class TestFishPrice:
    def test_calculate_fish_price(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import FishData

        fish = FishData(id="测试鱼", base_price=10)
        price_n = calculate_fish_price(fish, "N", 0)
        price_sr = calculate_fish_price(fish, "SR", 0)
        price_ssr = calculate_fish_price(fish, "SSR", 0)
        assert price_n < price_sr < price_ssr


class TestBuffCalculator:
    def test_no_buffs(self):
        result = FishingBuffCalculator.get_effects_at_time([], datetime.now(), 5, 0, 1)
        assert result["rod_level"] == 5
        assert result["speed_bonus"] == 0

    def test_speed_buff(self):
        now = datetime.now()
        buff = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_SPEED_BOOST,
                "value": 50,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff], now, 5, 0, 1)
        assert result["speed_bonus"] == 50

    def test_double_catch_buff(self):
        now = datetime.now()
        buff = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_DOUBLE_CATCH,
                "value": 1,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff], now, 5, 0, 1)
        assert result["double_catch"] is True

    def test_expired_buff(self):
        now = datetime.now()
        buff = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_SPEED_BOOST,
                "value": 50,
                "start_time": now - timedelta(hours=2),
                "end_time": now - timedelta(hours=1),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff], now, 5, 0, 1)
        assert result["speed_bonus"] == 0

    def test_duoduo_buff_not_stacking(self):
        now = datetime.now()
        buff1 = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_DUODUO,
                "value": 1,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        buff2 = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_DUODUO,
                "value": 1,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff1, buff2], now, 5, 0, 1)
        assert result["duoduo_count"] == 1
        assert result["rod_level"] == 4  # base(5) + rod_bonus(0) - duoduo_count(1)

    def test_duoduo_reduces_rod_level(self):
        now = datetime.now()
        buff = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_DUODUO,
                "value": 1,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff], now, 5, 0, 1)
        assert result["duoduo_count"] == 1
        assert result["rod_level"] == 4  # base(5) + rod_bonus(0) - duoduo_count(1)

    def test_duoduo_rod_level_floor_at_zero(self):
        now = datetime.now()
        buff = type(
            "Buff",
            (),
            {
                "buff_type": BuffEffect.BUFF_TYPE_DUODUO,
                "value": 1,
                "start_time": now - timedelta(minutes=5),
                "end_time": now + timedelta(minutes=55),
            },
        )()
        result = FishingBuffCalculator.get_effects_at_time([buff], now, 0, 0, 1)
        assert result["duoduo_count"] == 1
        assert result["rod_level"] == 0  # floor at 0 (base(0) - duoduo(1) → capped)

    def test_duoduo_buff_default_zero(self):
        result = FishingBuffCalculator.get_effects_at_time([], datetime.now(), 5, 0, 1)
        assert result["duoduo_count"] == 0


class TestApplyDuoduo:
    def test_no_downgrade_for_n(self):
        new_index, quantity = _apply_duoduo(0, 1)
        assert new_index == 0
        assert quantity == 1

    def test_one_downgrade(self):
        new_index, quantity = _apply_duoduo(3, 1)
        assert new_index == 2
        assert quantity == 2

    def test_two_downgrade(self):
        new_index, quantity = _apply_duoduo(3, 2)
        assert new_index == 1
        assert quantity == 4

    def test_downgrade_capped_at_zero(self):
        new_index, quantity = _apply_duoduo(1, 3)
        assert new_index == 0
        assert quantity == 2

    def test_zero_duoduo_count(self):
        new_index, quantity = _apply_duoduo(5, 0)
        assert new_index == 5
        assert quantity == 1


class TestComputeDuoduoQuantity:
    def test_no_duoduo_no_double_rate(self):
        """无多多、无双倍概率 → 倍率1。"""
        assert _compute_duoduo_quantity(0, 0.0) == 1

    def test_duoduo_only(self):
        """仅多多药水 → 2^count。"""
        assert _compute_duoduo_quantity(1, 0.0) == 2
        assert _compute_duoduo_quantity(2, 0.0) == 4
        assert _compute_duoduo_quantity(3, 0.0) == 8

    def test_fractional_low_roll(self, monkeypatch):
        """小数部分低随机值 → 向下取整。"""
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.engine.random.random",
            lambda: 0.05,
        )
        # 1 + 0.10 = 1.10, random < 0.10 → +1 → 2
        assert _compute_duoduo_quantity(0, 0.10) == 2

    def test_fractional_high_roll(self, monkeypatch):
        """小数部分高随机值 → 不+1。"""
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.engine.random.random",
            lambda: 0.50,
        )
        # 1 + 0.10 = 1.10, random >= 0.10 → 1
        assert _compute_duoduo_quantity(0, 0.10) == 1

    def test_combined_duoduo_and_fractional(self, monkeypatch):
        """多多+小数部分联合。"""
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.engine.random.random",
            lambda: 0.03,
        )
        # 2 + 0.06 = 2.06, random < 0.06 → +1 → 3
        assert _compute_duoduo_quantity(1, 0.06) == 3

    def test_combined_duoduo_and_fractional_no_extra(self, monkeypatch):
        """多多+小数部分联合，不触发+1。"""
        monkeypatch.setattr(
            "zhenxun.plugins.zhenxun_plugin_fishing.core.engine.random.random",
            lambda: 0.80,
        )
        # 2 + 0.06 = 2.06, random >= 0.06 → 2
        assert _compute_duoduo_quantity(1, 0.06) == 2

    def test_expected_value_converges(self):
        """大量采样验证期望值收敛到 base + double_rate。"""
        count = 100000
        total = sum(_compute_duoduo_quantity(0, 0.10) for _ in range(count))
        avg = total / count
        # 期望 1.10，允许 ±0.02 误差
        assert abs(avg - 1.10) < 0.02

    def test_expected_value_with_duoduo(self):
        """多多1层 + 0.10 → 期望 2.10。"""
        count = 100000
        total = sum(_compute_duoduo_quantity(1, 0.10) for _ in range(count))
        avg = total / count
        assert abs(avg - 2.10) < 0.02


class TestDisplayProbabilities:
    def test_merge_extended_slots_into_ur(self):
        """索引 5、6 和更高扩展槽的质量全部归入 UR，而不是 N。"""
        probabilities = [0.10, 0.20, 0.10, 0.10, 0.05, 0.10, 0.15, 0, 0.20]

        merged = fishing_engine._merge_probabilities_at_max_rarity(
            probabilities, "UR"
        )

        assert merged[:4] == probabilities[:4]
        assert merged[4] == 0.50
        assert all(probability == 0 for probability in merged[5:])
        assert sum(merged) == sum(probabilities)

    def test_merge_high_level_distribution_preserves_total(self):
        """高等级 16 槽分布归并后保持概率总和，且不污染 N 槽。"""
        probabilities = get_rarity_probabilities_full(20, 1)
        assert len(probabilities) == 16
        assert any(probabilities[index] > 0 for index in range(6, 16))

        merged = fishing_engine._merge_probabilities_at_max_rarity(
            probabilities, "UR"
        )

        assert merged[0] == probabilities[0]
        assert merged[4] == sum(probabilities[4:])
        assert all(probability == 0 for probability in merged[5:])
        assert abs(sum(merged) - sum(probabilities)) < 1e-12

    def test_merge_respects_non_ur_max_rarity(self):
        """非 UR 场景也应把所有超限质量归入自身上限槽。"""
        probabilities = [0.10, 0.20, 0.15, 0.10, 0.15, 0.10, 0.05, 0.15]

        merged = fishing_engine._merge_probabilities_at_max_rarity(
            probabilities, "SSR"
        )

        assert merged == [0.10, 0.20, 0.15, 0.55, 0.0, 0.0, 0.0, 0.0]
        assert sum(merged) == sum(probabilities)

    def test_random_roll_caps_out_of_range_extended_slot_to_ur(self, monkeypatch):
        """抽样器意外返回扩展槽索引时，星空概率表应封顶为 UR。"""
        fish = ConfigManager.get_fish(ConfigManager.get_location("1").fish_pool[0])
        assert fish is not None
        probabilities = [0.0] * 9
        probabilities[8] = 1.0
        monkeypatch.setattr(fishing_engine.random, "choice", lambda _: fish.id)
        monkeypatch.setattr(
            fishing_engine,
            "get_rarity_probabilities_full",
            lambda _rod_level, _difficulty: list(probabilities),
        )
        monkeypatch.setattr(
            fishing_engine,
            "_select_rarity",
            lambda selected_fish, _probabilities: (selected_fish, 8),
        )

        _, rarity, _, _, _ = fishing_engine._single_random_roll(
            [fish.id],
            rod_level=20,
            difficulty=1,
            weather_luck_boost=0,
            weather_lost_wind=False,
            weather_lost_wind_multiplier=1.0,
            location=None,
            is_starry=True,
            max_rarity="UTR",
        )

        assert rarity == "UR"
        assert rarity != "N"

    def test_random_roll_caps_out_of_range_extended_slot_to_ssr(self, monkeypatch):
        """抽样器意外返回扩展槽索引时，普通场景应封顶为 SSR。"""
        fish = ConfigManager.get_fish(ConfigManager.get_location("1").fish_pool[0])
        assert fish is not None
        probabilities = [0.0] * 9
        probabilities[8] = 1.0
        monkeypatch.setattr(fishing_engine.random, "choice", lambda _: fish.id)
        monkeypatch.setattr(fishing_engine.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            fishing_engine,
            "get_rarity_probabilities_full",
            lambda _rod_level, _difficulty: list(probabilities),
        )
        monkeypatch.setattr(
            fishing_engine,
            "_select_rarity",
            lambda selected_fish, _probabilities: (selected_fish, 8),
        )

        _, rarity, _, _, _ = fishing_engine._single_random_roll(
            [fish.id],
            rod_level=20,
            difficulty=1,
            weather_luck_boost=0,
            weather_lost_wind=False,
            weather_lost_wind_multiplier=1.0,
            location=None,
            is_starry=False,
            max_rarity="SSR",
        )

        assert rarity == "SSR"
        assert rarity != "N"

    def test_real_catch_chain_merges_extended_slots_to_non_ur_cap(
        self, monkeypatch
    ):
        """真实捕获链将 max_rarity 传入随机结算，扩展槽命中应得到场景上限。"""
        fish = ConfigManager.get_fish(ConfigManager.get_location("1").fish_pool[0])
        assert fish is not None
        probabilities = [0.0] * 16
        probabilities[5] = 0.20
        probabilities[6] = 0.30
        probabilities[12] = 0.50
        random_values = iter([1.0, 0.999999])
        monkeypatch.setattr(fishing_engine.random, "choice", lambda _: fish.id)
        monkeypatch.setattr(
            fishing_engine.random, "random", lambda: next(random_values)
        )
        monkeypatch.setattr(
            fishing_engine,
            "get_rarity_probabilities_full",
            lambda _rod_level, _difficulty: list(probabilities),
        )

        caught, rarity, quantity, _, _ = _catch_fish_with_buffs(
            [fish.id],
            rod_level=20,
            difficulty=1,
            max_rarity="SSR",
        )

        assert caught == fish
        assert rarity == "SSR"
        assert rarity != "N"
        assert quantity == 1

    def test_cat_park_real_catch_chain_caps_utr_and_extended_slots_to_ur(
        self, monkeypatch
    ):
        """S1 真实捕获链应将 UTR 与更高扩展槽概率质量归并为 UR。"""
        location = ConfigManager.get_location("S1")
        assert location is not None
        fish = ConfigManager.get_fish(location.fish_pool[0])
        assert fish is not None
        probabilities = [0.0] * 16

        monkeypatch.setattr(fishing_engine.random, "choice", lambda _: fish.id)
        monkeypatch.setattr(fishing_engine.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            fishing_engine,
            "get_rarity_probabilities_full",
            lambda _rod_level, _difficulty: list(probabilities),
        )

        for source_index in (5, 12):
            probabilities[:] = [0.0] * 16
            probabilities[source_index] = 1.0
            caught, rarity, quantity, _, _ = _catch_fish_with_buffs(
                location.fish_pool,
                rod_level=20,
                difficulty=location.difficulty,
                max_rarity=location.max_rarity,
                location=location,
                is_cat_park=True,
            )

            assert caught == fish
            assert rarity == "UR"
            assert rarity not in {"UTR", "N"}
            assert quantity == 1

    def test_cat_park_display_probabilities_exclude_utr(self):
        location = ConfigManager.get_location("S1")
        assert location is not None

        display = get_display_probabilities(
            20, location.difficulty, max_rarity=location.max_rarity
        )

        assert display.get("UTR", 0) == 0

    def test_probability_table_keeps_reserved_utr_mass(self):
        """概率表保留 UTR 扩展项，防止被误删或提前并入 UR。"""
        row = RARITY_DISTRIBUTION[9]
        assert row[5] > 0
        assert get_rarity_probabilities_full(10, 1)[5] == row[5]

    def test_starry_random_roll_truncates_reserved_utr_to_ur(self, monkeypatch):
        """集成抽选中星空图不可直接命中概率表 UTR，预留质量应落到 UR。"""
        fish = ConfigManager.get_fish(ConfigManager.get_location("1").fish_pool[0])
        assert fish is not None
        monkeypatch.setattr(fishing_engine.random, "choice", lambda _: fish.id)
        monkeypatch.setattr(fishing_engine.random, "random", lambda: 0.999999)

        _, rarity, is_frame, is_lost_wind_utr, is_material = (
            fishing_engine._single_random_roll(
                [fish.id],
                rod_level=10,
                difficulty=1,
                weather_luck_boost=0,
                weather_lost_wind=False,
                weather_lost_wind_multiplier=1.0,
                location=None,
                is_starry=True,
                max_rarity="UTR",
            )
        )

        assert rarity == "UR"
        assert not is_frame
        assert not is_lost_wind_utr
        assert not is_material

    def test_no_duoduo_same_as_rarity_probabilities(self):
        base = get_rarity_probabilities(5, 1)
        display = get_display_probabilities(5, 1, 0, "UR")
        for key in ["N", "R", "SR", "SSR", "UR"]:
            assert abs(base.get(key, 0) - display.get(key, 0)) < 0.0001

    def test_no_duoduo_ur_truncation(self):
        base = get_rarity_probabilities(10, 1)
        display = get_display_probabilities(10, 1, 0, "UR")
        assert display.get("UTR", 0) == 0
        base_ur = base.get("UR", 0)
        base_utr = base.get("UTR", 0)
        assert abs(display.get("UR", 0) - (base_ur + base_utr)) < 0.0001

    def test_one_duoduo_doubles_all_probs(self):
        base = get_rarity_probabilities(5, 1)
        display = get_display_probabilities(5, 1, 1, "UR")
        for key in ["N", "R", "SR", "SSR", "UR"]:
            assert abs(display.get(key, 0) - base.get(key, 0) * 2) < 0.0001

    def test_one_duoduo_total_is_two(self):
        display = get_display_probabilities(5, 1, 1, "UR")
        total = sum(display.values())
        assert abs(total - 2.0) < 0.01

    def test_two_duoduo_quadruples_all_probs(self):
        base = get_rarity_probabilities(5, 1)
        display = get_display_probabilities(5, 1, 2, "UR")
        for key in ["N", "R", "SR", "SSR", "UR"]:
            assert abs(display.get(key, 0) - base.get(key, 0) * 4) < 0.0001

    def test_duoduo_still_respects_ur_truncation(self):
        display = get_display_probabilities(10, 1, 1, "UR")
        assert display.get("UTR", 0) == 0

    def test_three_duoduo_octuples(self):
        base = get_rarity_probabilities(5, 1)
        display = get_display_probabilities(5, 1, 3, "UR")
        for key in ["N", "R", "SR", "SSR", "UR"]:
            assert abs(display.get(key, 0) - base.get(key, 0) * 8) < 0.0001

    def test_zero_duoduo_sum_is_one(self):
        display = get_display_probabilities(5, 1, 0, "UR")
        total = sum(display.values())
        assert abs(total - 1.0) < 0.01

    def test_ssr_max_rarity_truncation(self):
        full = get_rarity_probabilities_full(5, 1)
        display = get_display_probabilities(5, 1, 0, "SSR")
        assert display.get("UR", 0) == 0
        assert display.get("UTR", 0) == 0
        expected_ssr = sum(full[3:])
        assert abs(display["SSR"] - expected_ssr) < 0.0001
