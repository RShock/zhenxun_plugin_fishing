"""S2 原型前十天的可复现操作时间线。

每天在 00:00、08:00、16:00 各提供一次批量升级窗口，严格执行每日最多三条升级消息。
挖矿仍按 10 分钟固定步长推进，达到 3 级的科技由后台自动采购，并记录每个采购时点。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Literal


MODULE_DIR = pathlib.Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from s2_mining_simulator import (  # noqa: E402
    ERA_LABELS,
    ERA_UNLOCKS,
    LOCAL_KEYS,
    SPECS,
    SimulationState,
    _development_target,
    _strategy,
)


DECISION_WINDOWS = (0, 8 * 60, 16 * 60)


@dataclass(frozen=True)
class UpgradeEvent:
    day: int
    minute: int
    source: Literal["manual", "auto"]
    orders: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class DaySnapshot:
    day: int
    depth: float
    progress: float
    resources: dict[str, float]
    eras: tuple[str, ...]
    nodes_reached: int
    auto_nodes: int
    manual_messages: int
    manual_levels: int
    auto_levels: int
    planets: str


def unlocked_eras(state: SimulationState) -> tuple[str, ...]:
    return tuple(era for era, threshold in ERA_UNLOCKS.items() if state.progress >= threshold)


def level_diff(before: dict[str, int], state: SimulationState) -> tuple[tuple[str, int], ...]:
    return tuple(
        (key, state.local_levels[key] - before[key])
        for key in LOCAL_KEYS
        if state.local_levels[key] > before[key]
    )


def run(
    days: int = 10,
    seed: int = 42,
) -> tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent]]:
    """运行真实消息限制下的三个每日决策窗口。

    随机数使用固定种子，所以结果可重复；不启用 deterministic 期望值模式，因为特殊科技
    在期望值模式下会按小时强制触发，不代表玩家实际经历的一条随机路径。
    """
    state = SimulationState(
        target_depth=_development_target(11),
        seed=seed,
        deterministic=False,
        enforce_daily_limit=True,
    )
    snapshots: list[DaySnapshot] = []
    events: list[UpgradeEvent] = []
    previous_depth = 0.0
    previous_planets = state.planets

    for current_day in range(1, days + 1):
        if current_day > 1:
            state.start_new_day()
        day_events_start = len(events)

        for window_start in DECISION_WINDOWS:
            before = dict(state.local_levels)
            _strategy(state, message_budget=1, mode="balanced")
            manual_orders = level_diff(before, state)
            if manual_orders:
                events.append(UpgradeEvent(current_day, window_start, "manual", manual_orders))

            for block in range(1, 49):
                before = dict(state.local_levels)
                state.mine_block(10)
                auto_orders = level_diff(before, state)
                if auto_orders:
                    # 24:00 保留为当日结算边界，不伪装成下一天尚未执行的 00:00 手动窗口。
                    minute = window_start + block * 10
                    events.append(UpgradeEvent(current_day, minute, "auto", auto_orders))

        day_events = events[day_events_start:]
        manual_levels = sum(
            amount for event in day_events if event.source == "manual" for _, amount in event.orders
        )
        auto_levels = sum(
            amount for event in day_events if event.source == "auto" for _, amount in event.orders
        )
        snapshots.append(
            DaySnapshot(
                day=current_day,
                depth=state.depth,
                progress=state.progress,
                resources=dict(state.resources),
                eras=unlocked_eras(state),
                nodes_reached=len(state.ever_local_keys),
                auto_nodes=len(state.auto_unlocked),
                manual_messages=state.daily_upgrade_messages,
                manual_levels=manual_levels,
                auto_levels=auto_levels,
                planets=str(state.planets),
            )
        )
        if state.depth <= previous_depth and state.planets == previous_planets:
            raise AssertionError(f"D{current_day} 深度没有前进")
        previous_depth = state.depth
        previous_planets = state.planets

    return state, snapshots, events


def audit_first_ten_days(snapshots: list[DaySnapshot], events: list[UpgradeEvent]) -> None:
    """前十天闸门只约束交互规则和时代不断档，不把具体数值当最终平衡。"""
    if len(snapshots) < 10:
        raise AssertionError("前十天验收必须至少运行 10 天")
    if any(snapshot.manual_messages > 3 for snapshot in snapshots[:10]):
        raise AssertionError("出现超过每日 3 条的手动升级消息")
    if not any(event.source == "manual" for event in events):
        raise AssertionError("十天内没有产生手动升级")
    if not any(event.source == "auto" for event in events):
        raise AssertionError("十天内没有产生自动升级")
    if snapshots[-1].nodes_reached <= snapshots[0].nodes_reached:
        raise AssertionError("十天内没有新增科技节点")
    expected = {"industrial": 3, "electrical": 5, "modern": 7, "future": 9}
    for era, deadline in expected.items():
        if not any(era in snapshot.eras for snapshot in snapshots[:deadline]):
            raise AssertionError(f"{era} 在 D{deadline} 前没有解锁")


def format_clock(minute: int) -> str:
    if minute == 1440:
        return "24:00"
    return f"{minute // 60:02d}:{minute % 60:02d}"


def format_orders(orders: tuple[tuple[str, int], ...]) -> str:
    return "、".join(f"{SPECS[key].name}+{amount}" for key, amount in orders)


def format_snapshot(snapshot: DaySnapshot) -> str:
    era_text = "、".join(ERA_LABELS[era] for era in snapshot.eras)
    resources = snapshot.resources
    return (
        f"D{snapshot.day:02d} 进度={snapshot.progress:.4%} 星球={snapshot.planets} "
        f"消息={snapshot.manual_messages}/3 手动+{snapshot.manual_levels}级 自动+{snapshot.auto_levels}级 "
        f"节点={snapshot.nodes_reached}/{len(LOCAL_KEYS)} 自动线={snapshot.auto_nodes} "
        f"矿币={resources['credits']:.0f} Sn={resources['tin']:.0f} Cu={resources['copper']:.0f} "
        f"Qz={resources['quartz']:.0f} Au={resources['gold']:.0f} ◇={resources['coreshard']:.0f} "
        f"时代=[{era_text}]"
    )


def event_groups(events: list[UpgradeEvent], day: int, source: str) -> list[UpgradeEvent]:
    return [event for event in events if event.day == day and event.source == source]


def render_markdown(
    snapshots: list[DaySnapshot],
    events: list[UpgradeEvent],
    seed: int,
) -> str:
    lines = [
        "# S2 前十天操作时间线",
        "",
        f"固定随机种子：`{seed}`。每天在 `00:00`、`08:00`、`16:00` 各检查一次手动批量升级，全天最多三条升级消息；自动采购每 10 分钟结算。",
        "",
        "| 天数 | 星球进度 | 手动消息 | 手动等级 | 自动等级 | 已触达节点 | 自动线路 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for snapshot in snapshots:
        lines.append(
            f"| D{snapshot.day} | {snapshot.progress:.4%} | {snapshot.manual_messages}/3 | "
            f"{snapshot.manual_levels} | {snapshot.auto_levels} | {snapshot.nodes_reached}/{len(LOCAL_KEYS)} | {snapshot.auto_nodes} |"
        )

    for snapshot in snapshots:
        manual = event_groups(events, snapshot.day, "manual")
        automatic = event_groups(events, snapshot.day, "auto")
        totals: Counter[str] = Counter()
        for event in automatic:
            totals.update(dict(event.orders))
        lines.extend(
            [
                "",
                f"## D{snapshot.day}",
                "",
                f"日终进度 `{snapshot.progress:.4%}`，手动消息 `{snapshot.manual_messages}/3`，自动升级 `{snapshot.auto_levels}` 级。",
                "",
                "**手动升级**",
                "",
            ]
        )
        if manual:
            lines.extend(f"- `{format_clock(event.minute)}` {format_orders(event.orders)}" for event in manual)
        else:
            lines.append("- 无：三个检查点都没有足够资源或没有合适的新路线。")
        lines.extend(["", "**自动升级汇总**", ""])
        if totals:
            lines.append("- " + "、".join(f"{SPECS[key].name}+{amount}" for key, amount in totals.items()))
        else:
            lines.append("- 无")
        lines.extend(
            [
                "",
                f"<details><summary>展开 {len(automatic)} 个自动采购时点</summary>",
                "",
            ]
        )
        lines.extend(f"- `{format_clock(event.minute)}` {format_orders(event.orders)}" for event in automatic)
        lines.extend(["", "</details>"])

    lines.extend(
        [
            "",
            "## 当前观察",
            "",
            "- 一条手动消息最多会批量选择 8 个科技，并尽量把未自动化的路线直接升到 3 级。",
            "- 因此消息数量很低，但 D2 之后单条消息的决策密度很高；这是下一轮需要由体验判断的重点。",
            "- 自动采购日志很密集，但它不占 QQ 消息额度；正式展示应聚合成阶段报告，而不是逐条发送。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 S2 前十天真实三消息规则验收")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--trace-output",
        type=pathlib.Path,
        default=MODULE_DIR / "FIRST_TEN_DAYS_TRACE.md",
    )
    parser.add_argument("--no-write-trace", action="store_true")
    args = parser.parse_args()

    state, snapshots, events = run(args.days, args.seed)
    if args.days >= 10:
        audit_first_ten_days(snapshots, events)
    for snapshot in snapshots:
        print(format_snapshot(snapshot))

    print("\n手动升级时间线:")
    for event in events:
        if event.source == "manual":
            print(f"D{event.day:02d} {format_clock(event.minute)} {format_orders(event.orders)}")

    print("\n每日自动采购:")
    for snapshot in snapshots:
        automatic = event_groups(events, snapshot.day, "auto")
        totals: Counter[str] = Counter()
        for event in automatic:
            totals.update(dict(event.orders))
        names = "、".join(f"{SPECS[key].name}+{amount}" for key, amount in totals.most_common(12)) or "无"
        print(f"D{snapshot.day:02d} {len(automatic)} 个时点 / +{snapshot.auto_levels}级：{names}")

    if not args.no_write_trace:
        args.trace_output.write_text(render_markdown(snapshots, events, args.seed), encoding="utf-8")
        print(f"\n完整时间线已写入: {args.trace_output}")
    print(
        f"验收结果: days={args.days} depth={state.depth:.0f} "
        f"local_nodes={len(state.ever_local_keys)}/{len(state.local_levels)}"
    )


if __name__ == "__main__":
    main()
