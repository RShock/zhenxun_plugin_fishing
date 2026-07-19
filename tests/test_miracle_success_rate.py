"""奇迹子集搜索的确定性正确性与理论成功率性质测试。"""

from __future__ import annotations

import math
import random

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (
    MIRACLE_MAX_EXACT_N,
    MIRACLE_MOD_BASE,
    find_miracle_subset,
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
