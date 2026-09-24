from __future__ import annotations

import json
import math
import pathlib
import subprocess
from dataclasses import replace

import pytest

from s2_first_ten_days import (
    PLAYER_PROFILES,
    audit_opportunities,
    audit_profiles,
    resolve_output_path,
    run,
    run_helper_ten_day_matrix,
    run_opportunity_matrix,
    run_profile_matrix,
)
from s2_mining_simulator import GAME_DATA, RULES, SPECS, SimulationState, strategy_visit


HERE = pathlib.Path(__file__).resolve().parent
RUNNER = HERE / "s2_web_parity_runner.mjs"


def manually_unlock(state: SimulationState, key: str) -> None:
    spec = SPECS[key]
    state.depth = max(state.depth, spec.unlock_depth)
    for required in spec.prerequisites:
        state.levels[required] = max(1, state.levels[required])
    state.credits = 1e30
    for _ in range(spec.manual_target):
        ok, reason = state.upgrade_command([(key, 1)])
        assert ok, reason


def test_v3_uses_local_and_prestige_currencies_with_existing_era_regions() -> None:
    assert GAME_DATA["schemaVersion"] == 3
    assert GAME_DATA["gameVersion"] == "s2-vnext-v3-helper-1"
    assert GAME_DATA["contentVersion"] == "prestige-3"
    assert GAME_DATA["playtestDays"] == 30
    assert [item["key"] for item in GAME_DATA["resources"]] == ["credits", "cores"]
    assert len(GAME_DATA["multiplierRegions"]) == 17
    assert sum(item["status"] == "active" for item in GAME_DATA["multiplierRegions"]) == 15
    assert sum(item["status"] != "active" for item in GAME_DATA["multiplierRegions"]) == 2
    regions = {item["key"]: item for item in GAME_DATA["multiplierRegions"]}
    active = [item for item in GAME_DATA["upgrades"] if item["status"] == "active"]
    removed = {"pressure", "network", "heat", "diversity", "cascade", "precision", "compression", "lens"}
    assert len(active) == 43
    assert not ({item["effectKind"] for item in active} & removed)
    assert all(regions[item["region"]]["status"] == "active" for item in active)
    assert regions["opening_burst"]["status"] != "active"
    planetary = [item for item in GAME_DATA["upgrades"] if item["era"] == "planetary"]
    assert len(planetary) == 3
    assert all(item["status"] != "active" for item in planetary)


def test_batch_command_validates_before_mutating_and_counts_once() -> None:
    state = SimulationState(deterministic=True)
    state.credits = 1e9
    for orders in ([], [("rotary_pick", 0)], [("rotary_pick", -1)],
                   [("rotary_pick", True)], [("rotary_pick", 1.5)],
                   [("rotary_pick", 1), ("unknown", 1)],
                   [("rotary_pick", 101)]):
        assert state.upgrade_command(orders) == (False, "invalid")
        assert state.level("rotary_pick") == 0
    assert state.upgrade_command([("rotary_pick", 2), ("split_tunnel", 1)]) == (True, "locked")
    assert state.level("rotary_pick") == 2
    assert state.total_manual_levels == 2
    assert state.total_manual_commands == 1
    assert state.upgrade_command([("rotary_pick", 1)]) == (True, "")
    assert "rotary_pick" in state.auto_unlocked
    assert state.total_manual_commands == 2


def test_batch_partial_affordability_and_direct_purchase_command_count() -> None:
    state = SimulationState(deterministic=True)
    state.credits = state.cost_for("rotary_pick") + 1
    assert state.upgrade_command([("rotary_pick", 3)]) == (True, "credits")
    assert state.level("rotary_pick") == 1
    assert state.total_manual_commands == 1
    assert state.upgrade_command([("rotary_pick", 1)]) == (False, "credits")
    assert state.total_manual_commands == 1
    state.credits = state.cost_for("rotary_pick")
    assert state.purchase("rotary_pick") == (True, "")
    assert state.total_manual_levels == 2
    assert state.total_manual_commands == 1


def test_purchase_near_epsilon_clamps_balance_to_zero() -> None:
    state = SimulationState(deterministic=True)
    cost = state.cost_for("rotary_pick")
    state.credits = cost - 5e-10

    assert state.purchase("rotary_pick") == (True, "")
    assert state.credits == 0.0
    assert state.total_manual_levels == 1


