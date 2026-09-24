from __future__ import annotations

import copy
import json
import math
import pathlib
import shutil
import subprocess
import time
from functools import lru_cache

import pytest

from s2_mining_simulator import (
    CORE_SPECS,
    PRESTIGE_CONFIG,
    RULES,
    SimulationState,
    strategy_visit,
)
from s2_voyage import (
    earned_cores,
    mining_work,
    sample_voyage,
    time_for_work,
)


MODULE_DIR = pathlib.Path(__file__).resolve().parent
NODE = shutil.which("node")
VECTORS = [
    (0.0, 240.0),
    (239.0, 241.0),
    (1400.0, 1500.0),
    (43200.0, 43600.0),
    (50000.0, 50000.001),
]
NODE_REFERENCE = """
import fs from "node:fs";
import { S2Engine } from "../../../../web/static/s2-vnext/engine.js";
import {
  earnedCores, miningWork, sampleVoyage, timeForWork,
} from "../../../../web/static/s2-vnext/voyage.js";

const data = JSON.parse(fs.readFileSync(
  new URL("../../../../web/static/s2-vnext/game_data.json", import.meta.url),
));
const vectors = JSON.parse(process.argv[1]);
function fixture({ resets = 3, maxed = false } = {}) {
  const e = new S2Engine(data);
  const s = e.state;
  if (maxed) {
    resets = Math.max(
      resets,
      500000,
      ...data.prestige.upgrades.map((spec) => spec.unlockResets),
    );
  }
  s.resets = s.completedPlanets = resets;
  s.minute = s.planetStartedMinute = resets * 10;
  s.nextAutoMinute = (Math.floor(s.minute / 60) + 1) * 60;
  s.nextHelperMinute = (Math.floor(s.minute / 1440) + 1) * 1440;
  s.day = Math.floor(s.minute / 1440) + 1;
  s.cores = maxed
    ? data.prestige.upgrades.reduce((total, spec) => total
      + Array.from({ length: spec.maxLevel }, (_, level) =>
        spec.baseCost * spec.costGrowth ** level)
        .reduce((sum, cost) => sum + cost, 0), 0)
    : earnedCores(resets, data.prestige.rewardStep);
  if (maxed) {
    for (const spec of data.prestige.upgrades) {
      for (let i = 0; i < spec.maxLevel; i += 1) {
        if (!e.purchaseCore(spec.key).ok) throw new Error(spec.key);
      }
    }
  }
  return e;
}
function eventSummary(event) {
  return {
    key: event.key, cost: event.cost, level: event.level,
    automatic: event.automatic, source: event.source, age: event.age,
  };
}
function planSummary(plan) {
  return {
    initialAge: plan.initialAge,
    duration: plan.duration,
    segments: plan.segments.length,
    events: plan.events.length,
    firstEvent: eventSummary(plan.events[0]),
    lastEvent: eventSummary(plan.events.at(-1)),
    end: {
      age: plan.end.age, depth: plan.end.depth, credits: plan.end.credits,
      built: plan.end.built, allMaxedAge: plan.end.allMaxedAge,
      levels: plan.end.levels, manualLevels: plan.end.manualLevels,
      autoUnlocked: [...plan.end.autoUnlocked].sort(),
      everKeys: [...plan.end.everKeys].sort(),
      eraAges: plan.end.eraAges,
    },
  };
}
function sampleSummary(sample) {
  return {
    age: sample.age, depth: sample.depth, credits: sample.credits,
    built: sample.built, levels: sample.levels,
  };
}
function stateSummary(e) {
  const s = e.state;
  return {
    target_depth: s.targetDepth,
    minute: s.minute, day: s.day, depth: s.depth, credits: s.credits,
    levels: s.levels, manual_levels: s.manualLevels,
    auto_unlocked: [...s.autoUnlocked].sort(),
    ever_keys: [...s.everKeys].sort(),
    daily_manual_levels: s.dailyManualLevels,
    max_daily_manual_levels: s.maxDailyManualLevels,
    total_manual_levels: s.totalManualLevels,
    daily_helper_levels: s.dailyHelperLevels,
    total_helper_levels: s.totalHelperLevels,
    total_manual_commands: s.totalManualCommands,
    total_auto_levels: s.totalAutoLevels,
    helper_enabled: s.helperEnabled,
    last_helper_report: s.lastHelperReport,
    era_first_days: s.eraFirstDays,
    auto_cursor: s.autoCursor,
    next_auto_minute: s.nextAutoMinute,
    next_helper_minute: s.nextHelperMinute,
    resets: s.resets, completed_planets: s.completedPlanets,
    cores: s.cores, core_levels: s.coreLevels,
    planet_complete: s.planetComplete,
    planet_started_minute: s.planetStartedMinute,
    all_maxed_minute: s.allMaxedMinute,
    auto_depart: s.autoDepart,
    core_auto_route: s.coreAutoRoute,
    planet_history: s.planetHistory.map((item) => ({
      planet: item.planet, minutes: item.minutes,
      completed_minute: item.completedMinute, reward: item.reward,
      all_maxed_minute: item.allMaxedMinute,
    })),
  };
}
function replayGalaxy(profile) {
  const e = new S2Engine(data, { seed: 42 });
  let compiled = 0; let events = 0; let coreMaxedMinute = null;
  const allCoreMaxed = () => data.prestige.upgrades.every(
    (spec) => e.state.coreLevels[spec.key] === spec.maxLevel,
  );
  for (let block = 0; block < 365 * 144 && !e.galaxyComplete(); block += 1) {
    e.mineBlock(10);
    compiled += e.lastBatchSummary.compiled;
    events += e.lastBatchSummary.events;
    if (coreMaxedMinute === null && allCoreMaxed()) {
      coreMaxedMinute = e.state.minute;
    }
    if (e.state.minute % 1440 === 1200) {
      if (profile === "daily") e.strategyVisit();
      if (e.state.coreAutoRoute === "off" && e.state.completedPlanets > 0) {
        e.setCoreAutoRoute("balanced");
      }
      if (coreMaxedMinute === null && allCoreMaxed()) {
        coreMaxedMinute = e.state.minute;
      }
      if (e.state.planetComplete && e.state.resets === 0) {
        e.departPlanet();
      }
    }
  }
  return {
    state: stateSummary(e), rng: e.rng.snapshot(), compiled, events,
    elapsedDays: e.state.planetHistory.at(-1).completedMinute / 1440,
    coreMaxedMinute,
    tailDays: (
      e.state.planetHistory.at(-1).completedMinute - coreMaxedMinute
    ) / 1440,
  };
}

const integrals = vectors.map(([start, end]) => {
  const work = miningWork(start, end, 0.36, 0.08);
  return { work, inverse: timeForWork(start, work, 0.36, 0.08) };
});
const base = fixture();
const basePlan = base.voyagePlan();
const samples = [0, basePlan.duration / 3, basePlan.duration]
  .map((age) => sampleSummary(sampleVoyage(basePlan, age)));

const partial = fixture({ resets: 100 });
const cached = partial.voyagePlan();
partial.state.cores += 100;
const balanceCacheHit = partial.voyagePlan() === cached;
partial.purchaseCore("planet_drive");
const accelerated = partial.voyagePlan();
partial.mineBlock(accelerated.duration / 3);
const beforePurchase = {
  minute: partial.state.minute, depth: partial.state.depth,
  credits: partial.state.credits, levels: partial.state.levels,
};
partial.purchaseCore("core_refining");
const rebuilt = partial.voyagePlan();

const batch = fixture({ resets: 500000, maxed: true });
const batchStart = batch.state.completedPlanets;
const batchPlan = batch.voyagePlan();
batch.mineBlock(
  batchPlan.duration * (data.prestige.galaxyTargetPlanets - batchStart) + 1,
);
const bs = batch.state;
console.log(JSON.stringify({
  integrals,
  rewards: [0, 1, 5, 6, 10, 100, 1000000]
    .map((value) => earnedCores(value, data.prestige.rewardStep)),
  base: planSummary(basePlan),
  samples,
  partial: {
    balanceCacheHit,
    cachedDuration: cached.duration,
    acceleratedDuration: accelerated.duration,
    beforePurchase,
    rebuiltInitialAge: rebuilt.initialAge,
    rebuiltDuration: rebuilt.duration,
  },
  batch: {
    start: batchStart,
    planDuration: batchPlan.duration,
    minute: bs.minute,
    planetStartedMinute: bs.planetStartedMinute,
    completedPlanets: bs.completedPlanets,
    resets: bs.resets,
    cores: bs.cores,
    planetComplete: bs.planetComplete,
    history: bs.planetHistory,
    lastBatchSummary: batch.lastBatchSummary,
    totalAutoLevels: bs.totalAutoLevels,
  },
  galaxy: {
    daily: replayGalaxy("daily"),
    absent: replayGalaxy("absent"),
  },
}));
"""


