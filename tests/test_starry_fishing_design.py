from __future__ import annotations

from datetime import date, datetime

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
from zhenxun.plugins.zhenxun_plugin_fishing.constants import (
    RARITY_MULTIPLIER,
    STARRY_FISH_DROP_RATE,
    STARRY_FISH_ROD_BONUS_PER_LEVEL,
    STARRY_FISH_ROD_BONUS_THRESHOLD,
    STARRY_FISH_SOLAR_WIND_BONUS,
    get_display_probabilities,
)
from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
    compare_starry_fish,
    expand_starry_fish_with_duoduo,
    format_starry_fish_id,
    generate_starry_fish_id,
    draw_starry_reward,
    get_reward_pool,
    get_starry_fish_drop_rate,
    score_starry_fish,
    STARRY_REWARD_POOL_ITEMS,
)
from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
    find_miracle_subset as find_starry_miracle_subset,
)

STAR_MAPS = [
    (
        "11",
        "牛奶河",
        10,
        ["月乳鲫", "银匙鳐", "星沫鳗", "奶冠鲤", "银河灯鱼"],
        [169, 183, 175, 172, 179],
    ),
    (
        "12",
        "月环港",
        11,
        ["月壳蟹鱼", "潮汐银鲈", "环月飞鱼", "玉兔灯鲷", "灰晶鳕"],
        [194, 210, 200, 198, 206],
    ),
    (
        "13",
        "彗尾瀑",
        12,
        ["彗尾鲑", "焰尘鳟", "长尾星鳅", "白火鲢", "碎冰虹鱼"],
        [221, 239, 230, 226, 235],
    ),
    (
        "14",
        "星砂漠",
        13,
        ["沙星魟", "琉璃沙鳗", "星蝎鲶", "金尘鲷", "海市蜃鱼"],
        [253, 275, 264, 259, 269],
    ),
    (
        "15",
        "云鲸庭",
        14,
        ["云须鲸鱼", "鲸歌鲤", "浮庭鲫", "天羽鳐", "雾铃鳕"],
        [290, 314, 301, 296, 308],
    ),
    (
        "16",
        "极光井",
        15,
        ["极光鳗", "虹幕鲑", "井心灯鱼", "绿辉鲈", "磁光鳟"],
        [332, 360, 346, 339, 353],
    ),
    (
        "17",
        "黑洞涡",
        16,
        ["引力鲶", "暗环魟", "奇点鳕", "坠星鳗", "潮汐黑鲤"],
        [381, 412, 396, 389, 405],
    ),
    (
        "18",
        "水晶星冠",
        17,
        ["晶冠鲷", "棱镜鲫", "星核金鱼", "蓝晶鳟", "冠冕灯鲈"],
        [435, 472, 453, 445, 463],
    ),
    (
        "19",
        "时钟星湖",
        18,
        ["秒针鲑", "回环鳗", "逆刻鲤", "钟摆鲈", "永昼银鱼"],
        [498, 540, 519, 509, 529],
    ),
    (
        "20",
        "奇迹彼岸",
        19,
        ["奇迹锦鲤", "终星鳐", "愿核灯鱼", "彼岸银鲑", "九曜梦鱼"],
        [570, 618, 594, 582, 606],
    ),
]

STAR_ROD_PRICES = {
    11: 637500,
    12: 768000,
    13: 912000,
    14: 1083000,
    15: 1272000,
    16: 1494000,
    17: 1755000,
    18: 2040000,
    19: 2370000,
    20: 2745000,
}

STAR_WISH_RULES = {
    "adjacent_pair": 56.9533,
    "palindrome_3": 52.1703,
    "at_least_three_same": 48.3350,
    "run_3_inc_or_dec": 10.0670,
    "digit_sum_tail_9": 10.0000,
    "mirror_4": 5.8552,
    "at_least_four_same": 8.3073,
    "run_4_inc_or_dec": 0.7791,
    "at_least_five_same": 0.8909,
}

REJECTED_STAR_WISH_RULES = {
    "run_5_inc_or_dec": 0.055,
    "first_last_three_reversed": 0.100,
}


def normalize_meteor_number(value: int | str) -> str:
    return f"{int(value):09d}"