def test_third_manual_level_permanently_unlocks_automation() -> None:
    state = SimulationState(deterministic=True)
    manually_unlock(state, "rotary_pick")
    assert state.manual_levels["rotary_pick"] == 3
    assert "rotary_pick" in state.auto_unlocked
    assert not state.available("rotary_pick")
    assert state.available("rotary_pick", automatic=True)


def test_auto_queue_has_global_budget_and_protects_three_manual_levels() -> None:
    state = SimulationState(deterministic=True)
    manually_unlock(state, "rotary_pick")
    state.depth = 10000
    manually_unlock(state, "split_tunnel")
    state.credits = state.reserve_cost() + min(state.cost_for("rotary_pick"), state.cost_for("split_tunnel")) + 1
    before = state.total_auto_levels
    bought = state.auto_purchase()
    assert len(bought) <= int(RULES["autoPurchaseBudget"]) == 1
    assert state.total_auto_levels - before == len(bought)
    assert state.credits + 1e-9 >= state.reserve_cost()


def test_same_region_era_handoffs_add_while_speed_lines_multiply() -> None:
    active = [item for item in GAME_DATA["upgrades"] if item["status"] == "active"]
    era_index = {item["key"]: index for index, item in enumerate(GAME_DATA["eras"])}
    checked = 0
    for region in {item["region"] for item in active}:
        lines = sorted(
            (item for item in active if item["region"] == region),
            key=lambda item: era_index[item["era"]],
        )
        if len({item["era"] for item in lines}) < 2:
            continue
        old, new = lines[0], lines[-1]
        state = SimulationState(deterministic=True)
        state.minute = 1440 + 240
        state.auto_unlocked = {item["key"] for item in active[:6]}
        state.levels[old["key"]] = min(2, old["maxLevel"])
        state.levels[new["key"]] = min(2, new["maxLevel"])
        contribution = sum(
            float(item["effectPerLevel"]) * state.level(item["key"])
            for item in (old, new)
        )
        if region == "speed":
            expected = math.prod(
                (1 + float(item["effectPerLevel"])) ** state.level(item["key"])
                for item in (old, new)
            )
        elif region in {"resonance", "shift_relay"}:
            expected = 1 + contribution * len(state.auto_unlocked)
        elif region == "momentum":
            expected = 1 + contribution
        elif region == "crit_chance":
            expected = 1 + min(0.65, contribution) * float(RULES["baseCriticalDamage"])
        else:
            expected = 1 + contribution
        factor_key = "critical" if region == "crit_chance" else region
        assert math.isclose(state.multiplier_breakdown()[factor_key], expected, rel_tol=1e-12)
        checked += 1
    assert checked > 0


def test_old_technology_caps_and_later_era_dual_gates() -> None:
    old = next(item for item in GAME_DATA["upgrades"] if item["status"] == "active")
    capped = SimulationState(deterministic=True)
    capped.depth = 1e30
    capped.credits = 1e300
    capped.levels[old["key"]] = old["maxLevel"]
    capped.auto_unlocked.add(old["key"])
    assert not capped.available(old["key"])
    assert not capped.available(old["key"], automatic=True)
    assert capped.purchase(old["key"]) == (False, "locked")
    assert capped.purchase(old["key"], automatic=True) == (False, "locked")

    active = [item for item in GAME_DATA["upgrades"] if item["status"] == "active"]
    eras = GAME_DATA["eras"]
    for index, era in enumerate(eras[1:], start=1):
        previous = eras[index - 1]["key"]
        previous_keys = [item["key"] for item in active if item["era"] == previous]
        required = int(era["previousEraAutomations"])
        assert len(previous_keys) >= required

        state = SimulationState(deterministic=True)
        state.depth = float(era["unlockDepth"])
        state.auto_unlocked = set(previous_keys[:max(0, required - 1)])
        assert not state.era_unlocked(era["key"])

        state.depth = float(era["unlockDepth"]) / 2
        state.auto_unlocked = set(previous_keys[:required])
        assert not state.era_unlocked(era["key"])

        state.depth = float(era["unlockDepth"])
        assert state.era_unlocked(era["key"])