def assert_near_tree(
    actual: object,
    expected: object,
    path: str = "root",
    *,
    rel: float = 2e-10,
    abs_: float = 2e-7,
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
            rel=rel,
            abs=abs_,
        ), path
        return
    if isinstance(actual, dict) and isinstance(expected, dict):
        assert actual.keys() == expected.keys(), path
        for key in actual:
            assert_near_tree(
                actual[key],
                expected[key],
                f"{path}.{key}",
                rel=rel,
                abs_=abs_,
            )
        return
    if isinstance(actual, (list, tuple)) and isinstance(
        expected,
        (list, tuple),
    ):
        assert len(actual) == len(expected), path
        for index, (left, right) in enumerate(zip(actual, expected)):
            assert_near_tree(
                left,
                right,
                f"{path}[{index}]",
                rel=rel,
                abs_=abs_,
            )
        return
    assert actual == expected, path


@lru_cache(maxsize=1)
def js_reference() -> dict[str, object]:
    if NODE is None:
        pytest.skip("Node.js is required for voyage parity")
    completed = subprocess.run(
        [
            NODE,
            "--input-type=module",
            "--eval",
            NODE_REFERENCE,
            json.dumps(VECTORS),
        ],
        cwd=MODULE_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def voyage_fixture(
    *,
    resets: int = 3,
    maxed: bool = False,
) -> SimulationState:
    state = SimulationState(deterministic=True)
    if maxed:
        resets = max(
            resets,
            500_000,
            *(spec.unlock_resets for spec in CORE_SPECS.values()),
        )
    state.resets = state.completed_planets = resets
    state.minute = state.planet_started_minute = resets * 10
    state._next_auto_minute = (
        math.floor(state.minute / int(RULES["autoPurchaseIntervalMinutes"]))
        + 1
    ) * int(RULES["autoPurchaseIntervalMinutes"])
    state._next_helper_minute = (
        math.floor(state.minute / int(RULES["helperIntervalMinutes"]))
        + 1
    ) * int(RULES["helperIntervalMinutes"])
    state.day = math.floor(state.minute / 1440) + 1
    step = int(PRESTIGE_CONFIG["rewardStep"])
    state.cores = (
        sum(
            spec.base_cost
            * sum(
                spec.cost_growth**level
                for level in range(spec.max_level)
            )
            for spec in CORE_SPECS.values()
        )
        if maxed
        else earned_cores(resets, step)
    )
    if maxed:
        for spec in CORE_SPECS.values():
            for _ in range(spec.max_level):
                assert state.purchase_core(spec.key) == (True, "")
    return state


def event_summary(event: dict[str, object]) -> dict[str, object]:
    return {
        "key": event["key"],
        "cost": event["cost"],
        "level": event["level"],
        "automatic": event["automatic"],
        "source": event["source"],
        "age": event["age"],
    }


def plan_summary(plan: dict[str, object]) -> dict[str, object]:
    end = plan["end"]
    events = plan["events"]
    return {
        "initialAge": plan["initial_age"],
        "duration": plan["duration"],
        "segments": len(plan["segments"]),
        "events": len(events),
        "firstEvent": event_summary(events[0]),
        "lastEvent": event_summary(events[-1]),
        "end": {
            "age": end["age"],
            "depth": end["depth"],
            "credits": end["credits"],
            "built": end["built"],
            "allMaxedAge": end["all_maxed_age"],
            "levels": end["levels"],
            "manualLevels": end["manual_levels"],
            "autoUnlocked": sorted(end["auto_unlocked"]),
            "everKeys": sorted(end["ever_keys"]),
            "eraAges": end["era_ages"],
        },
    }


def sample_summary(sample: dict[str, object]) -> dict[str, object]:
    return {
        "age": sample["age"],
        "depth": sample["depth"],
        "credits": sample["credits"],
        "built": sample["built"],
        "levels": sample["levels"],
    }


def state_summary(state: SimulationState) -> dict[str, object]:
    return {
        "target_depth": state.target_depth,
        "minute": state.minute,
        "day": state.day,
        "depth": state.depth,
        "credits": state.credits,
        "levels": state.levels,
        "manual_levels": state.manual_levels,
        "auto_unlocked": sorted(state.auto_unlocked),
        "ever_keys": sorted(state.ever_keys),
        "daily_manual_levels": state.daily_manual_levels,
        "max_daily_manual_levels": state.max_daily_manual_levels,
        "total_manual_levels": state.total_manual_levels,
        "daily_helper_levels": state.daily_helper_levels,
        "total_helper_levels": state.total_helper_levels,
        "total_manual_commands": state.total_manual_commands,
        "total_auto_levels": state.total_auto_levels,
        "helper_enabled": state.helper_enabled,
        "last_helper_report": state.last_helper_report,
        "era_first_days": state.era_first_days,
        "auto_cursor": state.auto_cursor,
        "next_auto_minute": state._next_auto_minute,
        "next_helper_minute": state._next_helper_minute,
        "resets": state.resets,
        "completed_planets": state.completed_planets,
        "cores": state.cores,
        "core_levels": state.core_levels,
        "planet_complete": state.planet_complete,
        "planet_started_minute": state.planet_started_minute,
        "all_maxed_minute": state.all_maxed_minute,
        "auto_depart": state.auto_depart,
        "core_auto_route": state.core_auto_route,
        "planet_history": state.planet_history,
    }


def normalize_js_history(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "planet": item["planet"],
            "minutes": item["minutes"],
            "completed_minute": item["completedMinute"],
            "reward": item["reward"],
            "all_maxed_minute": item["allMaxedMinute"],
        }
        for item in items
    ]


