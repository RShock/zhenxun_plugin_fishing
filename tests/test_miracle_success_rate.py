"""奇迹子集搜索的确定性正确性与理论成功率性质测试。"""

from __future__ import annotations

import math
import random

import pytest
from types import SimpleNamespace

from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
    MIRACLE_MAX_EXACT_N,
    MIRACLE_MOD_BASE,
    MIRACLE_TARGET,
    find_miracle_subset,
)
from zhenxun.plugins.zhenxun_plugin_fishing.models.user_mutations import (
    apply_try_claim_miracle,
)

BACKPACK_SIZES = (24, 25, 26)
FIXED_SEEDS = (0, 1, 7, 42, 20260715)


def theoretical_rate(n: int, mod_base: int = MIRACLE_MOD_BASE) -> float:
    """按独立均匀子集和近似计算至少命中一次的概率。"""
    return 1.0 - math.exp(-((1 << n) - 1) / mod_base)


def _brute_force_has_subset(values: list[int], target: int, mod_base: int) -> bool:
    """穷举小输入，作为 MITM 搜索的独立正确性判据。"""
    for mask in range(1, 1 << len(values)):
        total = sum(value for index, value in enumerate(values) if mask >> index & 1)
        if total % mod_base == target % mod_base:
            return True
    return False


class TestMiracleSubsetSearch:
    def test_exhibition_fish_never_participates_or_gets_consumed(self):
        user = SimpleNamespace(
            starry_fish=[{"id": "999999"} for _ in range(7)],
            starry_exhibition=[{"id": "777784", "display_score": 9}],
            items={},
            star_frames=0,
        )
        dirty: set[str] = set()

        claim = apply_try_claim_miracle(user, dirty)

        assert claim is None
        assert len(user.starry_fish) == 7
        assert user.starry_exhibition == [{"id": "777784", "display_score": 9}]
        assert user.star_frames == 0
        assert dirty == set()

    def test_legacy_item_meteor_fish_participates_and_is_consumed(self):
        user = SimpleNamespace(
            starry_fish=[{"id": "999999"} for _ in range(7)],
            starry_exhibition=[],
            items={
                "777784|meteor_fish": {"item_type": "meteor_fish", "count": 1},
                "time_potion|potion": {"item_type": "potion", "count": 2},
            },
            star_frames=0,
        )
        dirty: set[str] = set()

        claim = apply_try_claim_miracle(user, dirty)

        assert claim is not None
        assert "777784" in claim["consumed_ids"]
        assert "777784|meteor_fish" not in user.items
        assert user.items["time_potion|potion"]["count"] == 2
        assert user.star_frames == 1
        assert "items" in dirty

    def test_nine_digit_legacy_fish_can_join_mixed_miracle(self):
        user = SimpleNamespace(
            starry_fish=[{"id": "990957"}],
            starry_exhibition=[],
            items={
                "36786820|meteor_fish": {
                    "item_type": "meteor_fish",
                    "count": 1,
                }
            },
            star_frames=0,
        )

        claim = apply_try_claim_miracle(user, set())

        assert claim is not None
        assert claim["consumed_ids"] == ["990957", "786820"]
        assert user.starry_fish == []
        assert "36786820|meteor_fish" not in user.items
        assert user.star_frames == 1

    def test_miracle_max_exact_n_covers_practical_sizes(self):
        assert MIRACLE_MAX_EXACT_N >= max(BACKPACK_SIZES)

    @pytest.mark.parametrize("seed", FIXED_SEEDS)
    def test_seeded_search_matches_brute_force(self, seed: int):
        """固定种子生成小问题，验证搜索结果与穷举真值一致。"""
        mod_base = 97
        rng = random.Random(seed)
        values = [rng.randrange(mod_base) for _ in range(10)]
        target = rng.randrange(mod_base)

        indices = find_miracle_subset(
            values,
            target=target,
            mod_base=mod_base,
            max_exact_n=len(values),
        )

        assert (indices is not None) is _brute_force_has_subset(
            values, target, mod_base
        )
        if indices is not None:
            assert indices
            assert len(indices) == len(set(indices))
            assert all(0 <= index < len(values) for index in indices)
            assert sum(values[index] for index in indices) % mod_base == target

    def test_theoretical_curve_is_strictly_increasing_for_practical_sizes(self):
        rates = [theoretical_rate(n) for n in BACKPACK_SIZES]

        assert all(0.0 < rate < 1.0 for rate in rates)
        assert rates == sorted(rates)
        assert len(set(rates)) == len(rates)

    def test_truncation_prevents_memory_explosion_on_large_candidate_list(self):
        """候选数远超 max_exact_n 时不会内存爆炸，且仍能找到有效解。"""
        n = 200
        values = [7777777] + [0] * (n - 1)
        indices = find_miracle_subset(values, max_exact_n=MIRACLE_MAX_EXACT_N)
        assert indices is not None
        assert len(indices) == 1
        assert 0 <= indices[0] < n
        assert sum(values[i] for i in indices) % MIRACLE_MOD_BASE == MIRACLE_TARGET % MIRACLE_MOD_BASE

    def test_truncation_finds_solution_when_top_n_contain_valid_subset(self):
        """大候选列表中，编号最大的 N 条包含解时能正确返回。"""
        n = 100
        values = list(range(n - MIRACLE_MAX_EXACT_N + 1))
        # 在高编号区域放两条能凑出 target 的鱼
        values.extend([3888889, 3888888])
        indices = find_miracle_subset(values, max_exact_n=MIRACLE_MAX_EXACT_N)
        assert indices is not None
        assert all(0 <= i < len(values) for i in indices)
        assert sum(values[i] for i in indices) % MIRACLE_MOD_BASE == MIRACLE_TARGET % MIRACLE_MOD_BASE
