from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess

import pytest

from s2_mining_simulator import (
    CORE_SPECS,
    GAME_DATA,
    MAX_SAFE_INTEGER,
    PRESTIGE_CONFIG,
    RULES,
    SETTLEMENT_MINUTES,
    SPECS,
    SimulationState,
    purchase_cores_for_route,
    replay_prestige,
    validate_game_data,
)
from s2_voyage import earned_cores

MODULE_DIR = pathlib.Path(__file__).resolve().parent
NODE = shutil.which("node")
NODE_REPLAY = """
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";
import data from "../../../../web/static/s2-vnext/game_data.json" with { type: "json" };
const options = JSON.parse(process.argv[1]);
const engine = new S2Engine(data, { seed: options.seed });
const milestones = [];
let recorded = 0;
for (let i = 0; i < options.days * 144; i += 1) {
  if (engine.state.completedPlanets >= options.planets) break;
  engine.mineBlock();
  if (engine.state.completedPlanets > recorded) {
    const history = engine.state.planetHistory.at(-1);
    milestones.push({
      ...history,
      resets: engine.state.resets,
      cores: engine.state.cores,
      coreLevels: { ...engine.state.coreLevels },
      totalManualLevels: engine.state.totalManualLevels,
      totalManualCommands: engine.state.totalManualCommands,
    });
    recorded = engine.state.completedPlanets;
  }
  if (engine.state.minute % 1440 === 1200) {
    if (options.profile === "daily") engine.strategyVisit();
    if (options.coreRoute !== "none"
      && engine.state.coreAutoRoute === "off"
      && engine.state.completedPlanets > 0) {
      engine.setCoreAutoRoute(options.coreRoute);
    }
    if (engine.state.planetComplete && engine.state.resets === 0) {
      engine.departPlanet();
    }
  }
}
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
        "days": 600 if profile == "absent" else 300,
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


def assert_near_tree(
    actual: object,
    expected: object,
    path: str = "root",
) -> None:
    if (
        type(actual) is int
        and type(expected) is int
    ):
        assert actual == expected, path
        return
    if (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and isinstance(expected, (int, float))
        and not isinstance(expected, bool)
    ):
        assert actual == pytest.approx(
            expected,
            rel=2e-10,
            abs=2e-7,
        ), path
        return
    if isinstance(actual, dict) and isinstance(expected, dict):
        assert actual.keys() == expected.keys(), path
        for key in actual:
            assert_near_tree(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(actual, list) and isinstance(expected, list):
        assert len(actual) == len(expected), path
        for index, (left, right) in enumerate(zip(actual, expected)):
            assert_near_tree(left, right, f"{path}[{index}]")
        return
    assert actual == expected, path


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
    assert js_state["coreAutoRoute"] == state.core_auto_route
    assert_near_tree(
        [
            normalize_js_history(item)
            for item in js_state["planetHistory"]
        ],
        state.planet_history,
        "planet_history",
    )

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
    state.credits = sum(
        state.cost_for("rotary_pick", level)
        for level in range(8)
    )

    assert state.manual_target("rotary_pick") == 0
    assert not state.available("rotary_pick")
    assert state.available("rotary_pick", automatic=True)

    bought = state.auto_purchase()
    assert len(bought) == 8
    assert state.level("rotary_pick") == 8
    assert "rotary_pick" in state.auto_unlocked
    assert state.total_auto_levels == 8
    assert state.level("split_tunnel") == 0
    assert state.credits == pytest.approx(0)


def test_resets_grant_no_free_speed_and_planet_drive_is_paid_x2_x3() -> None:
    state = SimulationState(deterministic=True)
    state.resets = state.completed_planets = 1000
    assert state.prestige_speed() == 1

    state.cores = 1
    assert state.purchase_core("planet_drive") == (True, "")
    assert state.prestige_speed() == 2
    assert state.core_cost("planet_drive") == 3
    assert state.purchase_core("planet_drive") == (False, "cores")

    state.cores = 3
    assert state.purchase_core("planet_drive") == (True, "")
    assert state.prestige_speed() == 3
    state.resets = 1_000_000
    assert state.prestige_speed() == 3


def core_key(effect_kind: str) -> str:
    return next(
        key
        for key, spec in CORE_SPECS.items()
        if spec.effect_kind == effect_kind
    )


def configured_core_spend(levels: dict[str, int]) -> int:
    return sum(
        spec.base_cost * sum(
            spec.cost_growth**level
            for level in range(levels[key])
        )
        for key, spec in CORE_SPECS.items()
    )


def test_core_effect_mapping_and_local_age_match_web_engine() -> None:
    state = SimulationState(deterministic=True)
    for kind in (
        "speed_strength",
        "income_strength",
        "depth_strength",
        "equipment_strength",
        "line_synergy",
        "global_linear",
        "global_speed",
    ):
        state.core_levels[core_key(kind)] = 1
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
    speed_strength = 1 + state.core_effect("speed_strength")
    equipment = 1 + state.core_effect("equipment_strength")
    income_strength = 1 + state.core_effect("income_strength")
    depth_strength = 1 + state.core_effect("depth_strength")
    assert factors["speed"] == pytest.approx(
        1 + SPECS["rotary_pick"].effect_per_level * speed_strength
    )
    assert factors["income"] == pytest.approx(
        1
        + SPECS["ore_ledger"].effect_per_level
        * equipment
        * income_strength
    )
    assert factors["extra_depth"] == pytest.approx(
        1
        + SPECS["deep_marker"].effect_per_level
        * equipment
        * depth_strength
    )
    assert factors["critical"] == pytest.approx(1 + 0.04 * RULES["baseCriticalDamage"])
    assert factors["teamwork"] == 1
    assert factors["stellar_relay"] == pytest.approx(
        1 + state.core_effect("line_synergy") * len(state.auto_unlocked)
    )
    assert factors["prestige"] == pytest.approx(
        (1 + state.core_effect("global_linear"))
        * 2 ** state.core_effect("global_speed")
    )

    state.minute += 1440
    assert state.multiplier_breakdown()["teamwork"] == pytest.approx(
        1
        + SPECS["union_rhythm"].effect_per_level
        * equipment
    )


def test_core_purchase_cost_unlock_and_rewards_are_exact_integers() -> None:
    state = SimulationState(deterministic=True)
    key = next(iter(CORE_SPECS))
    spec = CORE_SPECS[key]
    assert state.purchase_core(key) == (False, "locked")

    state.completed_planets = spec.unlock_resets
    state.cores = spec.base_cost
    assert state.core_cost(key) == spec.base_cost
    assert state.purchase_core(key) == (True, "")
    assert state.core_levels[key] == 1
    assert state.cores == 0
    assert state.core_cost(key) == spec.base_cost * spec.cost_growth
    assert state.purchase_core(key) == (False, "cores")

    planets = max(spec.unlock_resets, 500_000)
    funded = SimulationState(deterministic=True)
    funded.completed_planets = funded.resets = planets
    funded.cores = earned_cores(
        planets,
        int(PRESTIGE_CONFIG["rewardStep"]),
    )
    before = funded.cores
    funded.set_core_auto_route("balanced")
    assert type(funded.cores) is int
    assert funded.cores == before - configured_core_spend(funded.core_levels)

    reward_state = SimulationState(deterministic=True)
    step = int(PRESTIGE_CONFIG["rewardStep"])
    for reset in range(step * 2 + 1):
        reward_state.resets = reward_state.completed_planets = reset
        reward_state.minute = reset + 1
        reward_state.planet_started_minute = reset
        reward_state.depth = reward_state.target_depth
        before = reward_state.cores
        assert reward_state.finish_planet()
        expected = 1 + reset // step
        assert reward_state.cores - before == expected
        assert reward_state.planet_history[-1]["reward"] == expected
        reward_state.planet_complete = False


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


@pytest.mark.parametrize(
    "route",
    ["off", "balanced", "speed", "rebuild", "burst"],
)
def test_core_route_state_accepts_all_routes_and_uses_scored_target(
    route: str,
) -> None:
    state = SimulationState(deterministic=True)
    state.completed_planets = max(
        spec.unlock_resets for spec in CORE_SPECS.values()
    )
    if route == "off":
        state.cores = MAX_SAFE_INTEGER
        assert state.set_core_auto_route(route) == []
        assert not any(state.core_levels.values())
        return

    state.cores = 0
    assert state.set_core_auto_route(route) == []
    target = min(
        (
            spec
            for spec in CORE_SPECS.values()
            if state.core_available(spec.key)
        ),
        key=state.core_route_score,
    )
    state.cores = state.core_cost(target.key) - 1
    assert state.auto_purchase_core() == []
    assert not any(state.core_levels.values())

    state.cores += 1
    bought = state.auto_purchase_core()
    assert bought[0] == target.key


def test_route_helper_buys_nonpreferred_technology_after_priorities_max() -> None:
    state = SimulationState(deterministic=True)
    state.completed_planets = max(
        spec.unlock_resets for spec in CORE_SPECS.values()
    )
    preferred = {"global_linear", "global_speed", "speed_strength"}
    for key, spec in CORE_SPECS.items():
        if spec.effect_kind in preferred:
            state.core_levels[key] = spec.max_level
    state.cores = MAX_SAFE_INTEGER

    bought = purchase_cores_for_route(state, "speed")

    assert bought
    assert all(
        state.core_levels[key] == spec.max_level
        for key, spec in CORE_SPECS.items()
    )


def test_route_preferences_start_only_after_common_ten_planet_bootstrap() -> None:
    states = {
        route: SimulationState(deterministic=True)
        for route in ("speed", "rebuild", "burst")
    }
    for state in states.values():
        state.completed_planets = 9
        state.cores = MAX_SAFE_INTEGER
        state.set_core_auto_route("off")
    baseline = {
        spec.key: states["speed"].core_cost(spec.key)
        for spec in CORE_SPECS.values()
    }
    for route, state in states.items():
        state.core_auto_route = route
        assert {
            spec.key: state.core_route_score(spec)
            for spec in CORE_SPECS.values()
        } == baseline

    for route, state in states.items():
        state.completed_planets = 10
        preferred = {
            "speed": {"global_linear", "global_speed", "speed_strength"},
            "rebuild": {
                "income_strength", "local_discount", "equipment_strength",
            },
            "burst": {
                "opening_burst", "global_speed", "completion_depth",
            },
        }[route]
        assert all(
            state.core_route_score(spec)
            == state.core_cost(spec.key)
            / (4 if spec.effect_kind in preferred else 1)
            for spec in CORE_SPECS.values()
        )


def test_discount_completion_and_opening_burst_scopes() -> None:
    discount = SimulationState(deterministic=True)
    discount_key = core_key("local_discount")
    discount.core_levels[discount_key] = 1
    local_key = next(iter(SPECS))
    local_spec = SPECS[local_key]
    expected_discount = 1 + discount.core_effect("local_discount")
    assert discount.cost_for(local_key) == pytest.approx(
        local_spec.base_cost / expected_discount
    )
    core_candidate = next(iter(CORE_SPECS))
    assert discount.core_cost(core_candidate) == (
        CORE_SPECS[core_candidate].base_cost
        * CORE_SPECS[core_candidate].cost_growth
        ** discount.core_levels[core_candidate]
    )

    completion = SimulationState(deterministic=True)
    completion_key = core_key("completion_depth")
    completion.core_levels[completion_key] = 1
    before_depth = completion.depth_multiplier()
    for key, spec in SPECS.items():
        if spec.status == "active":
            completion.levels[key] = spec.max_level
    maxed_income = completion.income_multiplier()
    completion.core_levels[completion_key] = 0
    assert completion.income_multiplier() == pytest.approx(maxed_income)
    completion.core_levels[completion_key] = 1
    without_completion = completion.depth_multiplier() / (
        1 + completion.core_effect("completion_depth")
    )
    assert before_depth == 1
    assert completion.multiplier_breakdown()["completion_depth"] == pytest.approx(
        1 + completion.core_effect("completion_depth")
    )
    assert completion.depth_multiplier() == pytest.approx(
        without_completion
        * (1 + completion.core_effect("completion_depth"))
    )
    completion.levels[next(
        key for key, spec in SPECS.items() if spec.status == "active"
    )] -= 1
    assert completion.multiplier_breakdown()["completion_depth"] == 1

    burst = SimulationState(deterministic=True)
    burst.core_levels[core_key("opening_burst")] = 1
    factor = 1 + burst.core_effect("opening_burst")
    base_income = float(RULES["baseCreditsPerMinute"])
    base_depth = float(RULES["baseDepthPerMinute"])
    assert burst.income_multiplier() == pytest.approx(factor)
    assert burst.depth_multiplier() == pytest.approx(factor)
    burst.minute = float(PRESTIGE_CONFIG["openingBurstSeconds"]) / 60
    assert burst.income_multiplier() == pytest.approx(1)
    assert burst.depth_multiplier() == pytest.approx(1)
    burst.cores = MAX_SAFE_INTEGER
    burst.completed_planets = max(
        spec.unlock_resets for spec in CORE_SPECS.values()
    )
    assert burst.purchase_core(core_key("opening_burst")) == (True, "")
    assert burst.income_multiplier() == pytest.approx(1)
    assert base_income * factor > base_income
    assert base_depth * factor > base_depth


def test_prestige_three_validates_configured_target_and_safe_rewards() -> None:
    assert GAME_DATA["contentVersion"] == "prestige-3"
    assert PRESTIGE_CONFIG["galaxyTargetPlanets"] > 0
    assert PRESTIGE_CONFIG["openingBurstSeconds"] == 1
    assert PRESTIGE_CONFIG["legacyCorePrices"]

    unsafe_target = int(PRESTIGE_CONFIG["galaxyTargetPlanets"])
    step = int(PRESTIGE_CONFIG["rewardStep"])
    while earned_cores(unsafe_target, step) <= MAX_SAFE_INTEGER:
        unsafe_target *= 2

    for target in (0, unsafe_target):
        broken = copy.deepcopy(GAME_DATA)
        broken["prestige"]["galaxyTargetPlanets"] = target
        with pytest.raises(ValueError, match="prestige"):
            validate_game_data(broken)


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
        days=600 if profile == "absent" else 300,
        core_route=core_route,
    )

    assert len(milestones) == 12
    assert_near_tree(
        [
            normalize_js_milestone(item)
            for item in js["milestones"]
        ],
        milestones,
        "milestones",
    )
    assert_state_matches_js(state, js["state"], js["rng"])