def assert_rng_matches_js(
    state: SimulationState,
    js_rng: dict[str, object],
) -> None:
    version, internal, gauss_next = state.rng.getstate()
    assert version == 3
    assert js_rng["mt"] == list(internal[:-1])
    assert js_rng["index"] == internal[-1]
    if gauss_next is None:
        assert js_rng["gaussNext"] is None
    else:
        assert js_rng["gaussNext"] == pytest.approx(
            gauss_next,
            rel=1e-15,
            abs=1e-15,
        )


def replay_galaxy(
    profile: str,
) -> tuple[SimulationState, int, int, float | None]:
    state = SimulationState(seed=42)
    compiled = 0
    events = 0
    core_maxed_minute = None
    for _ in range(365 * 144):
        if state.galaxy_complete():
            break
        state.mine_block(10)
        compiled += state.last_batch_summary["compiled"]
        events += state.last_batch_summary["events"]
        if core_maxed_minute is None and all(
            state.core_levels[key] == spec.max_level
            for key, spec in CORE_SPECS.items()
        ):
            core_maxed_minute = state.minute
        if state.minute % 1440 == 1200:
            if profile == "daily":
                strategy_visit(state)
            if (
                state.core_auto_route == "off"
                and state.completed_planets > 0
            ):
                state.set_core_auto_route("balanced")
            if core_maxed_minute is None and all(
                state.core_levels[key] == spec.max_level
                for key, spec in CORE_SPECS.items()
            ):
                core_maxed_minute = state.minute
            if state.planet_complete and state.resets == 0:
                assert state.depart_planet() == (True, "")
    return state, compiled, events, core_maxed_minute


