from __future__ import annotations

import copy
import json
import math
import pathlib
import shutil
import subprocess

import pytest

from s2_mining_simulator import (
    CORE_SPECS,
    GAME_DATA,
    MAX_SAFE_INTEGER,
    RULES,
    SETTLEMENT_MINUTES,
    SPECS,
    SimulationState,
    purchase_cores_for_route,
    replay_prestige,
    validate_game_data,
)

MODULE_DIR = pathlib.Path(__file__).resolve().parent
NODE = shutil.which("node")
NODE_REPLAY = """
import { replayPrestige } from "./s2_prestige_replay.mjs";
import data from "../../../../web/static/s2-vnext/game_data.json" with { type: "json" };
const options = JSON.parse(process.argv[1]);
const { engine, milestones } = replayPrestige(data, options);
console.log(JSON.stringify({
  milestones,
  state: engine.state,
  rng: engine.rng.snapshot(),
}));
"""


def run_js_prestige(profile: str, core_route: str) -> dict[str, object]:
    if NODE is None:
        pytest.skip("Node.js is required for cross-language prestige parity")
    options = {
        "seed": 42,
        "profile": profile,
        "planets": 12,
        "days": 300,
        "coreRoute": core_route,
    }
    completed = subprocess.run(
        [
            NODE,
            "--input-type=module",
            "--eval",
            NODE_REPLAY,
            json.dumps(options),
        ],
        cwd=MODULE_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def normalize_js_history(item: dict[str, object]) -> dict[str, object]:
    return {
        "planet": item["planet"],
        "minutes": item["minutes"],
        "completed_minute": item["completedMinute"],
        "reward": item["reward"],
        "all_maxed_minute": item["allMaxedMinute"],
    }


def normalize_js_milestone(item: dict[str, object]) -> dict[str, object]:
    return {
        **normalize_js_history(item),
        "resets": item["resets"],
        "cores": item["cores"],
        "core_levels": item["coreLevels"],
        "total_manual_levels": item["totalManualLevels"],
        "total_manual_commands": item["totalManualCommands"],
    }


def assert_state_matches_js(
    state: SimulationState,
    js_state: dict[str, object],
    js_rng: dict[str, object],
) -> None:
    integer_fields = {
        "day": state.day,
        "minute": state.minute,
        "dailyManualLevels": state.daily_manual_levels,
        "maxDailyManualLevels": state.max_daily_manual_levels,
        "totalManualLevels": state.total_manual_levels,
        "totalAutoLevels": state.total_auto_levels,
        "autoCursor": state.auto_cursor,
        "nextAutoMinute": state._next_auto_minute,
        "nextHelperMinute": state._next_helper_minute,
        "totalHelperLevels": state.total_helper_levels,
        "dailyHelperLevels": state.daily_helper_levels,
        "totalManualCommands": state.total_manual_commands,
        "resets": state.resets,
        "completedPlanets": state.completed_planets,
        "cores": state.cores,
        "planetStartedMinute": state.planet_started_minute,
    }
    for key, value in integer_fields.items():
        assert js_state[key] == value, key

    assert js_state["depth"] == pytest.approx(state.depth, rel=1e-12, abs=1e-6)
    assert js_state["credits"] == pytest.approx(
        state.credits, rel=1e-12, abs=1e-6
    )
    assert js_state["targetDepth"] == pytest.approx(state.target_depth)
    assert js_state["levels"] == state.levels
    assert js_state["manualLevels"] == state.manual_levels
    assert sorted(js_state["autoUnlocked"]) == sorted(state.auto_unlocked)
    assert sorted(js_state["everKeys"]) == sorted(state.ever_keys)
    assert js_state["eraFirstDays"] == state.era_first_days
    assert js_state["helperEnabled"] is state.helper_enabled
    assert js_state["lastHelperReport"] == state.last_helper_report
    assert js_state["coreLevels"] == state.core_levels
    assert js_state["planetComplete"] is state.planet_complete
    assert js_state["allMaxedMinute"] == state.all_maxed_minute
    assert js_state["autoDepart"] is state.auto_depart
    assert [
        normalize_js_history(item) for item in js_state["planetHistory"]
    ] == state.planet_history

    version, internal, gauss_next = state.rng.getstate()
    assert version == 3
    assert js_rng["mt"] == list(internal[:-1])
    assert js_rng["index"] == internal[-1]
    if gauss_next is None:
        assert js_rng["gaussNext"] is None
    else:
        assert js_rng["gaussNext"] == pytest.approx(
            gauss_next, rel=1e-15, abs=1e-15
        )


def test_resource_contract_accepts_legacy_and_prestige_data() -> None:
    assert validate_game_data(copy.deepcopy(GAME_DATA))["prestige"]

    legacy = copy.deepcopy(GAME_DATA)
    legacy["contentVersion"] = "thirty-day-eras-1"
    legacy.pop("prestige")
    legacy["resources"] = legacy["resources"][:1]
    assert [item["key"] for item in validate_game_data(legacy)["resources"]] == [
        "credits"
    ]

    broken = copy.deepcopy(GAME_DATA)
    broken["resources"] = broken["resources"][:1]
    with pytest.raises(ValueError, match="resources"):
        validate_game_data(broken)


def test_planet_completion_clips_production_and_pauses_without_rng() -> None:
    state = SimulationState(seed=42)
    state.target_depth = 100

    state.mine_block()

    assert state.depth == state.target_depth
    assert state.credits == pytest.approx(
        100
        * float(RULES["baseCreditsPerMinute"])
        / float(RULES["baseDepthPerMinute"])
    )
    assert state.planet_complete
    assert state.completed_planets == state.cores == 1
    assert state.planet_history == [{
        "planet": 1,
        "minutes": 10,
        "completed_minute": 10,
        "reward": 1,
        "all_maxed_minute": None,
    }]

    paused_rng = state.rng.getstate()
    paused_credits = state.credits
    state.mine_block(20)
    assert state.rng.getstate() == paused_rng
    assert state.credits == paused_credits
    assert state.completed_planets == state.cores == 1
    assert len(state.planet_history) == 1


def test_first_departure_is_manual_and_later_departure_is_automatic() -> None:
    state = SimulationState(deterministic=True)
    state.depth = state.target_depth - 1
    state.mine_block()
    assert state.planet_complete
    assert state.resets == 0

    state.total_manual_levels = 7
    state.helper_enabled = False
    next_auto = state._next_auto_minute
    next_helper = state._next_helper_minute
    assert state.depart_planet() == (True, "")
    assert state.resets == 1
    assert not state.planet_complete
    assert state.depth == state.credits == 0
    assert state.total_manual_levels == 7
    assert not state.helper_enabled
    assert state._next_auto_minute == next_auto
    assert state._next_helper_minute == next_helper

    state.depth = state.target_depth - 1
    state.mine_block()
    assert state.completed_planets == 2
    assert state.resets == 2
    assert not state.planet_complete
    assert state.planet_started_minute == state.minute


def test_post_reset_zero_target_automation_is_paid_and_prerequisite_aware() -> None:
    state = SimulationState(deterministic=True)
    state.resets = 3
    state.completed_planets = 3
    state.credits = 1e12

    assert state.manual_target("rotary_pick") == 0
    assert not state.available("rotary_pick")
    assert state.available("rotary_pick", automatic=True)

    bought = state.auto_purchase()
    expected_budget = math.ceil(
        state.prestige_speed() * int(RULES["autoPurchaseBudget"])
    )
    assert len(bought) == expected_budget == 8
    assert state.level("rotary_pick") == 8
    assert "rotary_pick" in state.auto_unlocked
    assert state.total_auto_levels == 8
    assert state.level("split_tunnel") == 0


def test_core_effect_mapping_and_local_age_match_web_engine() -> None:
    state = SimulationState(deterministic=True)
    state.core_levels["core_drill"] = 1
    state.core_levels["core_refining"] = 1
    state.core_levels["core_depth"] = 1
    state.core_levels["stellar_forge"] = 1
    state.core_levels["stellar_relay"] = 1
    state.core_levels["galactic_drive"] = 1
    state.resets = 10
    state.levels["rotary_pick"] = 1
    state.levels["ore_ledger"] = 1
    state.levels["deep_marker"] = 1
    state.levels["impact_hammer"] = 1
    state.levels["union_rhythm"] = 1
    state.auto_unlocked = {"rotary_pick", "ore_ledger"}
    state.minute = 20 * 1440
    state.planet_started_minute = state.minute

    factors = state.multiplier_breakdown()
    assert factors["speed"] == pytest.approx(1 + 0.18 * 1.18)
    assert factors["income"] == pytest.approx(1 + 0.25 * 1.2 * 1.5)
    assert factors["extra_depth"] == pytest.approx(1 + 0.26 * 1.2 * 1.5)
    assert factors["critical"] == pytest.approx(1 + 0.04 * RULES["baseCriticalDamage"])
    assert factors["teamwork"] == 1
    assert factors["stellar_relay"] == pytest.approx(1.03)
    assert factors["prestige"] == pytest.approx(2**11)

    state.minute += 1440
    assert state.multiplier_breakdown()["teamwork"] == pytest.approx(
        1 + 0.045 * 1.2
    )


def test_core_purchase_cost_unlock_and_reward_step() -> None:
    state = SimulationState(deterministic=True)
    key = "core_drill"
    assert key in CORE_SPECS
    assert state.purchase_core(key) == (False, "locked")

    state.completed_planets = 1
    state.cores = 1
    assert state.core_cost(key) == 1
    assert state.purchase_core(key) == (True, "")
    assert state.core_levels[key] == 1
    assert state.cores == 0
    assert state.core_cost(key) == 2
    assert state.purchase_core(key) == (False, "cores")

    reward_state = SimulationState(deterministic=True)
    reward_state.resets = 5
    reward_state.completed_planets = 5
    reward_state.minute = 10
    reward_state.depth = reward_state.target_depth
    assert reward_state.finish_planet()
    assert reward_state.cores == 2
    assert reward_state.planet_history[-1]["reward"] == 2


def test_mine_block_uses_javascript_safe_integer_contract() -> None:
    state = SimulationState(deterministic=True)
    for invalid in (True, 10.0, MAX_SAFE_INTEGER + 1):
        with pytest.raises(ValueError, match="settlement-sized"):
            state.mine_block(invalid)

    state.minute = MAX_SAFE_INTEGER - SETTLEMENT_MINUTES + 1
    with pytest.raises(ValueError, match="settlement-sized"):
        state.mine_block()

    state.minute = 0.5
    with pytest.raises(ValueError, match="settlement-sized"):
        state.mine_block()


def test_legacy_maxed_state_keeps_unknown_all_maxed_minute() -> None:
    state = SimulationState(deterministic=True)
    state.levels = {
        key: spec.max_level if spec.status == "active" else 0
        for key, spec in SPECS.items()
    }
    state.all_maxed_minute = None

    assert state.all_local_maxed()
    state.mine_block()
    assert state.all_maxed_minute is None


def test_speed_core_route_never_falls_back() -> None:
    state = SimulationState(deterministic=True)
    state.completed_planets = 12
    state.cores = 1000
    state.core_levels["core_drill"] = CORE_SPECS["core_drill"].max_level
    state.core_levels["galactic_drive"] = CORE_SPECS[
        "galactic_drive"
    ].max_level

    assert purchase_cores_for_route(state, "speed") == []
    assert all(
        level == 0
        for key, level in state.core_levels.items()
        if key not in {"core_drill", "galactic_drive"}
    )


@pytest.mark.parametrize(
    ("profile", "core_route"),
    [("daily", "balanced"), ("absent", "none")],
)
def test_twelve_planet_javascript_python_parity(
    profile: str,
    core_route: str,
) -> None:
    js = run_js_prestige(profile, core_route)
    state, milestones = replay_prestige(
        seed=42,
        profile=profile,
        planets=12,
        days=300,
        core_route=core_route,
    )

    assert len(milestones) == 12
    assert [
        normalize_js_milestone(item) for item in js["milestones"]
    ] == milestones
    assert_state_matches_js(state, js["state"], js["rng"])
