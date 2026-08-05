from s2_mining_simulator import LOCAL_KEYS, SPECS, LogNumber, SimulationState, run_scenario
from s2_first_ten_days import run as run_first_ten_days


def test_batch_upgrade_uses_one_message_and_daily_limit_is_three():
    state = SimulationState(target_depth=1_000_000, seed=1)
    state.resources["credits"] = 100_000

    ok, _ = state.upgrade_command([("pickaxe", 2), ("cart", 2)])
    assert ok
    assert state.daily_upgrade_messages == 1
    assert state.local_levels["pickaxe"] == 2
    assert state.local_levels["cart"] == 2

    assert state.upgrade_command([("refinery", 1)])[0]
    assert state.upgrade_command([("survey", 1)])[0]
    assert not state.upgrade_command([("pickaxe", 1)])[0]
    assert state.daily_upgrade_messages == 3


def test_level_three_unlocks_auto_and_auto_unlock_survives_prestige():
    state = SimulationState(target_depth=100, seed=2)
    state.resources["credits"] = 100_000
    assert state.upgrade_command([("pickaxe", 3)])[0]
    assert "pickaxe" in state.auto_unlocked
    state.depth = state.target_depth
    state.mine_minute(1)
    assert state.planets == LogNumber.from_int(1)
    assert state.local_levels["pickaxe"] == 0
    assert "pickaxe" in state.active_auto_keys


def test_prestige_resets_local_economy_but_keeps_core_upgrades():
    state = SimulationState(target_depth=100, seed=3)
    state.resources["credits"] = 10_000
    state.cores = LogNumber.from_int(4)
    assert state.upgrade_command([("planetary_power", 1)])[0]
    state.local_levels["pickaxe"] = 8
    state.resources["tin"] = 99
    state.prestige()
    assert state.permanent_levels["planetary_power"] == 1
    assert state.local_levels["pickaxe"] == 0
    assert state.resources["tin"] == 0
    assert state.cores == LogNumber.from_int(4)


def test_stage_two_projection_does_not_construct_huge_integer():
    state = SimulationState(target_depth=1_000_000, seed=4)
    projection = state.project_stage_two(308)
    assert projection["target_log10"] == 308
    assert projection["log10_minutes_to_target"] > 300
    assert state.planets == LogNumber.zero()


def test_seeded_scenario_reaches_first_reset_in_development_window():
    state, log = run_scenario(days=30, seed=42, target_log10=11)
    assert state.planets >= LogNumber.one()
    assert state.permanent_levels["planetary_power"] >= 1
    assert state.first_reset_day is not None
    assert 15 <= state.first_reset_day <= 45
    assert any("D25" in line for line in log)


def test_stage_one_registry_has_distinct_effectful_nodes():
    assert len(LOCAL_KEYS) >= 100
    assert len({SPECS[key].name for key in LOCAL_KEYS}) == len(LOCAL_KEYS)
    assert all(SPECS[key].effect_kind != "none" or SPECS[key].special for key in LOCAL_KEYS)


def test_relative_burst_is_applied_before_its_timer_expires():
    state = SimulationState(target_depth=1_000_000, seed=5)
    state.local_levels["relativity"] = 1
    state.burst_seconds = 60
    state.mine_minute(1)
    assert state.burst_seconds == 0
    assert state.depth > 500


def test_stage_one_matrix_keeps_reset_window_and_coverage_across_seeds():
    from s2_mining_simulator import run_stage_one_matrix

    audits = run_stage_one_matrix(seeds=(1, 42, 2026), days=45, target_log10=11)
    assert all(a.passed for a in audits)
    assert all(15 <= a.first_reset_day <= 45 for a in audits if a.first_reset_day is not None)
    assert all(a.local_nodes_reached == 124 for a in audits)
    assert all(a.special_nodes_reached == a.special_nodes_total for a in audits)
    assert all(a.max_daily_messages <= 3 for a in audits)


def test_stage_one_45_day_integration_reaches_every_local_node():
    state, log = run_scenario(days=45, seed=42, target_log10=11)
    assert len(state.ever_local_keys) == len(LOCAL_KEYS)
    assert sum(1 for key in state.ever_local_keys if SPECS[key].special) >= 12
    assert any("阶段一审查" in line for line in log)


def test_first_ten_days_uses_real_message_limit_and_records_auto_purchases():
    _, snapshots, events, checks = run_first_ten_days(days=10, seed=42)

    assert all(snapshot.manual_messages <= 3 for snapshot in snapshots)
    assert all(snapshot.checks >= 20 for snapshot in snapshots)
    assert any(not check.acted for check in checks)
    assert any(event.source == "manual" for event in events)
    assert any(event.source == "auto" for event in events)
    assert snapshots[-1].nodes_reached > snapshots[0].nodes_reached
