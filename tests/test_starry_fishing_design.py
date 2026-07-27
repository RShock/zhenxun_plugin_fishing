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
        [160, 190, 180, 160, 190],
    ),
    (
        "12",
        "月环港",
        11,
        ["月壳蟹鱼", "潮汐银鲈", "环月飞鱼", "玉兔灯鲷", "灰晶鳕"],
        [210, 250, 230, 210, 240],
    ),
    (
        "13",
        "彗尾瀑",
        12,
        ["彗尾鲑", "焰尘鳟", "长尾星鳅", "白火鲢", "碎冰虹鱼"],
        [270, 330, 300, 280, 310],
    ),
    (
        "14",
        "云鲸庭",
        13,
        ["云须鲸鱼", "鲸歌鲤", "浮庭鲫", "天羽鳐", "雾铃鳕"],
        [370, 440, 400, 380, 430],
    ),
    (
        "15",
        "镜砂海",
        14,
        ["沙星魟", "琉璃沙鳗", "星蝎鲶", "金尘鲷", "海市蜃鱼"],
        [470, 580, 530, 490, 560],
    ),
    (
        "16",
        "极光井",
        15,
        ["极光鳗", "虹幕鲑", "井心灯鱼", "绿辉鲈", "磁光鳟"],
        [620, 750, 680, 640, 730],
    ),
    (
        "17",
        "坠星渊",
        16,
        ["引力鲶", "暗环魟", "奇点鳕", "坠星鳗", "潮汐黑鲤"],
        [820, 1000, 920, 860, 970],
    ),
    (
        "18",
        "晶冕礁",
        17,
        ["晶冠鲷", "棱镜鲫", "星核金鱼", "蓝晶鳟", "冠冕灯鲈"],
        [1100, 1300, 1200, 1100, 1300],
    ),
    (
        "19",
        "停时湖",
        18,
        ["秒针鲑", "回环鳗", "逆刻鲤", "钟摆鲈", "永昼银鱼"],
        [1400, 1700, 1600, 1500, 1600],
    ),
    (
        "20",
        "愿星岸",
        19,
        ["奇迹锦鲤", "终星鳐", "愿核灯鱼", "彼岸银鲑", "九曜梦鱼"],
        [1900, 2300, 2100, 1900, 2200],
    ),
]