def test_critical_chance_has_immediate_benefit_without_damage_upgrade() -> None:
    state = SimulationState(deterministic=True)
    key = next(key for key, spec in SPECS.items() if spec.effect_kind == "crit_chance" and spec.status == "active")
    before = state.multiplier_breakdown()["critical"]
    state.levels[key] = 1
    assert before == 1
    assert state.multiplier_breakdown()["critical"] > before
    assert math.isclose(state.multiplier_breakdown()["critical"], 1 + SPECS[key].effect_per_level * RULES["baseCriticalDamage"])


def test_helper_purchases_cheapest_commissioning_without_reserve_or_rng() -> None:
    state = SimulationState(deterministic=True)
    state.depth = 1e7
    state.credits = 1e12
    before_rng = state.rng.getstate()
    report = state.helper_purchase()
    assert state.rng.getstate() == before_rng
    assert report["levels"] == state.total_helper_levels == len(report["items"])
    assert report["spent"] == pytest.approx(sum(item["cost"] for item in report["items"]))
    assert state.total_manual_levels == state.total_manual_commands == 0
    assert state.daily_helper_levels == report["levels"]
    assert all(state.manual_levels[key] == SPECS[key].manual_target for key in state.auto_unlocked)
    assert all(item["level"] <= SPECS[item["key"]].max_level for item in report["items"])
    assert report["items"][0]["key"] == "rotary_pick"
    assert report["items"][0]["level"] == 1


def test_helper_can_spend_reserved_budget_but_never_automatic_levels() -> None:
    state = SimulationState(deterministic=True)
    first_cost = state.cost_for("rotary_pick")
    assert state.reserve_cost() > first_cost
    state.credits = first_cost
    report = state.helper_purchase()
    assert report["items"] == [{"key": "rotary_pick", "level": 1, "cost": first_cost}]
    assert state.credits == 0
    assert state.total_helper_levels == 1
    assert state.total_auto_levels == 0
    assert state.manual_levels["rotary_pick"] == 1


def test_helper_waits_until_midnight_and_auto_runs_first() -> None:
    state = SimulationState(deterministic=True)
    manually_unlock(state, "rotary_pick")
    state._next_auto_minute = 1440
    state.credits = 1e30
    state.mine_block(1430)
    assert state.total_helper_levels == 0
    assert state.day == 1
    state.mine_block(10)
    assert state.day == 2
    assert state.last_helper_report["minute"] == 1440
    assert state.last_helper_report["levels"] > 0
    assert state.daily_helper_levels == state.last_helper_report["levels"]
    assert state.daily_manual_levels == 0
    sources = [item["source"] for item in state.last_block_events]
    assert "auto" in sources and "helper" in sources
    midnight = [item for item in state.last_block_events if item["minute"] == 1440]
    assert midnight[0]["source"] == "auto"
    assert any(item["source"] == "helper" for item in midnight)
    state.mine_block(10)
    assert state.last_block_events == []
    assert state.start_new_day() is None
    assert state.day == 2


