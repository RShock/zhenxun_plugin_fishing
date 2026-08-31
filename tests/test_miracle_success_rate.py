"""奇迹子集搜索的确定性正确性与理论成功率性质测试。"""

from __future__ import annotations

import json
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
from zhenxun.plugins.zhenxun_plugin_fishing.models import user_mutations
from zhenxun.plugins.zhenxun_plugin_fishing.models.user_mutations import (
    apply_try_claim_miracle,
)

BACKPACK_SIZES = (24, 25, 26)
FIXED_SEEDS = (0, 1, 7, 42, 20260715)
DEBUG_LOG_PREFIX = "[奇迹兑换调试] "


def parse_debug_records(messages):
    return [json.loads(message.removeprefix(DEBUG_LOG_PREFIX)) for message in messages]


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

    def test_large_backpack_prefers_distinct_ids(self):
        candidates = [("backpack", {"id": value}) for value in range(30)]
        candidates.extend(("backpack", {"id": 0}) for _ in range(10))

        indices = user_mutations._select_miracle_search_indices(candidates, 26)

        assert len(indices) == 26
        assert len({candidates[index][1]["id"] for index in indices}) == 26

    def test_large_backpack_retries_with_a_new_candidate_set(self, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import starry_system

        user = SimpleNamespace(
            user_id="retry-user",
            starry_fish=[{"id": value} for value in range(41)],
            items={},
            star_frames=0,
        )
        sample_calls = []
        find_calls = []

        def fake_sample(population, count):
            sample_calls.append(list(population))
            return list(population[:count]) if len(sample_calls) == 1 else list(population[-count:])

        def fake_find(values):
            find_calls.append(list(values))
            return None if len(find_calls) == 1 else [0]

        monkeypatch.setattr(user_mutations.random, "sample", fake_sample)
        monkeypatch.setattr(starry_system, "find_miracle_subset", fake_find)

        claim = apply_try_claim_miracle(user, set())

        assert claim is not None
        assert find_calls == [list(range(26)), list(range(15, 41))]
        assert claim["consumed_ids"] == ["000015"]
        assert len(user.starry_fish) == 40

    def test_large_backpack_miss_writes_detailed_debug_log(self, monkeypatch):
        user = SimpleNamespace(
            user_id="large-miss-user",
            starry_fish=[{"id": 0} for _ in range(101)],
            items={},
            star_frames=0,
        )
        messages = []
        monkeypatch.setattr(
            user_mutations.logger, "info", lambda message: messages.append(message)
        )
        find_calls = []
        from zhenxun.plugins.zhenxun_plugin_fishing.core import starry_system

        def fake_find(values):
            find_calls.append(values)
            return None

        monkeypatch.setattr(starry_system, "find_miracle_subset", fake_find)

        claim = apply_try_claim_miracle(user, set())

        assert claim is None
        assert len(find_calls) == 2
        assert all(message.startswith(DEBUG_LOG_PREFIX) for message in messages)
        assert all(len(message) < 900 for message in messages)
        records = parse_debug_records(messages)
        exchange_ids = {record["exchange_id"] for record in records}
        assert len(exchange_ids) == 1
        assert {record["stage"] for record in records} == {"search", "miss"}
        assert {
            record["search_round"]
            for record in records
            if record["record_type"] == "summary"
        } == {1, 2}
        search_records = [record for record in records if record["stage"] == "search"]
        miss_summary = next(
            record
            for record in records
            if record["stage"] == "miss" and record["record_type"] == "summary"
        )
        assert search_records[0]["user_id"] == "large-miss-user"
        assert search_records[0]["candidate_count"] == 101
        assert search_records[0]["search_count"] == 26
        assert any(record["record_type"] == "candidates" for record in search_records)
        window = next(
            record for record in search_records if record["record_type"] == "search_window"
        )
        assert len(window["ids"]) == 26
        assert miss_summary["matched_count"] == 0
        assert miss_summary["failure_reason"] == "no_subset_in_search_window"
        assert miss_summary["remaining_count"] == 101

    def test_any_miss_writes_full_inventory_and_window(self, monkeypatch):
        user = SimpleNamespace(
            user_id="small-miss-user",
            starry_fish=[
                {"id": "000001"},
                {"id": "000002"},
                {"id": "000003"},
            ],
            items={},
            star_frames=0,
        )
        messages = []
        monkeypatch.setattr(
            user_mutations.logger, "info", lambda message: messages.append(message)
        )

        assert apply_try_claim_miracle(user, set()) is None

        records = parse_debug_records(messages)
        assert {record["stage"] for record in records} == {"search", "miss"}
        search_records = [record for record in records if record["stage"] == "search"]
        candidates = next(
            record for record in search_records if record["record_type"] == "candidates"
        )
        window = next(
            record
            for record in search_records
            if record["record_type"] == "search_window"
        )
        miss_summary = next(
            record
            for record in records
            if record["stage"] == "miss" and record["record_type"] == "summary"
        )
        assert [item["id"] for item in candidates["values"]] == [
            "000001",
            "000002",
            "000003",
        ]
        assert window["offset"] == 0
        assert window["count"] == 3
        assert window["indices"] == [0, 1, 2]
        assert window["ids"] == ["000001", "000002", "000003"]
        assert miss_summary["candidate_count"] == 3
        assert miss_summary["window_start"] == 0
        assert miss_summary["window_end"] == 2
        assert miss_summary["remaining_count"] == 3

    def test_large_backpack_claim_log_contains_match_and_remaining_inventory(
        self, monkeypatch
    ):
        user = SimpleNamespace(
            user_id="large-claim-user",
            starry_fish=[
                {"id": 123456},
                {"id": 7654321},
                *({"id": 0} for _ in range(100)),
            ],
            items={},
            star_frames=0,
        )
        messages = []
        monkeypatch.setattr(
            user_mutations.logger, "info", lambda message: messages.append(message)
        )
        monkeypatch.setattr(user_mutations.random, "randrange", lambda _size: 0)

        claim = apply_try_claim_miracle(user, set())

        assert claim is not None
        records = parse_debug_records(messages)
        claimed = next(
            record
            for record in records
            if record["stage"] == "claimed" and record["record_type"] == "summary"
        )
        assert claimed["matched_sum_mod"] == 7777777
        matched = [record for record in records if record["record_type"] == "matched"]
        assert [item["id"] for record in matched for item in record["values"]] == [
            "123456",
            "7654321",
        ]
        assert claimed["remaining_count"] == 100

    def test_monitoring_batch_continues_after_inventory_drops_to_40(
        self, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import starry_system

        user = SimpleNamespace(
            user_id="batch-monitor-user",
            starry_fish=[{"id": 0} for _ in range(41)],
            items={},
            star_frames=0,
        )
        messages = []
        calls = []

        def fake_find_miracle_subset(values):
            calls.append(len(values))
            return [0] if len(calls) == 1 else None

        monkeypatch.setattr(starry_system, "find_miracle_subset", fake_find_miracle_subset)
        monkeypatch.setattr(
            user_mutations.logger, "info", lambda message: messages.append(message)
        )

        claims = user_mutations.apply_try_claim_miracles(user, dirty=set())

        records = parse_debug_records(messages)
        summaries = [
            record for record in records if record["record_type"] == "summary"
        ]
        assert len(claims) == 1
        assert calls == [26, 26, 26]
        assert len({record["exchange_id"] for record in records}) == 1
        assert [
            (record["attempt"], record["search_round"], record["stage"])
            for record in summaries
        ] == [
            (1, 1, "search"),
            (1, 1, "claimed"),
            (2, 1, "search"),
            (2, 2, "search"),
            (2, 2, "miss"),
        ]
        assert all(record["initial_held_count"] == 41 for record in summaries)
        search_summaries = [
            record for record in summaries if record["stage"] == "search"
        ]
        assert [record["candidate_count"] for record in search_summaries] == [41, 40, 40]
        assert summaries[-1]["held_count"] == 40
        assert summaries[-1]["remaining_count"] == 40

    def test_legacy_fish_displays_the_full_id_used_by_miracle(self):
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
        assert claim["consumed_ids"] == ["990957", "36786820"]
        assert user.starry_fish == []
        assert "36786820|meteor_fish" not in user.items
        assert user.star_frames == 1

    def test_legacy_seven_digit_id_is_shown_without_truncation(self):
        user = SimpleNamespace(
            starry_fish=[],
            starry_exhibition=[],
            items={
                "7777777|meteor_fish": {
                    "item_type": "meteor_fish",
                    "count": 1,
                }
            },
            star_frames=0,
        )

        claim = apply_try_claim_miracle(user, set())

        assert claim is not None
        assert claim["consumed_ids"] == ["7777777"]
        assert "7777777|meteor_fish" not in user.items
        assert user.star_frames == 1

    def test_legacy_hidden_digits_explain_a_truncated_seven_seven_sum(self):
        displayed_group = [
            238850,
            20684,
            6612,
            892038,
            517461,
            91368,
            91368,
            124642,
            124642,
            583174,
            3191,
            83747,
        ]
        assert sum(displayed_group) == 2_777_777

        user = SimpleNamespace(
            starry_fish=[{"id": value} for value in displayed_group[1:]],
            starry_exhibition=[],
            items={
                "5238850|meteor_fish": {
                    "item_type": "meteor_fish",
                    "count": 1,
                }
            },
            star_frames=0,
        )

        claim = apply_try_claim_miracle(user, set())

        assert claim is not None
        assert "5238850" in claim["consumed_ids"]
        assert "5238850|meteor_fish" not in user.items

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
