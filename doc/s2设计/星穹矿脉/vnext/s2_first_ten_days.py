"""S2 原型前十天的可复现验收序列。

每个游戏小时先做一次批量升级决策，再用六个 10 分钟块推进；测试模式关闭随机扰动和每日消息限制，
专门检查网页原型的资源/科技节奏，不代替 QQ 规则的三条消息单元测试。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass


MODULE_DIR = pathlib.Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from s2_mining_simulator import (  # noqa: E402
    ERA_LABELS,
    ERA_UNLOCKS,
    SPECS,
    SimulationState,
    _development_target,
)


PRIORITY = (
    "pickaxe",
    "cart",
    "refinery",
    "survey",
    "cat",
    "industrial_blaster",
    "steam_cart",
    "electric_pickaxe",
    "electric_cart",
    "modern_drill",
    "future_quantum",
    "relativity",
)


@dataclass(frozen=True)
class DaySnapshot:
    day: int
    depth: float
    progress: float
    credits: float
    copper: float
    quartz: float
    gold: float
    coreshard: float
    eras: tuple[str, ...]
    levels: dict[str, int]
    nodes_reached: int
    purchases: int


def unlocked_eras(state: SimulationState) -> tuple[str, ...]:
    return tuple(era for era, threshold in ERA_UNLOCKS.items() if state.progress >= threshold)


def choose_upgrades(state: SimulationState) -> list[tuple[str, int]]:
    """每小时只发一条批量决策；一次最多碰 5 个节点，给玩家留下取舍。"""
    priority_index = {key: index for index, key in enumerate(PRIORITY)}
    candidates = [
        key for key in state.local_levels
        if state.level(key) < SPECS[key].max_level and state._available(key)
    ]
    candidates.sort(
        key=lambda key: (
            0 if state.level(key) == 0 else 1,
            SPECS[key].unlock,
            priority_index.get(key, 100),
            key,
        )
    )
    candidates = candidates[:5]

    # 先筛出单项买得起的节点，再尝试批量；不能因为优先级第一项暂时太贵而饿死后面的路线。
    affordable: list[tuple[str, int]] = []
    for key in candidates:
        level = state.level(key)
        # 主线设备用批量升级尽快进入自动化；时代节点先逐项探路，避免测试策略一口气铺满整棵树。
        amount = min(3 - level, 3) if key in PRIORITY and level < 3 else 1
        costs = state._batch_cost(key, amount)
        if all(state.resources.get(resource, 0.0) + 1e-9 >= cost for resource, cost in costs.items()):
            affordable.append((key, amount))
    for size in range(len(affordable), 0, -1):
        orders = affordable[:size]
        ok, _ = state.upgrade_command(orders)
        if ok:
            return orders
    return []


def run(days: int = 10, seed: int = 42) -> tuple[SimulationState, list[DaySnapshot], list[str]]:
    state = SimulationState(
        target_depth=_development_target(11),
        seed=seed,
        deterministic=True,
        enforce_daily_limit=False,
    )
    snapshots: list[DaySnapshot] = []
    decisions: list[str] = []
    previous_depth = 0.0
    previous_planets = state.planets
    for day in range(1, days + 1):
        if day > 1:
            state.start_new_day()
        day_purchases = 0
        for hour in range(24):
            orders = choose_upgrades(state)
            day_purchases += len(orders)
            if orders:
                decisions.append(
                    f"D{day:02d} {hour:02d}:00 "
                    + " ".join(f"{key}+{amount}" for key, amount in orders)
                )
            for _ in range(6):
                state.mine_block(10)
        eras = unlocked_eras(state)
        snapshots.append(
            DaySnapshot(
                day=day,
                depth=state.depth,
                progress=state.progress,
                credits=state.resources["credits"],
                copper=state.resources["copper"],
                quartz=state.resources["quartz"],
                gold=state.resources["gold"],
                coreshard=state.resources["coreshard"],
                eras=eras,
                levels={key: state.level(key) for key in PRIORITY if state.level(key)},
                nodes_reached=len(state.ever_local_keys),
                purchases=day_purchases,
            )
        )
        if state.depth <= previous_depth and state.planets == previous_planets:
            raise AssertionError(f"D{day} 深度没有前进")
        previous_depth = state.depth
        previous_planets = state.planets
    return state, snapshots, decisions


def format_snapshot(snapshot: DaySnapshot) -> str:
    era_text = ",".join(ERA_LABELS[era] for era in snapshot.eras)
    level_text = " ".join(f"{key}={level}" for key, level in snapshot.levels.items()) or "无"
    return (
        f"D{snapshot.day:02d} depth={snapshot.depth:.0f} ({snapshot.progress:.4%}) "
        f"credits={snapshot.credits:.0f} Cu={snapshot.copper:.0f} Qz={snapshot.quartz:.0f} "
        f"Au={snapshot.gold:.0f} shard={snapshot.coreshard:.0f} "
        f"eras=[{era_text}] purchases={snapshot.purchases} levels=[{level_text}]"
    )


def audit_first_ten_days(snapshots: list[DaySnapshot]) -> None:
    """前十天的体验闸门：自动化可吞掉当天决策，但深度和科技时代不能断档。"""
    if len(snapshots) < 10:
        raise AssertionError("前十天验收必须至少运行 10 天")
    if sum(snapshot.purchases for snapshot in snapshots[:10]) <= 0:
        raise AssertionError("十天内没有产生任何手动升级决策")
    if snapshots[-1].nodes_reached <= snapshots[0].nodes_reached:
        raise AssertionError("十天内没有新增科技节点")
    expected = {"industrial": 3, "electrical": 5, "modern": 7, "future": 9}
    for era, deadline in expected.items():
        if not any(era in snapshot.eras for snapshot in snapshots[:deadline]):
            raise AssertionError(f"{era} 在 D{deadline} 前没有解锁")
    if len(snapshots[-1].levels) < 10:
        raise AssertionError("D10 可观察的升级线路过少")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 S2 原型前十天固定步长验收")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    state, snapshots, decisions = run(args.days, args.seed)
    audit_first_ten_days(snapshots)
    for snapshot in snapshots:
        print(format_snapshot(snapshot))
    print("\n最近 12 条小时决策:")
    print("\n".join(decisions[-12:]) or "无")
    print(
        f"\n验收结果: days={args.days} depth={state.depth:.0f} "
        f"local_nodes={len(state.ever_local_keys)}/{len(state.local_levels)}"
    )


if __name__ == "__main__":
    main()