STAR_ROD_PRICES = {
    11: 637500,
    12: 768000,
    13: 1000000,
    14: 1400000,
    15: 1900000,
    16: 2600000,
    17: 3500000,
    18: 4700000,
    19: 6300000,
    20: 8300000,
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
            234.9,
            304.3,
            397.7,
            539.1,
            701.9,
            912.8,
            1219.7,
            1601.4,
            2081.8,
            2775.8,
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
            find_starry_miracle_subset([1, 2, 4, 8], target=31, mod_base=10_000_000)
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

    def test_miracle_subset_searches_all_items_when_above_legacy_cap(self):
        """超过旧上限后仍应搜索全部背包，不能漏掉小编号参与的解。"""
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

        # 唯一解依赖旧 top-26 会挤出的小编号，现应仍能精确找到。
        big_noise = [9_000_001] * MIRACLE_MAX_EXACT_N
        crowded = big_noise + [3, 7_777_777 - 3]
        indices = find_starry_miracle_subset(crowded)
        assert indices is not None
        assert sum(crowded[i] for i in indices) % 10_000_000 == 7_777_777

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
        miracle_bag = [
            {"id": 999999, "score": 1.0, "location_id": "11"} for _ in range(7)
        ]
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
        assert "consumed_ids" in info
        assert len(info["consumed_ids"]) == info["subset_count"]
        # 6 位补零编号，便于收杆页小字展示
        assert all(isinstance(x, str) and len(x) == 6 for x in info["consumed_ids"])
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
        for claim in claims:
            assert claim.get("consumed_ids")
            assert len(claim["consumed_ids"]) == claim["subset_count"]
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
        rod_bonus = (
            20 - STARRY_FISH_ROD_BONUS_THRESHOLD
        ) * STARRY_FISH_ROD_BONUS_PER_LEVEL
        expected = STARRY_FISH_DROP_RATE + rod_bonus + STARRY_FISH_SOLAR_WIND_BONUS
        assert rate == pytest.approx(expected)
        assert rate == pytest.approx(0.125)
        # 明确不是乘算
        multiplied = (STARRY_FISH_DROP_RATE + rod_bonus) * 1.5
        assert rate != pytest.approx(multiplied)

    def test_flash_potion_doubles_final_starry_fish_drop_rate(self):
        """闪光先包含太阳风加成，再把合计后的最终掉率翻倍。"""
        normal = get_starry_fish_drop_rate(rod_level=20, solar_wind=True)
        flash = get_starry_fish_drop_rate(
            rod_level=20, gamma_ray_burst=True
        )

        assert flash == pytest.approx(normal * 2)
        assert flash == pytest.approx(0.25)

    def test_flash_potion_drop_rate_is_capped_at_one(self):
        assert get_starry_fish_drop_rate(
            rod_level=300, gamma_ray_burst=True
        ) == pytest.approx(1.0)

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
            "6_all_odd",
            "star_airplane",
        }
        assert scored.raw_score == pytest.approx(16.853252, abs=0.000001)
        assert scored.display_score == 17
        assert scored.reward_pool == "ultimate"
        assert not any(
            feature.label.startswith(("3_", "4_", "5_")) for feature in scored.features
        )  # 每个窗口家族内仍由 6 位长段吸收短段

    def test_pair_features_two_and_three_pair(self):
        """两对：相邻两段长度≥2且数字不同；三对：3段长度2且中间与两侧不同。三对吸收两对。
        命中葫芦时两对被葫芦吸收，不单独计分。"""
        # 001123: runs=[00, 11, 2, 3], 两对(00+11)且无葫芦 → 纯两对
        two = score_starry_fish("001123")
        labels = {f.label for f in two.features}
        assert "two_pair" in labels
        assert "three_pair" not in labels
        assert "full_house" not in labels
        assert any(
            f.score == pytest.approx(1.595508)
            for f in two.features
            if f.label == "two_pair"
        )

        # 001122: runs=[00, 11, 22], 三段长度2且中间与两侧不同 → 三对
        three = score_starry_fish("001122")
        labels = {f.label for f in three.features}
        assert "three_pair" in labels
        assert "two_pair" not in labels  # 同家族最大匹配
        assert any(
            f.score == pytest.approx(3.091515)
            for f in three.features
            if f.label == "three_pair"
        )

        # 001100: runs=[00, 11, 00], 两侧相同但中间不同 → 仍是三对
        three_same_sides = score_starry_fish("001100")
        labels = {f.label for f in three_same_sides.features}
        assert "three_pair" in labels
        assert "two_pair" not in labels

        # 001011: runs=[00, 1, 0, 11], 对子不相邻 → 不构成两对
        non_adjacent = score_starry_fish("001011")
        labels = {f.label for f in non_adjacent.features}
        assert "two_pair" not in labels
        assert "three_pair" not in labels

    def test_full_house_feature(self):
        """葫芦：5 位窗口 AAABB / AABBB；存在即计一次。
        命中葫芦时两对被吸收，不单独计分。"""
        aaabb = score_starry_fish("000112")
        labels = {f.label for f in aaabb.features}
        assert "full_house" in labels
        assert any(
            f.score == pytest.approx(2.454693)
            for f in aaabb.features
            if f.label == "full_house"
        )

        aabbb = score_starry_fish("001112")
        assert "full_house" in {f.label for f in aabbb.features}

        # 双窗口命中也不叠分
        both = score_starry_fish("000111")
        fh = [f for f in both.features if f.label == "full_house"]
        assert len(fh) == 1

        # 000011 同时有两对结构和葫芦(00011=AAABB)，两对应被葫芦吸收
        absorbed = score_starry_fish("000011")
        labels = {f.label for f in absorbed.features}
        assert "full_house" in labels
        assert "two_pair" not in labels

        # 非葫芦：000011 是 4+2，不是 3+2
        not_fh = score_starry_fish("000011")
        # 000011 windows: 00001=[4,1], 00011=[3,2] -> 后窗是葫芦！
        # 用 000001：windows 00000=[5], 00001=[4,1]
        not_fh = score_starry_fish("000001")
        assert "full_house" not in {f.label for f in not_fh.features}

    def test_all_odd_and_all_even_features(self):
        odd_score = score_starry_fish("135791")
        odd_labels = {f.label for f in odd_score.features}
        assert "6_all_odd" in odd_labels
        assert "6_all_even" not in odd_labels
        assert next(
            f for f in odd_score.features if f.label == "6_all_odd"
        ).score == pytest.approx(1.806180)

        even_score = score_starry_fish("024680")
        even_labels = {f.label for f in even_score.features}
        assert "6_all_even" in even_labels
        assert "6_all_odd" not in even_labels
        assert next(
            f for f in even_score.features if f.label == "6_all_even"
        ).score == pytest.approx(1.806180)

        mixed_score = score_starry_fish("123456")
        mixed_labels = {f.label for f in mixed_score.features}
        assert "6_all_odd" not in mixed_labels
        assert "6_all_even" not in mixed_labels

    def test_chunk_sequence_feature(self):
        for number, mode in (
            ("111213", "2+2+2"),
            ("131211", "2+2+2"),
            ("100101", "3+3"),
            ("101100", "3+3"),
            ("000001", "3+3"),
        ):
            scored = score_starry_fish(number)
            feature = next(f for f in scored.features if f.label == "chunk_sequence")
            assert feature.score == pytest.approx(2.658763)
            assert mode in feature.note

        for number in ("111315", "100102", "999000"):
            assert "chunk_sequence" not in {
                f.label for f in score_starry_fish(number).features
            }

    def test_pihu_is_fallback_only(self):
        pihu = score_starry_fish("002150")
        assert [feature.label for feature in pihu.features] == ["pihu"]
        assert pihu.raw_score == pytest.approx(0.802444)
        assert pihu.display_score == 1
        # 002150 中 0 出现三次（位 1,2,6），只标记同号位而非整段 1-6
        assert pihu.features[0].span == "1-2,6"

        # 虽有至少三个 1，但已经命中 3 位回文，不能再叠屁胡。
        patterned = score_starry_fish("101245")
        assert "3_palindrome" in {f.label for f in patterned.features}
        assert "pihu" not in {f.label for f in patterned.features}

        # 连号本身也会阻止屁胡兜底。
        sequence = score_starry_fish("000001")
        assert "chunk_sequence" in {f.label for f in sequence.features}
        assert "pihu" not in {f.label for f in sequence.features}

        # 没有任意数字达到 3 次时，即使无其他番型也不能屁胡。
        no_triple = score_starry_fish("024579")
        assert "pihu" not in {f.label for f in no_triple.features}


    def test_pihu_digit_mark_only_same_numbers(self):
        """屁胡只高亮同号数字；卡片外壳按奖池稀有度染色（≥15 分 UTR）。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render.base import (
            RARITY_COLORS,
            _starry_feature_digit_styles,
            build_starry_fish_cards,
        )

        # 屁胡 display_score=1 → 低级奖池 → R
        scored = score_starry_fish("002150")
        assert scored.reward_pool == "low"
        mask, colors, texts = _starry_feature_digit_styles(
            scored.features,
            scored.id_text,
            reward_pool=scored.reward_pool,
        )
        assert mask == [True, True, False, False, False, True]
        assert colors[0] == RARITY_COLORS["R"]
        assert colors[2] is None
        assert texts[0] == "#ffffff"

        cards = build_starry_fish_cards([{"id": "002150", "location_id": "11"}])
        assert len(cards) == 1
        assert cards[0]["pool_rarity"] == "R"
        assert cards[0]["pool_color"] == RARITY_COLORS["R"]
        # 对比文字色必须存在且与背景色搭配（暗底→白字，亮底→深字）
        assert cards[0]["pool_text_color"] in ("#ffffff", "#1f2937")

        # 奖池分档：无/低/中/高/究极 → N/R/SR/SSR/UR；≥15 分 → UTR
        from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import StarryFeature

        feat = StarryFeature("pihu", "pihu", "1,2,6", 0.802444)
        for pool, rarity in (
            ("none", "N"),
            ("low", "R"),
            ("middle", "SR"),
            ("high", "SSR"),
            ("ultimate", "UR"),
        ):
            _mask, pool_colors, _ = _starry_feature_digit_styles(
                [feat],
                "002150",
                reward_pool=pool,
            )
            assert pool_colors[0] == RARITY_COLORS[rarity]

        _mask, utr_colors, _ = _starry_feature_digit_styles(
            [feat],
            "002150",
            reward_pool="ultimate",
            display_score=15,
        )
        assert utr_colors[0] == RARITY_COLORS["UTR"]

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

    def test_middle_pool_cat_frame_grants_three(self):
        cat_frame = next(
            item
            for item in STARRY_REWARD_POOL_ITEMS["middle"]
            if item["key"] == "cat_frame"
        )
        assert cat_frame["count"] == 3

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
        low_frag = next(
            item for item in low_items if item["key"] == "lottery_fragment_low"
        )
        assert low_frag["name"] == "中级抽奖碎片"
        mid_items = STARRY_REWARD_POOL_ITEMS["middle"]
        mid_frag = next(
            item for item in mid_items if item["key"] == "lottery_fragment_mid"
        )
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
        from zhenxun.plugins.zhenxun_plugin_fishing.items.potion_use import (
            _normalize_utr_fish_name,
        )

        assert _normalize_utr_fish_name(" 金鱼 ") == "金鱼"
        assert _normalize_utr_fish_name("金鱼 UTR") == "金鱼"
        assert _normalize_utr_fish_name("金鱼UTR") == "金鱼"
        assert _normalize_utr_fish_name("") == ""


class TestStarryFramePityFreeze:
    def test_starry_map_freezes_frame_pity(self):
        """11-20 星空图不累计木框保底。"""
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
            if not is_starry_location(item.id) and not str(item.id).lower().startswith(
                "s"
            ):
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
        if fish is not None and getattr(fish, "id", None) in ("展示木框", "木框"):
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
            if not is_starry_location(item.id) and not str(item.id).lower().startswith(
                "s"
            ):
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
        assert rarity != "UTR" or getattr(fish, "id", None) in ("展示木框", "木框")

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
        if (
            rarity == "UTR"
            and fish is not None
            and getattr(fish, "id", None) not in ("展示木框", "木框")
        ):
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
            item
            for item in ConfigManager.get_locations()
            if is_starry_location(item.id)
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
        assert not any("木框保底" in h for h in hints)