def test_large_mine_block_matches_small_blocks_and_resets_event_buffer() -> None:
    large = SimulationState(seed=42)
    small = SimulationState(seed=42)
    large.mine_block(2880)
    observed = []
    for _ in range(2880 // 10):
        small.mine_block(10)
        observed.extend(small.last_block_events)
    assert large.last_block_events == observed
    assert large.levels == small.levels
    assert large.credits == small.credits
    assert large.depth == small.depth
    assert large.day == small.day == 3
    assert large.last_helper_report == small.last_helper_report
    assert large.total_helper_levels == small.total_helper_levels


def test_disabled_helper_does_not_backfill_missed_days() -> None:
    state = SimulationState(deterministic=True)
    state.set_helper_enabled(False)
    state.credits = 1e9
    state.mine_block(2880)
    assert state.last_helper_report == {"minute": 2880, "levels": 0, "spent": 0.0, "items": []}
    assert state.total_helper_levels == 0
    assert state._next_helper_minute == 4320
    state.set_helper_enabled(True)
    assert state.total_helper_levels == 0
    state.mine_block(10)
    assert state.last_helper_report["minute"] == 2880
    state.mine_block(1430)
    assert state.last_helper_report["minute"] == 4320
    assert state.total_helper_levels > 0
    with pytest.raises(ValueError):
        state.set_helper_enabled(1)


def test_empty_daily_helper_report_and_no_login_day_reset() -> None:
    state = SimulationState(deterministic=True)
    state.set_helper_enabled(False)
    state.credits = 1e9
    state.mine_block(1440)
    assert state.day == 2
    assert state.daily_helper_levels == state.daily_manual_levels == 0
    assert state.last_helper_report == {"minute": 1440, "levels": 0, "spent": 0.0, "items": []}
    state.set_helper_enabled(True)
    for key, spec in SPECS.items():
        state.levels[key] = spec.max_level
    state.mine_block(1440)
    assert state.day == 3
    assert state.last_helper_report == {"minute": 2880, "levels": 0, "spent": 0.0, "items": []}
    assert state.last_block_events == []


def test_d1_first_upgrade_and_daily_replay_counts() -> None:
    state, snapshots, events = run(10, 42, profile="daily", route="balanced")
    manual = [item for item in events if item.source == "manual"]
    assert manual[0].day == 1
    assert manual[0].minute == 1200
    assert all(item.visits == 1 for item in snapshots)
    assert all(item.manual_commands == item.manual_levels for item in snapshots)
    assert any(item.helper_levels > 0 for item in snapshots)
    assert sum(item.manual_levels for item in snapshots) == len(manual)
    assert sum(item.helper_levels for item in snapshots) == sum(event.source == "helper" for event in events)
    assert snapshots[0].current_era == "foundation"
    assert snapshots[-1].depth > snapshots[0].depth
    assert state.minute == 10 * 1440
    assert state.day == 11
    assert state.total_manual_levels == 34
    assert state.total_helper_levels == 17
    assert state.total_auto_levels == 79


def test_opportunity_matrix_reports_bursts_not_three_to_six_cap() -> None:
    matrix = run_opportunity_matrix()
    assert audit_opportunities(matrix) == []
    assert len(matrix) == 20
    assert all(len(counts) == 10 for counts in matrix.values())
    assert max(max(counts) for counts in matrix.values()) <= RULES["manualBurstWarningLevels"]
    assert audit_opportunities({(42, "balanced"): [31]}) == ["seed=42 route=balanced: [31]"]


def test_daily_absent_and_legacy_profiles_are_replayed() -> None:
    results = run_profile_matrix(10, 42)
    audit_profiles(results)
    assert set(results) == set(PLAYER_PROFILES)
    assert PLAYER_PROFILES["daily"].check_minutes == (1200,)
    assert PLAYER_PROFILES["absent"].check_minutes == ()
    assert all(item.manual_levels == item.manual_commands == item.visits == 0 for item in results["absent"][1])
    assert results["absent"][0].total_helper_levels > 0
    assert results["daily"][1][-1].current_era == "electrical"
    assert results["absent"][1][-1].current_era == "electrical"


def test_profile_audit_only_applies_d10_acceptance_to_exact_ten_day_runs() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        run(0)
    audit_profiles(run_profile_matrix(1, 42))
    twenty_day = run_profile_matrix(20, 42)
    for key in ("daily", "absent"):
        state, snapshots, events = twenty_day[key]
        snapshots[-1] = replace(snapshots[-1], current_era="foundation")
        twenty_day[key] = (state, snapshots, events)
    audit_profiles(twenty_day)

    ten_day = run_profile_matrix(10, 42)
    state, snapshots, events = ten_day["daily"]
    snapshots[-1] = replace(snapshots[-1], current_era="foundation")
    ten_day["daily"] = (state, snapshots, events)
    with pytest.raises(AssertionError, match="D10"):
        audit_profiles(ten_day)


def test_daily_and_absent_five_seed_four_route_helper_matrix() -> None:
    matrix = run_helper_ten_day_matrix()
    assert len(matrix) == 20
    assert {item.seed for item in matrix} == {1, 7, 42, 99, 2026}
    assert {item.route for item in matrix} == set(GAME_DATA["strategy"]["routeVariants"])
    assert all(item.daily_industrial_minute is not None for item in matrix)
    assert all(item.absent_industrial_minute is not None for item in matrix)
    assert all(item.daily_electrical_minute is not None for item in matrix)
    assert all(item.absent_electrical_minute is not None for item in matrix)
    assert all(item.daily_electrical_minute <= 10 * 1440 for item in matrix)
    assert all(item.absent_electrical_minute <= 10 * 1440 for item in matrix)
    assert all(
        item.electrical_lag_minutes
        == item.absent_electrical_minute - item.daily_electrical_minute
        for item in matrix
    )
    assert all(item.daily_max_manual_levels <= RULES["manualBurstWarningLevels"] for item in matrix)
    assert all(item.daily_max_helper_levels > 0 for item in matrix)
    assert all(item.absent_max_helper_levels > 0 for item in matrix)
    assert all(item.daily_max_total_purchases >= item.daily_max_manual_levels for item in matrix)
    assert all(item.absent_max_total_purchases >= item.absent_max_helper_levels for item in matrix)
    assert all(item.absent_depth < item.daily_depth for item in matrix)


def test_output_path_defaults_to_new_helper_trace_and_protects_historical_trace() -> None:
    assert resolve_output_path(pathlib.Path("HELPER_TEN_DAYS_TRACE.md")) == HERE / "HELPER_TEN_DAYS_TRACE.md"
    with pytest.raises(ValueError, match="拒绝覆盖历史"):
        resolve_output_path(HERE / "FIRST_TEN_DAYS_TRACE.md")


def test_replay_same_seed_is_repeatable_and_strategy_visit_drains_affordable() -> None:
    a, sa, ea = run(10, 7, profile="daily")
    b, sb, eb = run(10, 7, profile="daily")
    assert sa == sb and ea == eb and a.levels == b.levels
    fresh = SimulationState(deterministic=True)
    fresh.credits = 1e9
    orders = strategy_visit(fresh)
    assert orders
    assert fresh.total_manual_commands == len(orders)
    assert not strategy_visit(fresh)


@pytest.mark.parametrize("profile", ["daily", "absent", "active", "regular", "low"])
def test_python_and_web_engine_match(profile: str) -> None:
    state, snapshots, events = run(10, 42, profile=profile, route="balanced")
    completed = subprocess.run(
        ["node", str(RUNNER), "42", "10", profile, "balanced"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
    )
    web = json.loads(completed.stdout)
    for py, js in zip(snapshots, web["snapshots"], strict=True):
        assert py.day == js["day"]
        assert py.manual_levels == js["manualLevels"]
        assert py.auto_levels == js["autoLevels"]
        assert py.helper_levels == js["helperLevels"]
        assert py.manual_commands == js["manualCommands"]
        assert py.visits == js["visits"]
        assert py.current_era == js["currentEra"]
        assert math.isclose(py.depth, js["depth"], rel_tol=1e-12)
        assert math.isclose(py.credits, js["credits"], rel_tol=1e-12)
        assert math.isclose(py.income_multiplier, js["incomeMultiplier"], rel_tol=1e-12)
        assert math.isclose(py.depth_multiplier, js["depthMultiplier"], rel_tol=1e-12)
    py_events = [(item.day, item.minute, item.source, item.key, item.level, item.cost) for item in events]
    js_events = [(item["day"], item["minute"], item["source"], item["key"], item["level"], item["cost"]) for item in web["events"]]
    assert len(py_events) == len(js_events)
    for py, js in zip(py_events, js_events, strict=True):
        assert py[:5] == js[:5]
        assert math.isclose(py[5], js[5], rel_tol=1e-12)
    assert state.levels == web["levels"]
    assert state.manual_levels == web["manualLevels"]
    assert sorted(state.auto_unlocked) == web["autoUnlocked"]
    assert state.helper_enabled == web["helperEnabled"]
    assert state._next_helper_minute == web["nextHelperMinute"]
    assert state.total_helper_levels == web["totalHelperLevels"]
    assert state.total_manual_levels == web["totalManualLevels"]
    assert state.total_manual_commands == web["totalManualCommands"]
    assert state.total_auto_levels == web["totalAutoLevels"]
    assert state.last_helper_report == web["lastHelperReport"]


def test_web_opportunity_matrix_matches_python() -> None:
    matrix = run_opportunity_matrix()
    for (seed, route), counts in matrix.items():
        completed = subprocess.run(
            ["node", str(RUNNER), str(seed), "10", "opportunity", route],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
        )
        web = json.loads(completed.stdout)
        assert [item["manualLevels"] for item in web["snapshots"]] == counts
