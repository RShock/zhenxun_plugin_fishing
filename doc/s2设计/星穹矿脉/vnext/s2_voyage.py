"""Continuous expected-value voyage integration for the S2 mining simulator."""

from __future__ import annotations

import math
from typing import Any


def mining_work(
    start: float,
    end: float,
    teamwork: float,
    momentum: float,
) -> float:
    """Integrate local-age teamwork and daily momentum over an age interval."""
    if end <= start:
        return 0.0
    current = start
    total = 0.0
    pieces = 0
    teamwork_scale = teamwork / math.sqrt(1440)
    while current < end:
        pieces += 1
        if pieces > 8192:
            raise ValueError("voyage age integration exceeded its bounded horizon")
        day = math.floor(current / 1440) * 1440
        ramp = current - day < 240
        stop = min(end, day + (240 if ramp else 1440))
        width = stop - current
        root = math.sqrt(current)
        delta = width / (math.sqrt(stop) + root)
        root_integral = (
            2 * root * root * delta
            + 2 * root * delta**2
            + 2 / 3 * delta**3
        )
        base = width + teamwork_scale * root_integral
        if ramp:
            weighted_root = (
                2 * root**3 * delta**2
                + 10 / 3 * root**2 * delta**3
                + 2 * root * delta**4
                + 2 / 5 * delta**5
            )
            total += (
                (1 + momentum * (current - day) / 240) * base
                + momentum
                / 240
                * (width * width / 2 + teamwork_scale * weighted_root)
            )
        else:
            total += (1 + momentum) * base
        current = stop
    return total


def time_for_work(
    start: float,
    work: float,
    teamwork: float,
    momentum: float,
) -> float:
    """Invert ``mining_work`` with the same bounded binary search as the JS."""
    if not work > 0 or not math.isfinite(work):
        raise ValueError("invalid voyage event distance")
    if not teamwork and not momentum:
        return start + work
    low = start
    high = start + work / (1 + teamwork * math.sqrt(start / 1440))
    if not high > start:
        raise ValueError("voyage event below clock precision")
    for _ in range(52):
        middle = low + (high - low) / 2
        if mining_work(start, middle, teamwork, momentum) < work:
            low = middle
        else:
            high = middle
    return high


def earned_cores(planets: int, step: int) -> int:
    """Return the cumulative reward prefix for completed planets."""
    quotient, remainder = divmod(planets, step)
    return (
        planets
        + step * quotient * (quotient - 1) // 2
        + quotient * remainder
    )


def _local_snapshot(state: Any, era_ages: dict[str, float]) -> dict[str, Any]:
    return {
        "age": state.minute,
        "depth": state.depth,
        "credits": state.credits,
        "levels": dict(state.levels),
        "manual_levels": dict(state.manual_levels),
        "auto_unlocked": set(state.auto_unlocked),
        "ever_keys": set(state.ever_keys),
        "era_ages": dict(era_ages),
        "all_maxed_age": state.all_maxed_minute,
        "built": sum(state.levels.values()),
    }


def compile_voyage(state: Any) -> dict[str, Any]:
    """Compile one local planet into deterministic purchase/mining events."""
    initial_age = state.minute
    era_ages: dict[str, float] = {}
    segments: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    max_events = (
        sum(state.specs[key].max_level * 2 for key in state.local_keys)
        + len(state.local_keys)
        + 10
    )
    for _ in range(max_events):
        if state.depth >= state.target_depth:
            return {
                "initial_age": initial_age,
                "segments": segments,
                "events": events,
                "end": _local_snapshot(state, era_ages),
                "duration": state.minute,
            }
        previous_eras = set(state.era_first_days)
        before_levels = dict(state.levels)
        purchases = state.auto_purchase()
        for era in state.era_first_days:
            if era not in previous_eras:
                era_ages[era] = state.minute
        for key in purchases:
            level = before_levels[key] + 1
            events.append(
                {
                    "key": key,
                    "cost": state.cost_for(key, level - 1),
                    "level": level,
                    "automatic": True,
                    "source": "auto",
                    "age": state.minute,
                }
            )
            before_levels[key] = level

        factors = state.multiplier_breakdown()
        effects = state.effect_levels()
        income = (
            float(state.rules["baseCreditsPerMinute"])
            * state.income_multiplier()
            / factors["teamwork"]
            / factors["momentum"]
        )
        depth_rate = (
            float(state.rules["baseDepthPerMinute"])
            * state.depth_multiplier()
            / factors["teamwork"]
            / factors["momentum"]
        )
        teamwork = effects.get("teamwork", 0.0)
        momentum = effects.get("momentum", 0.0)
        work = (state.target_depth - state.depth) / depth_rate
        boundary_kind = "depth"
        boundary_value = state.target_depth

        for key in state.local_keys:
            spec = state.specs[key]
            if (
                spec.status != "active"
                or state.level(key) >= spec.max_level
                or any(state.level(required) < 1 for required in spec.prerequisites)
            ):
                continue
            era = state.era_by_key[spec.era]
            era_index = state.era_sequence.index(spec.era)
            previous = state.era_sequence[era_index - 1] if era_index else None
            if (
                previous
                and state.era_automation_count(previous)
                < int(era["previousEraAutomations"])
            ):
                continue
            needed_depth = max(spec.unlock_depth, float(era["unlockDepth"]))
            is_depth = state.depth < needed_depth
            value = needed_depth if is_depth else state.cost_for(key)
            distance = (
                (value - state.depth) / depth_rate
                if is_depth
                else (value - state.credits) / income
            )
            if 0 < distance < work:
                work = distance
                boundary_kind = "depth" if is_depth else "credits"
                boundary_value = value

        next_age = time_for_work(
            state.minute,
            work,
            teamwork,
            momentum,
        )
        if not math.isfinite(next_age) or next_age <= state.minute:
            raise ValueError("non-progressing voyage event")
        segments.append(
            {
                **_local_snapshot(state, era_ages),
                "end_age": next_age,
                "income": income,
                "depth_rate": depth_rate,
                "teamwork": teamwork,
                "momentum": momentum,
            }
        )
        state.credits += income * work
        state.depth = min(state.target_depth, state.depth + depth_rate * work)
        if boundary_kind == "depth":
            state.depth = max(state.depth, boundary_value)
        else:
            state.credits = max(state.credits, boundary_value)
        state.minute = next_age
        state.day = math.floor(state.minute / 1440) + 1
    raise ValueError("voyage exceeded the finite local upgrade event budget")


def sample_voyage(plan: dict[str, Any], age: float) -> dict[str, Any]:
    """Sample a compiled voyage without replaying its purchase events."""
    if age >= plan["duration"]:
        return plan["end"]
    segments = plan["segments"]
    low = 0
    high = len(segments)
    while low + 1 < high:
        middle = (low + high) // 2
        if segments[middle]["age"] <= age:
            low = middle
        else:
            high = middle
    segment = segments[low]
    work = mining_work(
        segment["age"],
        age,
        segment["teamwork"],
        segment["momentum"],
    )
    return {
        **segment,
        "age": age,
        "credits": segment["credits"] + segment["income"] * work,
        "depth": segment["depth"] + segment["depth_rate"] * work,
    }