def find_miracle_subset(
    values: list[int], target: int = 999_999_999, mod_base: int = 1_000_000_000
) -> list[int] | None:
    mid = len(values) // 2
    left = [v % mod_base for v in values[:mid]]
    right = [v % mod_base for v in values[mid:]]

    left_sums: dict[int, int] = {}
    for mask in range(1 << len(left)):
        total = 0
        for i, value in enumerate(left):
            if mask & (1 << i):
                total = (total + value) % mod_base
        left_sums.setdefault(total, mask)

    for rmask in range(1 << len(right)):
        total = 0
        for i, value in enumerate(right):
            if rmask & (1 << i):
                total = (total + value) % mod_base
        need = (target - total) % mod_base
        if need in left_sums:
            lmask = left_sums[need]
            indices = [i for i in range(len(left)) if lmask & (1 << i)]
            indices.extend(mid + i for i in range(len(right)) if rmask & (1 << i))
            if indices:
                return indices
    return None


def expected_fish_value(
    base_prices: list[int], rod_level: int, difficulty: int, max_rarity: str = "UR"
) -> float:
    probs = get_display_probabilities(rod_level, difficulty, max_rarity=max_rarity)
    avg_base_price = sum(base_prices) / len(base_prices)
    return sum(
        prob * avg_base_price * RARITY_MULTIPLIER[rarity]
        for rarity, prob in probs.items()
    )


class TestStarryFishingConfig:
    def test_star_maps_11_to_20_exist_with_expected_pools_and_prices(self):
        for location_id, name, difficulty, fish_pool, base_prices in STAR_MAPS:
            location = ConfigManager.get_location(location_id)
            assert location is not None
            assert location.name == name
            assert location.difficulty == difficulty
            assert location.fish_pool == fish_pool
            assert location.max_rarity == "UTR"

            for fish_name, base_price in zip(fish_pool, base_prices):
                fish = ConfigManager.get_fish(fish_name)
                assert fish is not None
                assert fish.base_price == base_price

    def test_star_rod_upgrade_prices_continue_to_level_20(self):
        for target_level, price in STAR_ROD_PRICES.items():
            assert ConfigManager.get_rod_upgrade_price(target_level - 1) == price

    def test_star_map_expected_values_match_design_table(self):
        expected_values = [
            234.4,
            269.0,
            307.2,
            352.3,
            402.7,
            461.8,
            529.2,
            605.3,
            692.7,
            792.7,
        ]
        for (location_id, _, difficulty, _, base_prices), expected in zip(
            STAR_MAPS, expected_values
        ):
            rod_level = int(location_id) - 1
            actual = expected_fish_value(base_prices, rod_level, difficulty)
            assert actual == pytest.approx(expected, abs=0.1)

    def test_star_map_20_unlocks_at_rod_level_19_under_current_rule(self):
        location = ConfigManager.get_location("20")
        assert location is not None
        assert location.difficulty == 19
        assert 19 >= location.difficulty


