# -*- coding: utf-8 -*-
"""S2 v4.2：前期逐轮精确模拟，稳定态单循环采样后批量外推。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class Ore:
    key: str
    name: str
    unlock_ratio: float
    base: float
    cost: float
    cost_growth: float
    prod_growth: float
    weight: float


ORES = (
    Ore("stone", "猫砂石", 0.00, 9.0, 8.0, 1.74, 2.04, 1.0),
    Ore("copper", "铜须矿", 0.12, 3.2, 24.0, 1.76, 2.08, 2.2),
    Ore("amethyst", "紫晶猫眼", 0.32, 1.0, 90.0, 1.78, 2.12, 5.0),
    Ore("gold", "金猫锭", 0.58, 0.28, 360.0, 1.80, 2.16, 12.0),
    Ore("rainbow", "虹核晶", 0.82, 0.06, 1800.0, 1.82, 2.20, 30.0),
)


@dataclass(frozen=True)
class Tech:
    key: str
    name: str
    cost: int
    need_resets: int


TECHS = (
    Tech("start", "整备协议", 3, 3),
    Tech("upgrade", "升级协议", 3, 6),
    Tech("layer", "地层协议", 3, 9),
    Tech("reset", "无限协议", 3, 12),
)
ALL_TECHS = frozenset(tech.key for tech in TECHS)


@dataclass(frozen=True)
class Config:
    core: float = 1e8
    pulses_per_day: int = 4
    max_cycle_days: int = 8
    second_order_exponent: int = 308
    tech_efficiency: float = 1.18
    depth_scale: float = 200_000.0
    mineral_noise: float = 0.02
    exact_cycle_limit: int = 64
    target_manual_max: int = 80

    @property
    def second_order_need(self) -> int:
        """真正天文门槛；只用于整数算术，绝不用于循环边界。"""
        return 10**self.second_order_exponent


@dataclass(frozen=True)
class CycleResult:
    days: int
    manual: int
    reward: int
    mineral_expected: tuple[float, ...]
    mineral_actual: tuple[float, ...]
    before_reset: dict


@dataclass
class State:
    day: int = 0
    resets: int = 0
    shards: int = 0
    spent_shards: int = 0
    techs: set[str] = field(default_factory=set)
    cycle_days: list[int] = field(default_factory=list)
    cycle_manual: list[int] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    stable_sample: dict | None = None
    extrapolation: dict | None = None
    exact_cycles: int = 0
    won: bool = False


def tech_enabled(state: State, key: str) -> bool:
    return key in state.techs


def buy_available_tech(state: State) -> None:
    """基准策略按固定顺序购买；科技只花一阶无限产出的星核。"""
    for tech in TECHS:
        if tech.key in state.techs or state.resets < tech.need_resets:
            continue
        if state.shards >= tech.cost:
            state.shards -= tech.cost
            state.spent_shards += tech.cost
            state.techs.add(tech.key)


def speed_multiplier(state: State, cfg: Config) -> float:
    """效率只由永久科技状态决定；状态固定后循环参数严格不再漂移。"""
    return cfg.tech_efficiency ** len(state.techs)


def controlled_factor(ore_index: int, pulse_index: int, amplitude: float) -> float:
    """可复现、零均值的受控扰动；每 4 波均值恰为 1，不做随机抽样。"""
    pattern = (-1.0, 0.5, 1.0, -0.5)
    return 1.0 + amplitude * pattern[(pulse_index + ore_index) % len(pattern)]


def run_cycle(state: State, cfg: Config) -> CycleResult:
    """精确跑一轮；矿产用期望值叠加有界、可复现扰动。"""
    levels = [0] * len(ORES)
    stocks = [0.0] * len(ORES)
    expected_totals = [0.0] * len(ORES)
    actual_totals = [0.0] * len(ORES)
    unlocked = [False] * len(ORES)
    unlocked[0] = True
    depth = 0.0
    manual = 0
    pulse_index = 0
    if tech_enabled(state, "start"):
        levels[0] = 2
        stocks[0] = 16.0
    else:
        manual += 1

    for cycle_day in range(1, cfg.max_cycle_days + 1):
        manual_upgrade_done = False
        for _ in range(cfg.pulses_per_day):
            ratio = min(1.0, depth / cfg.core)
            for index, ore in enumerate(ORES):
                if not unlocked[index] and ratio >= ore.unlock_ratio:
                    unlocked[index] = True
                    if not tech_enabled(state, "layer"):
                        manual += 1

            depth_gain = 0.0
            multiplier = speed_multiplier(state, cfg)
            for index, ore in enumerate(ORES):
                if not unlocked[index]:
                    continue
                expected = (
                    ore.base
                    * ore.prod_growth ** levels[index]
                    * multiplier
                    / cfg.pulses_per_day
                )
                actual = expected * controlled_factor(
                    index, pulse_index, cfg.mineral_noise
                )
                expected_totals[index] += expected
                actual_totals[index] += actual
                stocks[index] += actual
                depth_gain += actual * ore.weight * cfg.depth_scale
            depth += depth_gain
            pulse_index += 1

            if tech_enabled(state, "upgrade"):
                for index, ore in enumerate(ORES):
                    bought = 0
                    cost = ore.cost * ore.cost_growth ** levels[index]
                    while unlocked[index] and stocks[index] >= cost and bought < 2:
                        stocks[index] -= cost
                        levels[index] += 1
                        bought += 1
                        cost = ore.cost * ore.cost_growth ** levels[index]
            elif not manual_upgrade_done:
                bought = 0
                while bought < 3:
                    candidates = []
                    for index, ore in enumerate(ORES):
                        cost = ore.cost * ore.cost_growth ** levels[index]
                        if unlocked[index] and stocks[index] >= cost:
                            candidates.append((levels[index], index, cost))
                    if not candidates:
                        break
                    _, index, cost = min(candidates)
                    stocks[index] -= cost
                    levels[index] += 1
                    bought += 1
                if bought:
                    manual += 1
                    manual_upgrade_done = True

            if depth >= cfg.core:
                if not tech_enabled(state, "reset"):
                    manual += 1
                return CycleResult(
                    cycle_day,
                    manual,
                    1,
                    tuple(expected_totals),
                    tuple(actual_totals),
                    {
                        "levels_before_reset": levels,
                        "stock_before_reset": stocks,
                        "depth_before_reset": depth,
                    },
                )
    raise RuntimeError(f"第 {state.resets + 1} 轮在 {cfg.max_cycle_days} 日内未挖穿")


def record_exact_cycle(state: State, result: CycleResult) -> None:
    state.day += result.days
    state.resets += 1
    state.shards += result.reward
    state.exact_cycles += 1
    state.cycle_days.append(result.days)
    state.cycle_manual.append(result.manual)
    state.history.append(
        {
            "reset": state.resets,
            "total_day": state.day,
            "cycle_days": result.days,
            "manual_actions": result.manual,
            "reward": result.reward,
            "shards": state.shards,
            "techs": sorted(state.techs),
            "mineral_expected": result.mineral_expected,
            "mineral_actual": result.mineral_actual,
            "cleared": {
                "levels": True,
                "stocks": True,
                "automation": True,
                "progress": True,
            },
            **result.before_reset,
        }
    )


def extrapolate_stable_cycles(
    state: State, cfg: Config, sample: CycleResult, count: int
) -> None:
    """按 N×单循环结果直接结算；复杂度与 N 无关。"""
    if count < 0:
        raise ValueError("外推轮数不能为负")
    state.stable_sample = {
        "days": sample.days,
        "manual": sample.manual,
        "reward": sample.reward,
        "mineral_expected": sample.mineral_expected,
        "mineral_actual": sample.mineral_actual,
    }
    state.extrapolation = {
        "cycles": count,
        "days": sample.days * count,
        "manual_actions": sample.manual * count,
        "rewards": sample.reward * count,
        "mineral_expected": tuple(value * count for value in sample.mineral_expected),
        "mineral_actual": tuple(value * count for value in sample.mineral_actual),
        "formula": "total = exact_prefix + stable_cycle_sample * N",
    }
    state.day += sample.days * count
    state.resets += count
    state.shards += sample.reward * count


def run(cfg: Config = Config(), *, force_exact: bool = False) -> State:
    state = State()
    target = cfg.second_order_need
    while state.resets < target:
        if state.exact_cycles >= cfg.exact_cycle_limit:
            raise RuntimeError("精确模拟超过安全上限；禁止遍历天文数量轮次")
        buy_available_tech(state)
        result = run_cycle(state, cfg)
        stable = state.techs == ALL_TECHS
        record_exact_cycle(state, result)
        if stable and not force_exact and state.resets < target:
            extrapolate_stable_cycles(state, cfg, result, target - state.resets)
            break
    state.won = state.resets >= target
    return state


def summary(state: State, cfg: Config) -> dict:
    return {
        "won": state.won,
        "total_days": state.day,
        "first_order_resets": state.resets,
        "second_order_target": cfg.second_order_need,
        "shards_left": state.shards,
        "shards_spent": state.spent_shards,
        "techs": sorted(state.techs),
        "exact_cycles": state.exact_cycles,
        "first_three_cycle_days": state.cycle_days[:3],
        "sample_cycle_days": state.stable_sample["days"]
        if state.stable_sample
        else None,
        "first_three_manual": state.cycle_manual[:3],
        "sample_manual": state.stable_sample["manual"] if state.stable_sample else None,
        "total_manual": sum(state.cycle_manual)
        + (state.extrapolation or {}).get("manual_actions", 0),
        "extrapolated_cycles": (state.extrapolation or {}).get("cycles", 0),
        "no_stall": state.won,
        "config": asdict(cfg),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="S2 v4.2 稳定循环批量外推模拟")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    cfg = Config()
    state = run(cfg)
    data = {
        "version": "S2 v4.2",
        "summary": summary(state, cfg),
        "history": state.history,
        "stable_sample": state.stable_sample,
        "extrapolation": state.extrapolation,
    }
    if args.json:
        args.json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if not args.quiet:
        for row in state.history:
            print(
                f"∞1 #{row['reset']:02d} D+{row['cycle_days']:02d} 手动{row['manual_actions']:02d} 科技={','.join(row['techs']) or '-'}"
            )
    print(json.dumps(data["summary"], ensure_ascii=False, indent=2))
    ok = (
        state.won
        and state.exact_cycles < cfg.exact_cycle_limit
        and state.stable_sample is not None
    )
    print("ACCEPT" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