def test_integral_inverse_and_core_prefix_match_javascript() -> None:
    reference = js_reference()
    for index, (start, end) in enumerate(VECTORS):
        work = mining_work(start, end, 0.36, 0.08)
        assert work == pytest.approx(
            reference["integrals"][index]["work"],
            rel=2e-10,
            abs=2e-7,
        )
        assert time_for_work(
            start,
            work,
            0.36,
            0.08,
        ) == pytest.approx(end, rel=2e-10, abs=2e-7)

        pieces = 20_000
        width = (end - start) / pieces
        midpoint = sum(
            (
                1 + 0.36 * math.sqrt(
                    (start + (item + 0.5) * width) / 1440
                )
            )
            * (
                1
                + 0.08
                * min(
                    1,
                    ((start + (item + 0.5) * width) % 1440) / 240,
                )
            )
            * width
            for item in range(pieces)
        )
        assert work == pytest.approx(midpoint, rel=2e-7)

    planets = [0, 1, 5, 6, 10, 100, 1_000_000]
    assert [
        earned_cores(value, int(PRESTIGE_CONFIG["rewardStep"]))
        for value in planets
    ] == reference["rewards"]


def test_compiled_voyage_and_partial_samples_match_javascript() -> None:
    state = voyage_fixture()
    plan = state.voyage_plan()
    reference = js_reference()

    assert_near_tree(plan_summary(plan), reference["base"], "plan")
    samples = [
        sample_summary(sample_voyage(plan, age))
        for age in (0, plan["duration"] / 3, plan["duration"])
    ]
    assert_near_tree(samples, reference["samples"], "samples")
    assert len(plan["events"]) == sum(
        spec.max_level
        for spec in state.specs.values()
        if spec.status == "active"
    )
    assert plan["duration"] - plan["end"]["all_maxed_age"] > 4 * 1440