class TestStarWishNumbers:
    def test_meteor_number_is_normalized_to_9_digits(self):
        assert normalize_meteor_number(1) == "000000001"
        assert normalize_meteor_number("12345678") == "012345678"
        assert normalize_meteor_number(999_999_999) == "999999999"

    def test_common_rule_probabilities_are_not_below_half_percent(self):
        for probability in STAR_WISH_RULES.values():
            assert probability >= 0.5

    def test_rejected_rule_probabilities_are_below_half_percent(self):
        for probability in REJECTED_STAR_WISH_RULES.values():
            assert probability < 0.5

    def test_miracle_subset_uses_mod_1e7_target_7777777(self):
        values = [123_456, 7_654_321, 111_111]
        indices = find_starry_miracle_subset(values)
        assert indices is not None
        assert sum(values[i] for i in indices) % 10_000_000 == 7_777_777

    def test_miracle_subset_returns_none_when_no_non_empty_subset_matches(self):
        assert (
            find_starry_miracle_subset(
                [1, 2, 4, 8], target=31, mod_base=10_000_000
            )
            is None
        )

    def test_miracle_subset_exact_within_practical_backpack_size(self):
        """????? 25~26???????????????"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
            MIRACLE_MAX_EXACT_N,
        )

        filler = list(range(1, MIRACLE_MAX_EXACT_N - 1))  # ?????
        planted = [123_456, 7_654_321]  # 123456+7654321 == 7777777
        values = filler + planted
        assert len(values) <= MIRACLE_MAX_EXACT_N
        indices = find_starry_miracle_subset(values)
        assert indices is not None
        assert sum(values[i] for i in indices) % 10_000_000 == 7_777_777

    def test_miracle_subset_uses_top_max_exact_n_when_above_cap(self):
        """超过 26 条时只对编号最大的 26 条做 MITM。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
            MIRACLE_MAX_EXACT_N,
        )

        filler = list(range(1, MIRACLE_MAX_EXACT_N + 6))
        planted = [123_456, 7_654_321]  # 二者都是最大编号之一
        values = filler + planted
        assert len(values) > MIRACLE_MAX_EXACT_N
        indices = find_starry_miracle_subset(values)
        assert indices is not None
        assert sum(values[i] for i in indices) % 10_000_000 == 7_777_777

        # 唯一解依赖被挤出 top-26 的小数时，应放弃匹配
        big_noise = list(range(900_000, 900_000 + MIRACLE_MAX_EXACT_N))
        crowded = big_noise + [3, 7_777_777 - 3]
        top = sorted(crowded, reverse=True)[:MIRACLE_MAX_EXACT_N]
        assert 3 not in top
        assert find_starry_miracle_subset(crowded) is None

    def test_miracle_subset_finds_singleton_equal_to_target_mod(self):
        values = [7_777_777, 3, 5]
        indices = find_starry_miracle_subset(values)
        assert indices == [0]


    @pytest.mark.asyncio
    async def test_try_claim_miracle_consumes_backpack_and_grants_frame(self, db):
        """?????????? starry_fish ??????? +1??????"""
        from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser

        user, _ = await FishingUser.get_or_create_user("miracle_user_1")
        # 8 ??????????? 7777777
        miracle_bag = [{"id": 999999, "score": 1.0, "location_id": "11"} for _ in range(7)]
        miracle_bag.append({"id": 777784, "score": 1.0, "location_id": "11"})
        miracle_bag.append({"id": 111111, "score": 1.0, "location_id": "11"})  # ????
        user.starry_fish = miracle_bag
        user.starry_exhibition = [
            {"id": 888888, "score": 5.0, "location_id": "11"},
        ]
        user.star_frames = 0
        await user.save()

        info = await FishingUser.try_claim_miracle("miracle_user_1")
        assert info is not None
        assert info["subset_count"] >= 1
        assert info["star_frames"] == 1
        user2 = await FishingUser.get_user("miracle_user_1")
        assert int(user2.star_frames) == 1
        remaining_ids = [int(x.get("id", 0)) for x in (user2.starry_fish or [])]
        # ?????????????
        assert remaining_ids == [111111]
        # ?????
        assert len(user2.starry_exhibition or []) == 1
        assert int((user2.starry_exhibition or [{}])[0].get("id", 0)) == 888888

    @pytest.mark.asyncio
    async def test_try_claim_miracles_can_fire_multiple_times(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser

        user, _ = await FishingUser.get_or_create_user("miracle_user_2")
        def _bag():
            return [{"id": 999999} for _ in range(7)] + [{"id": 777784}]

        user.starry_fish = _bag() + _bag() + [{"id": 100}]
        user.star_frames = 0
        await user.save()

        claims = await FishingUser.try_claim_miracles("miracle_user_2")
        assert len(claims) >= 2
        user2 = await FishingUser.get_user("miracle_user_2")
        assert int(user2.star_frames) >= 2
        remaining = [int(x.get("id", 0)) for x in (user2.starry_fish or [])]
        assert remaining == [100]


    def test_starry_fish_id_is_six_digits(self):
        assert format_starry_fish_id(1) == "000001"
        assert format_starry_fish_id("12345") == "012345"

    def test_starry_fish_drop_rate_base_and_rod_bonus(self):
        assert get_starry_fish_drop_rate() == STARRY_FISH_DROP_RATE
        assert get_starry_fish_drop_rate(rod_level=10) == STARRY_FISH_DROP_RATE
        assert get_starry_fish_drop_rate(rod_level=11) == pytest.approx(
            STARRY_FISH_DROP_RATE + STARRY_FISH_ROD_BONUS_PER_LEVEL
        )
        # Lv.20：超过 10 级 10 级 → +5%
        assert get_starry_fish_drop_rate(rod_level=20) == pytest.approx(
            STARRY_FISH_DROP_RATE
            + (20 - STARRY_FISH_ROD_BONUS_THRESHOLD) * STARRY_FISH_ROD_BONUS_PER_LEVEL
        )

    def test_starry_fish_drop_rate_solar_wind_is_flat_bonus(self):
        """太阳风改为恒定 +2.5%，不与鱼竿加成乘算。"""
        base_with_solar = get_starry_fish_drop_rate(solar_wind=True)
        assert base_with_solar == pytest.approx(
            STARRY_FISH_DROP_RATE + STARRY_FISH_SOLAR_WIND_BONUS
        )
        # 旧逻辑会是 0.05 * 1.5 = 0.075；新逻辑应为 0.05 + 0.025 = 0.075（Lv<=10 时数值巧合相同）
        # 高竿时必须体现绝对加值：Lv.20 + 太阳风 = 10% + 2.5% = 12.5%，而非 10% * 1.5
        rate = get_starry_fish_drop_rate(rod_level=20, solar_wind=True)
        rod_bonus = (20 - STARRY_FISH_ROD_BONUS_THRESHOLD) * STARRY_FISH_ROD_BONUS_PER_LEVEL
        expected = STARRY_FISH_DROP_RATE + rod_bonus + STARRY_FISH_SOLAR_WIND_BONUS
        assert rate == pytest.approx(expected)
        assert rate == pytest.approx(0.125)
        # 明确不是乘算
        multiplied = (STARRY_FISH_DROP_RATE + rod_bonus) * 1.5
        assert rate != pytest.approx(multiplied)

    def test_hengjiyuan_generation_uses_digits_2_to_8(self):
        for _ in range(100):
            fish_id = format_starry_fish_id(generate_starry_fish_id(hengjiyuan=True))
            assert set(fish_id) <= set("2345678")

    def test_six_digit_scoring_matches_design_reference(self):
        scored = score_starry_fish("011110")
        assert scored.display_score == 17
        assert scored.reward_pool == "ultimate"
        assert scored.raw_score == pytest.approx(16.838223, abs=0.00001)

    def test_777777_scores_each_family_independently(self):
        """全同号也属于普通滑梯和镜像回文，各家族独立计分。"""
        scored = score_starry_fish("777777")
        labels = {feature.label for feature in scored.features}

        assert labels == {
            "6_same_run",
            "6_slide",
            "6_palindrome",
            "6_all_big_5_9",
            "star_airplane",
        }
        assert scored.raw_score == pytest.approx(15.047072, abs=0.000001)
        assert scored.display_score == 15
        assert scored.reward_pool == "ultimate"
        assert not any(
            feature.label.startswith(("3_", "4_", "5_"))
            for feature in scored.features
        )  # 每个窗口家族内仍由 6 位长段吸收短段

    def test_pair_features_two_and_three_pair(self):
        """两对/三对：恰好长度 2 的同号连段；三对吸收两对。"""
        two = score_starry_fish("001011")
        labels = {f.label for f in two.features}
        assert "two_pair" in labels
        assert "three_pair" not in labels
        assert any(f.score == pytest.approx(1.359121) for f in two.features if f.label == "two_pair")

        three = score_starry_fish("001122")
        labels = {f.label for f in three.features}
        assert "three_pair" in labels
        assert "two_pair" not in labels  # 同家族最大匹配
        assert any(f.score == pytest.approx(3.091515) for f in three.features if f.label == "three_pair")

        # 4 连同号 + 1 对：只有 1 段长度恰好为 2，不构成两对
        mixed = score_starry_fish("000011")
        labels = {f.label for f in mixed.features}
        assert "two_pair" not in labels
        assert "three_pair" not in labels
        assert "4_same_run" in labels

    def test_full_house_feature(self):
        """葫芦：5 位窗口 AAABB / AABBB；存在即计一次。"""
        aaabb = score_starry_fish("000112")
        labels = {f.label for f in aaabb.features}
        assert "full_house" in labels
        assert any(f.score == pytest.approx(2.454693) for f in aaabb.features if f.label == "full_house")

        aabbb = score_starry_fish("001112")
        assert "full_house" in {f.label for f in aabbb.features}

        # 双窗口命中也不叠分
        both = score_starry_fish("000111")
        fh = [f for f in both.features if f.label == "full_house"]
        assert len(fh) == 1

        # 非葫芦：000011 是 4+2，不是 3+2
        not_fh = score_starry_fish("000011")
        # 000011 windows: 00001=[4,1], 00011=[3,2] -> 后窗是葫芦！
        # 用 000001：windows 00000=[5], 00001=[4,1]
        not_fh = score_starry_fish("000001")
        assert "full_house" not in {f.label for f in not_fh.features}

    def test_starry_reward_pool_boundaries_match_design(self):
        assert get_reward_pool(5) == "middle"
        assert get_reward_pool(6) == "high"
        assert get_reward_pool(10) == "high"
        assert get_reward_pool(11) == "ultimate"


    def test_draw_starry_reward_none_pool_returns_none(self):
        assert draw_starry_reward("none") is None
        assert draw_starry_reward("") is None

    def test_draw_starry_reward_from_known_pools(self):
        import random

        rng = random.Random(0)
        for pool in ("low", "middle", "high", "ultimate"):
            reward = draw_starry_reward(pool, rng=rng)
            assert reward is not None
            assert reward["pool"] == pool
            assert reward["key"]
            assert reward["name"]
            assert reward["count"] >= 1
            keys = {item["key"] for item in STARRY_REWARD_POOL_ITEMS[pool]}
            assert reward["key"] in keys

    def test_high_score_fish_maps_to_high_or_ultimate_pool(self):
        # display_score 6-10 high, 11+ ultimate
        assert get_reward_pool(6) == "high"
        assert get_reward_pool(11) == "ultimate"

    def test_compare_starry_fish_prefers_score_then_larger_id(self):
        assert compare_starry_fish("011110", "000001") == 11110
        assert compare_starry_fish("000000", "999999") == 999999


class TestStarryRewardItemKeys:
    def test_flash_and_utr_reward_keys_in_pools(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
            STARRY_REWARD_POOL_ITEMS,
        )

        high_keys = {item["key"] for item in STARRY_REWARD_POOL_ITEMS["high"]}
        ultimate_keys = {item["key"] for item in STARRY_REWARD_POOL_ITEMS["ultimate"]}
        assert "flash_potion" in high_keys
        assert "utr_select_ticket" in high_keys
        assert "utr_select_ticket" in ultimate_keys

    def test_low_pool_includes_wish_score_bonus(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
            STARRY_REWARD_POOL_ITEMS,
        )

        low_items = STARRY_REWARD_POOL_ITEMS["low"]
        low_keys = {item["key"] for item in low_items}
        assert "wish_score" in low_keys
        # 与其他奖励等概率，共 4 项
        assert len(low_items) == 4
        wish = next(item for item in low_items if item["key"] == "wish_score")
        assert wish["score_bonus"] == 0.5
        assert wish["name"] == "0.5积分"
        low_frag = next(item for item in low_items if item["key"] == "lottery_fragment_low")
        assert low_frag["name"] == "中级抽奖碎片"
        mid_items = STARRY_REWARD_POOL_ITEMS["middle"]
        mid_frag = next(item for item in mid_items if item["key"] == "lottery_fragment_mid")
        assert mid_frag["name"] == "高级抽奖碎片"
        high_items = STARRY_REWARD_POOL_ITEMS["high"]
        high_frag = next(
            item for item in high_items if item["key"] == "lottery_fragment_high"
        )
        assert high_frag["name"] == "究极抽奖碎片"
        # 碎片永远高一级：低/中/高级池各自只有对应高一级碎片
        assert not any("低级" in str(i.get("name", "")) for i in low_items)
        assert not any(i["key"] == "lottery_fragment_low" for i in mid_items)
        assert not any(i["key"] == "lottery_fragment_mid" for i in high_items)

    def test_reward_handlers_cover_flash_and_utr(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import starry_rewards as sr

        assert "flash_potion" in sr._REWARD_HANDLERS
        assert "utr_select_ticket" in sr._REWARD_HANDLERS
        assert "wish_score" in sr._REWARD_HANDLERS
        assert "lottery_fragment_high" in sr._REWARD_HANDLERS
        assert sr._REWARD_HANDLERS["flash_potion"] == ("item", "闪光药水", "potion")
        assert sr._REWARD_HANDLERS["utr_select_ticket"] == (
            "item",
            "utr_select_ticket",
            "ticket",
        )
        assert sr._REWARD_HANDLERS["wish_score"] == ("wish_score", None, None)
        assert "lottery_fragment_high" in sr._FRAGMENT_SPECS
        assert sr._FRAGMENT_SPECS["lottery_fragment_high"]["upgrade_pool"] == "ultimate"

    def test_wish_score_reward_applies_to_user(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.stop_mutations import (
            apply_starry_reward_on_user,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser("test-wish-score")
        user.starry_score_accumulated = 10.0
        dirty: set[str] = set()
        result = apply_starry_reward_on_user(
            user,
            {
                "key": "wish_score",
                "name": "0.5积分",
                "count": 1,
                "score_bonus": 0.5,
                "pool": "low",
                "pool_name": "低级奖池",
            },
            dirty,
            source="catch",
        )
        assert result["granted"] is True
        assert result["score_bonus"] == 0.5
        assert user.starry_score_accumulated == 10.5
        assert "starry_score_accumulated" in dirty

    def test_fragment_upgrade_settles_immediately_on_stop(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.stop_mutations import (
            apply_fragment_upgrades_on_user,
            apply_starry_reward_on_user,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser("test-frag-upgrade")
        dirty: set[str] = set()
        # 预先持有 4 个中级碎片，再发 1 个应立刻合成一次中级奖池
        apply_starry_reward_on_user(
            user,
            {
                "key": "lottery_fragment_low",
                "name": "中级抽奖碎片",
                "count": 4,
                "pool": "low",
            },
            dirty,
            source="seed",
        )
        apply_starry_reward_on_user(
            user,
            {
                "key": "lottery_fragment_low",
                "name": "中级抽奖碎片",
                "count": 1,
                "pool": "low",
            },
            dirty,
            source="catch",
        )
        upgraded = apply_fragment_upgrades_on_user(
            user, dirty, fish_id="123456", display_score=2
        )
        assert upgraded
        assert all(u.get("granted") for u in upgraded)
        assert all(u.get("upgrade_from") == "中级抽奖碎片" for u in upgraded)
        assert all(str(u.get("fish_id")) == "123456" for u in upgraded)
        # 5 个碎片应被消耗
        frag = None
        for key, item in (user.items or {}).items():
            if key.startswith("lottery_fragment_low|"):
                frag = item
                break
        remaining = int(frag["count"]) if frag else 0
        assert remaining == 0


class TestUtrSelectNormalize:
    def test_normalize_utr_fish_name(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.shop.potion_use import (
            _normalize_utr_fish_name,
        )

        assert _normalize_utr_fish_name(" 金鱼 ") == "金鱼"
        assert _normalize_utr_fish_name("金鱼 UTR") == "金鱼"
        assert _normalize_utr_fish_name("金鱼UTR") == "金鱼"
        assert _normalize_utr_fish_name("") == ""



class TestStarryFramePityFreeze:
    def test_starry_map_freezes_frame_pity(self):
        """11-20 星空图不累计展示木框保底。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
            _catch_fish_with_buffs,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import is_starry_location

        loc = None
        for item in ConfigManager.get_locations():
            if is_starry_location(item.id):
                loc = item
                break
        assert loc is not None, "需要至少一张星空图"
        fish, rarity, qty, new_frame, new_utr = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            frame_pity=40,
            location=loc,
        )
        assert new_frame == 40

    def test_normal_map_still_increments_or_resets_frame_pity(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
            _catch_fish_with_buffs,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import is_starry_location

        loc = None
        for item in ConfigManager.get_locations():
            if (not is_starry_location(item.id)
                    and not str(item.id).lower().startswith("s")):
                loc = item
                break
        assert loc is not None
        fish, rarity, qty, new_frame, new_utr = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            frame_pity=10,
            location=loc,
        )
        if fish is not None and getattr(fish, "id", None) == "展示木框":
            assert new_frame == 0
        else:
            assert new_frame > 10



class TestStarryUtrPityAndWeather:
    """11-20 UTR：乱纪元觉醒后启用递进/保底，其他天气不启用。"""

    def _starry_loc(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import is_starry_location

        for item in ConfigManager.get_locations():
            if is_starry_location(item.id):
                return item
        raise AssertionError("需要至少一张星空图")

    def _normal_loc(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import is_starry_location

        for item in ConfigManager.get_locations():
            if not is_starry_location(item.id) and not str(item.id).lower().startswith("s"):
                return item
        raise AssertionError("需要普通地图")

    def test_starry_unlocked_still_requires_chaotic_lost_wind_effect(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
            _catch_fish_with_buffs,
        )

        loc = self._starry_loc()
        fish, rarity, qty, new_frame, new_utr = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            max_rarity="UTR",
            frame_pity=40,
            utr_pity=20,
            weather_lost_wind=False,
            location=loc,
        )
        assert new_frame == 40  # 木框保底仍冻结
        assert new_utr == 20

        fish, rarity, qty, new_frame, new_utr = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            max_rarity="UTR",
            frame_pity=40,
            utr_pity=20,
            weather_lost_wind=True,
            location=loc,
        )
        if rarity == "UTR" and fish is not None:
            assert new_utr == 0
        else:
            assert new_utr == 21

    def test_starry_locked_does_not_count_utr_pity(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
            _catch_fish_with_buffs,
        )

        loc = self._starry_loc()
        fish, rarity, qty, new_frame, new_utr = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            max_rarity="UR",
            frame_pity=40,
            utr_pity=20,
            weather_lost_wind=False,
            location=loc,
        )
        assert new_utr == 20
        assert rarity != "UTR" or getattr(fish, "id", None) == "展示木框"

    def test_normal_map_utr_pity_requires_lost_wind(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.engine import (
            _catch_fish_with_buffs,
        )

        loc = self._normal_loc()
        # 无迷途风：不计 UTR 保底
        _, _, _, _, new_utr_off = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            max_rarity="UTR",
            utr_pity=20,
            weather_lost_wind=False,
            location=loc,
        )
        assert new_utr_off == 20

        # 有迷途风：计 UTR 保底（或出 UTR 归零）
        fish, rarity, _, _, new_utr_on = _catch_fish_with_buffs(
            loc.fish_pool,
            rod_level=max(1, loc.difficulty + 1),
            difficulty=loc.difficulty,
            max_rarity="UTR",
            utr_pity=20,
            weather_lost_wind=True,
            location=loc,
        )
        if rarity == "UTR" and fish is not None and getattr(fish, "id", None) != "展示木框":
            assert new_utr_on == 0
        else:
            assert new_utr_on == 21

    def test_starry_pity_hint_label(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.hints import build_pity_hints

        starry_hints = build_pity_hints(
            total_fish=[],
            frame_pity=0,
            cat_frame_pity=0,
            utr_pity=30,
            display_slots=0,
            upgraded_display_count=0,
            cat_frames=0,
            effects_now=None,
            skip_frame_pity=True,
            is_starry=True,
        )
        assert any("UTR保底" in h and "迷途风" not in h for h in starry_hints)

        normal_hints = build_pity_hints(
            total_fish=[],
            frame_pity=0,
            cat_frame_pity=0,
            utr_pity=30,
            display_slots=0,
            upgraded_display_count=0,
            cat_frames=0,
            effects_now=None,
            skip_frame_pity=True,
            is_starry=False,
        )
        assert any("迷途风UTR保底" in h for h in normal_hints)

    def test_display_prob_starry_utr_unlocked_still_requires_lost_wind(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.probability import (
            calculate_display_probabilities,
        )

        probs = calculate_display_probabilities(
            rod_level=16,
            difficulty=10,
            max_rarity="UTR",
            weather_lost_wind=False,
            starry_utr_unlocked=True,
        )
        assert probs.get("UTR", 0) == 0

        active = calculate_display_probabilities(
            rod_level=16,
            difficulty=10,
            max_rarity="UTR",
            weather_lost_wind=True,
            starry_utr_unlocked=True,
        )
        assert active.get("UTR", 0) > 0

        locked = calculate_display_probabilities(
            rod_level=16,
            difficulty=10,
            max_rarity="UR",
            weather_lost_wind=False,
            starry_utr_unlocked=False,
        )
        assert locked.get("UTR", 0) == 0

    @pytest.mark.asyncio
    async def test_starry_achievement_returns_unlock_message_without_lost_wind(
        self, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            check_achievements_for_location,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import is_starry_location

        location = next(
            item for item in ConfigManager.get_locations() if is_starry_location(item.id)
        )
        fish = ConfigManager.get_fish(location.fish_pool[0])
        assert fish is not None
        collected = {
            (candidate.id, rarity)
            for fish_id in location.fish_pool
            if (candidate := ConfigManager.get_fish(fish_id)) is not None
            for rarity in ["N", "R", "SR", "SSR", "UR"]
        }

        async def _collected(_user_id):
            return collected

        async def _not_completed(_user_id, _key):
            return False

        async def _mark_completed(_user_id, _key):
            return None

        monkeypatch.setattr(FishingUser, "get_user_collected", _collected)
        monkeypatch.setattr(FishingUser, "is_achievement_completed", _not_completed)
        monkeypatch.setattr(FishingUser, "mark_achievement_completed", _mark_completed)

        result = await check_achievements_for_location("starry-message", location)
        message = "\n".join(result["messages"])

        assert "UTR稀有度已对你解锁" in message
        assert "保持乱纪元显示" in message
        assert "迷途风效果" in message

    @pytest.mark.asyncio
    async def test_generate_starry_weather_never_lost_wind(self, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing import weather_service as ws
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import STARRY_LOCATION_IDS

        created = []

        class FakeFilter:
            def __init__(self, *a, **k):
                pass

            async def first(self):
                return None

            async def all(self):
                return []

        class FakeWeather:
            @classmethod
            def filter(cls, *a, **k):
                return FakeFilter()

            @classmethod
            async def get_or_create(cls, **kwargs):
                created.append(
                    kwargs.get("defaults", {}).get("weather_type")
                    or kwargs.get("weather_type")
                )
                return object(), True

        async def _fake_add_buff(**kwargs):
            return None

        monkeypatch.setattr(ws, "FishingWeather", FakeWeather)
        monkeypatch.setattr(ws.FishingBuff, "add_buff", staticmethod(_fake_add_buff))
        ok = await ws.generate_starry_weather()
        assert ok is True
        assert len(created) == len(STARRY_LOCATION_IDS)
        special = {"solar_wind", "meteor_shower", "hengjiyuan"}
        assert all(t in special | {"chaotic_era"} for t in created)
        assert "lost_wind" not in created
        assert sum(1 for t in created if t in special) == 5
        assert sum(1 for t in created if t == "chaotic_era") == 5

    @pytest.mark.asyncio
    async def test_chaotic_windows_follow_each_weather_day_across_23(self, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing import weather_service as ws

        old_weather = type(
            "Weather",
            (),
            {
                "start_time": datetime(2026, 7, 19, 23, 0),
                "end_time": datetime(2026, 7, 20, 23, 0),
            },
        )()
        captured = {}

        class FakeFilter:
            async def all(self):
                return [old_weather]

        class FakeWeather:
            @classmethod
            def filter(cls, **kwargs):
                captured.update(kwargs)
                return FakeFilter()

        monkeypatch.setattr(ws, "FishingWeather", FakeWeather)
        windows = await ws.get_chaotic_era_windows(
            "11", datetime(2026, 7, 20, 22, 50), datetime(2026, 7, 20, 23, 10)
        )

        assert captured["date__in"] == [date(2026, 7, 19), date(2026, 7, 20)]
        assert windows == [
            (datetime(2026, 7, 20, 22, 50), datetime(2026, 7, 20, 23, 0))
        ]


class TestPityHintsSkipFrame:
    def test_skip_frame_pity_flag(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.core.hints import build_pity_hints

        hints = build_pity_hints(
            total_fish=[],
            frame_pity=30,
            cat_frame_pity=0,
            utr_pity=0,
            display_slots=1,
            upgraded_display_count=1,
            cat_frames=0,
            effects_now=None,
            skip_frame_pity=True,
        )
        assert not any("展示木框保底" in h for h in hints)