def test_saved_partial_new_purchase_and_balance_independent_cache() -> None:
    state = voyage_fixture(resets=100)
    cached = state.voyage_plan()
    state.cores += 100
    assert state.voyage_plan() is cached

    assert state.purchase_core("planet_drive") == (True, "")
    accelerated = state.voyage_plan()
    assert accelerated is not cached
    assert accelerated["duration"] < cached["duration"]
    state.mine_block(accelerated["duration"] / 3)

    saved = copy.deepcopy(state)
    before = {
        "minute": saved.minute,
        "depth": saved.depth,
        "credits": saved.credits,
        "levels": dict(saved.levels),
    }
    assert saved.purchase_core("core_refining") == (True, "")
    rebuilt = saved.voyage_plan()
    assert rebuilt["initial_age"] > 0
    assert {
        "minute": saved.minute,
        "depth": saved.depth,
        "credits": saved.credits,
        "levels": saved.levels,
    } == before

    reference = js_reference()["partial"]
    actual = {
        "balanceCacheHit": True,
        "cachedDuration": cached["duration"],
        "acceleratedDuration": accelerated["duration"],
        "beforePurchase": before,
        "rebuiltInitialAge": rebuilt["initial_age"],
        "rebuiltDuration": rebuilt["duration"],
    }
    assert_near_tree(actual, reference, "partial")


def test_continuous_partitioning_and_auto_core_boundaries_are_stable() -> None:
    seed = voyage_fixture(resets=100)
    assert seed.purchase_core("planet_drive") == (True, "")
    large = copy.deepcopy(seed)
    split = copy.deepcopy(seed)

    large.mine_block(100_000)
    for index in range(100):
        split.mine_block(1_000)
        if index % 7 == 0:
            split = copy.deepcopy(split)
    assert_near_tree(
        state_summary(large),
        state_summary(split),
        "partition",
    )
    assert large.rng.getstate() == split.rng.getstate()

    boundary_seed = voyage_fixture(resets=100)
    fast = copy.deepcopy(boundary_seed)
    slow = copy.deepcopy(boundary_seed)
    fast.set_core_auto_route("balanced")
    slow.set_core_auto_route("balanced")
    fast.mine_block(14_400)
    for index in range(1_440):
        slow.mine_block(10)
        if index == 37:
            slow = copy.deepcopy(slow)
    left = state_summary(fast)
    right = state_summary(slow)
    # Bound resource drift by the measured clock error, not a global tolerance.
    clock_drift = abs(fast.planet_started_minute - slow.planet_started_minute)
    assert clock_drift < 1e-8
    for key, rate in (
        (
            "credits",
            float(RULES["baseCreditsPerMinute"])
            * max(fast.income_multiplier(), slow.income_multiplier()),
        ),
        (
            "depth",
            float(RULES["baseDepthPerMinute"])
            * max(fast.depth_multiplier(), slow.depth_multiplier()),
        ),
    ):
        assert abs(left[key] - right[key]) <= 2e-7 + 2 * clock_drift * rate, key
        right[key] = left[key]
    assert_near_tree(left, right, "core_boundaries")
    assert fast.last_batch_summary["compiled"] <= 80


def test_partial_core_upgrade_sequence_matches_split_saved_cycles() -> None:
    initial = voyage_fixture(resets=100)
    initial.mine_block(20_000)
    large = copy.deepcopy(initial)
    split = copy.deepcopy(initial)

    for key in (
        "planet_drive",
        "core_depth",
        "core_refining",
        "stellar_relay",
    ):
        assert large.purchase_core(key) == (True, "")
        assert split.purchase_core(key) == (True, "")
        large.mine_block(6_000)
        for _ in range(12):
            split.mine_block(500)
            split = copy.deepcopy(split)
        assert_near_tree(
            state_summary(large),
            state_summary(split),
            f"partial_upgrade.{key}",
        )
        assert large.rng.getstate() == split.rng.getstate()


def test_every_compiled_purchase_meets_actual_preconditions() -> None:
    plan = voyage_fixture().voyage_plan()
    verifier = voyage_fixture()

    for segment in plan["segments"]:
        events = [
            event
            for event in plan["events"]
            if event["age"] == segment["age"]
        ]
        for event in events:
            remaining = [
                item
                for item in events
                if (
                    item is not event
                    and item["level"] > verifier.level(item["key"])
                )
            ]
            verifier.depth = segment["depth"]
            verifier.credits = (
                segment["credits"]
                + event["cost"]
                + sum(item["cost"] for item in remaining)
            )
            assert event["level"] == verifier.level(event["key"]) + 1
            assert event["cost"] == verifier.cost_for(event["key"])
            assert verifier.available(event["key"], automatic=True)
            assert verifier.purchase(
                event["key"],
                automatic=True,
            ) == (True, "")
        assert verifier.levels == segment["levels"]

    assert verifier.levels == plan["end"]["levels"]


@pytest.mark.parametrize("profile", ["daily", "absent"])
def test_natural_balanced_galaxy_replay_matches_javascript(
    profile: str,
) -> None:
    state, compiled, events, core_maxed_minute = replay_galaxy(profile)
    reference = js_reference()["galaxy"][profile]

    assert_near_tree(
        state_summary(state),
        reference["state"],
        f"galaxy.{profile}.state",
    )
    assert_rng_matches_js(state, reference["rng"])
    assert compiled == reference["compiled"]
    assert events == reference["events"]
    target = int(PRESTIGE_CONFIG["galaxyTargetPlanets"])
    assert state.completed_planets == reference["state"]["completed_planets"] == target
    expected_spend = sum(
        spec.base_cost
        * sum(
            spec.cost_growth**level
            for level in range(spec.max_level)
        )
        for spec in CORE_SPECS.values()
    )
    expected_cores = (
        earned_cores(target, int(PRESTIGE_CONFIG["rewardStep"]))
        - expected_spend
    )
    assert state.cores == reference["state"]["cores"]
    assert state.cores == expected_cores
    assert state.total_auto_levels == reference["state"]["total_auto_levels"]
    assert state.core_levels == reference["state"]["core_levels"]
    assert state.core_levels == {
        key: spec.max_level
        for key, spec in CORE_SPECS.items()
    }
    assert core_maxed_minute == reference["coreMaxedMinute"]
    assert core_maxed_minute is not None
    tail_days = (
        state.planet_history[-1]["completed_minute"] - core_maxed_minute
    ) / 1440
    assert tail_days == pytest.approx(reference["tailDays"], abs=1e-9)
    assert 4.9 < tail_days < 5.1


def test_configured_target_batch_matches_javascript_and_stays_bounded() -> None:
    state = voyage_fixture(resets=500_000, maxed=True)
    start = state.completed_planets
    plan = state.voyage_plan()
    target = int(PRESTIGE_CONFIG["galaxyTargetPlanets"])
    started = time.perf_counter()
    state.mine_block(plan["duration"] * (target - start) + 1)
    elapsed = time.perf_counter() - started

    expected = js_reference()["batch"]
    actual = {
        "start": start,
        "planDuration": plan["duration"],
        "minute": state.minute,
        "planetStartedMinute": state.planet_started_minute,
        "completedPlanets": state.completed_planets,
        "resets": state.resets,
        "cores": state.cores,
        "planetComplete": state.planet_complete,
        "history": state.planet_history,
        "lastBatchSummary": state.last_batch_summary,
        "totalAutoLevels": state.total_auto_levels,
    }
    expected = {
        **expected,
        "history": normalize_js_history(expected["history"]),
    }
    assert_near_tree(actual, expected, "batch")
    assert state.completed_planets == target
    assert state.resets == target - 1
    assert state.cores == (
        earned_cores(target, int(PRESTIGE_CONFIG["rewardStep"]))
        - earned_cores(start, int(PRESTIGE_CONFIG["rewardStep"]))
    )
    assert len(state.planet_history) == int(PRESTIGE_CONFIG["historyLimit"])
    assert state.last_batch_summary["planets"] == target - start
    assert state.last_batch_summary["compiled"] == 0
    assert state.last_batch_summary["events"] == 0
    assert len(state.last_block_events) <= 1024
    assert elapsed < 2.0
    assert state.depart_planet() == (False, "galaxy")


def test_opening_burst_splits_exactly_and_never_overawards_work() -> None:
    burst_key = next(
        key
        for key, spec in CORE_SPECS.items()
        if spec.effect_kind == "opening_burst"
    )
    state = SimulationState(deterministic=True)
    state.completed_planets = state.resets = CORE_SPECS[
        burst_key
    ].unlock_resets
    state.core_levels[burst_key] = 1
    plan = state.voyage_plan()
    boundary = float(PRESTIGE_CONFIG["openingBurstSeconds"]) / 60

    assert plan["segments"][0]["age"] == 0
    assert plan["segments"][0]["end_age"] == pytest.approx(boundary)
    assert plan["segments"][1]["age"] == pytest.approx(boundary)
    first = plan["segments"][0]
    second = plan["segments"][1]
    work = mining_work(
        first["age"],
        first["end_age"],
        first["teamwork"],
        first["momentum"],
    )
    assert second["credits"] == pytest.approx(
        first["credits"] + first["income"] * work
    )
    assert second["depth"] == pytest.approx(
        first["depth"] + first["depth_rate"] * work
    )
    assert second["credits"] < state.cost_for(next(iter(state.local_keys)))
    assert second["depth"] < state.target_depth

    epsilon = boundary / 1000
    before = sample_voyage(plan, boundary - epsilon)
    at = sample_voyage(plan, boundary)
    after = sample_voyage(plan, boundary + epsilon)
    assert before["credits"] < at["credits"] < after["credits"]
    assert before["depth"] < at["depth"] < after["depth"]
    assert first["income"] > second["income"]
    assert first["depth_rate"] > second["depth_rate"]


def test_short_voyage_stays_inside_opening_burst() -> None:
    burst_key = next(
        key
        for key, spec in CORE_SPECS.items()
        if spec.effect_kind == "opening_burst"
    )
    state = SimulationState(deterministic=True)
    state.completed_planets = state.resets = CORE_SPECS[
        burst_key
    ].unlock_resets
    state.core_levels[burst_key] = 1
    state.target_depth = 1

    plan = state.voyage_plan()
    boundary = float(PRESTIGE_CONFIG["openingBurstSeconds"]) / 60

    assert plan["duration"] < boundary
    assert len(plan["segments"]) == 1
    assert plan["end"]["depth"] == pytest.approx(state.target_depth)
