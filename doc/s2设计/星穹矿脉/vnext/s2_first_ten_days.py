"""S2 原型前十天的可复现操作时间线。

玩家按设定频率查看进度，但每天只有三条成功升级消息。挖矿和自动采购仍按
10 分钟固定步长结算；没有买到升级的查看不会消耗消息额度。
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


SETTLEMENT_MINUTES = 10


@dataclass(frozen=True)
class PlayerProfile:
    key: str
    name: str
    check_minutes: tuple[int, ...]


PLAYER_PROFILES = {
    "active": PlayerProfile("active", "活跃玩家", tuple(range(60, 1440, 60))),
    "regular": PlayerProfile("regular", "普通玩家", tuple(range(180, 1440, 180))),
    "low": PlayerProfile("low", "低频玩家", (480, 840, 1260)),
}


@dataclass(frozen=True)
class UpgradeEvent:
    day: int
    minute: int
    source: Literal["manual", "auto"]
    orders: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class DecisionCheck:
    day: int
    minute: int
    orders: tuple[tuple[str, int], ...]

    @property
    def acted(self) -> bool:
        return bool(self.orders)


@dataclass(frozen=True)
class DaySnapshot:
    day: int
    depth: float
    progress: float
    resources: dict[str, float]
    eras: tuple[str, ...]
    newly_entered_eras: tuple[str, ...]
    nodes_reached: int
    new_nodes: int
    auto_nodes: int
    checks: int
    manual_messages: int
    manual_levels: int
    manual_amounts: tuple[tuple[int, int], ...]
    max_projects_per_message: int
    auto_levels: int
    planets: str


def unlocked_eras(state: SimulationState) -> tuple[str, ...]:
    return tuple(era for era in ERA_UNLOCKS if state.era_unlocked(era))


def level_diff(before: dict[str, int], state: SimulationState) -> tuple[tuple[str, int], ...]:
    return tuple(
        (key, state.local_levels[key] - before[key])
        for key in LOCAL_KEYS
        if state.local_levels[key] > before[key]
    )


def run(
    days: int = 10,
    seed: int = 42,
    check_interval_minutes: int | None = None,
    profile: str = "active",
) -> tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent], list[DecisionCheck]]:
    """运行按频率查看、每天最多三条成功升级消息的玩家路径。"""
    if profile not in PLAYER_PROFILES:
        raise ValueError(f"未知玩家画像: {profile}")
    if check_interval_minutes is not None:
        if check_interval_minutes < SETTLEMENT_MINUTES or check_interval_minutes % SETTLEMENT_MINUTES:
            raise ValueError("查看间隔必须是至少 10 分钟的 10 分钟整数倍")
        check_minutes = tuple(range(check_interval_minutes, 1440, check_interval_minutes))
    else:
        check_minutes = PLAYER_PROFILES[profile].check_minutes
    check_minute_set = set(check_minutes)

    state = SimulationState(
        target_depth=_development_target(11),
        seed=seed,
        deterministic=False,
        enforce_daily_limit=True,
    )
    snapshots: list[DaySnapshot] = []
    events: list[UpgradeEvent] = []
    checks: list[DecisionCheck] = []
    previous_depth = 0.0
    previous_planets = state.planets
    previous_nodes = 0
    previous_eras: set[str] = set()

    for current_day in range(1, days + 1):
        if current_day > 1:
            state.start_new_day()
        day_events_start = len(events)
        day_checks_start = len(checks)

        for minute in range(SETTLEMENT_MINUTES, 1440 + 1, SETTLEMENT_MINUTES):
            before = dict(state.local_levels)
            state.mine_block(SETTLEMENT_MINUTES)
            auto_orders = level_diff(before, state)
            if auto_orders:
                events.append(UpgradeEvent(current_day, minute, "auto", auto_orders))

            # 24:00 是日结边界；下一次查看应发生在新一天经过实际游玩时间之后。
            if minute in check_minute_set:
                checks_remaining = sum(1 for check_minute in check_minutes if check_minute > minute)
                orders = _strategy(
                    state,
                    message_budget=1,
                    mode="balanced",
                    checks_remaining=checks_remaining,
                )
                checks.append(DecisionCheck(current_day, minute, orders))
                if orders:
                    events.append(UpgradeEvent(current_day, minute, "manual", orders))

        day_events = events[day_events_start:]
        day_checks = checks[day_checks_start:]
        manual = [event for event in day_events if event.source == "manual"]
        manual_amounts = Counter(amount for event in manual for _, amount in event.orders)
        manual_levels = sum(amount for event in manual for _, amount in event.orders)
        auto_levels = sum(
            amount for event in day_events if event.source == "auto" for _, amount in event.orders
        )
        eras = unlocked_eras(state)
        snapshots.append(
            DaySnapshot(
                day=current_day,
                depth=state.depth,
                progress=state.progress,
                resources=dict(state.resources),
                eras=eras,
                newly_entered_eras=tuple(era for era in eras if era not in previous_eras),
                nodes_reached=len(state.ever_local_keys),
                new_nodes=len(state.ever_local_keys) - previous_nodes,
                auto_nodes=len(state.auto_unlocked),
                checks=len(day_checks),
                manual_messages=state.daily_upgrade_messages,
                manual_levels=manual_levels,
                manual_amounts=tuple(sorted(manual_amounts.items())),
                max_projects_per_message=max((len(event.orders) for event in manual), default=0),
                auto_levels=auto_levels,
                planets=str(state.planets),
            )
        )
        if state.depth <= previous_depth and state.planets == previous_planets:
            raise AssertionError(f"D{current_day} 深度没有前进")
        previous_depth = state.depth
        previous_planets = state.planets
        previous_nodes = len(state.ever_local_keys)
        previous_eras = set(eras)

    return state, snapshots, events, checks


def first_era_day(snapshots: list[DaySnapshot], era: str) -> int | None:
    return next((snapshot.day for snapshot in snapshots if era in snapshot.eras), None)


def audit_first_ten_days(
    snapshots: list[DaySnapshot],
    events: list[UpgradeEvent],
    checks: list[DecisionCheck],
) -> None:
    """把玩家反馈转成不可回归的前十天体验闸门。"""
    first_ten = snapshots[:10]
    if len(first_ten) < 10:
        raise AssertionError("前十天验收必须至少运行 10 天")
    if any(snapshot.manual_messages > 3 for snapshot in first_ten):
        raise AssertionError("出现超过每日 3 条的手动升级消息")
    if any(snapshot.checks < 20 for snapshot in first_ten):
        raise AssertionError("活跃玩家没有获得接近每小时一次的查看机会")

    manual = [event for event in events if event.source == "manual" and event.day <= 10]
    automatic = [event for event in events if event.source == "auto" and event.day <= 10]
    if not manual or not automatic:
        raise AssertionError("前十天必须同时出现手动升级和自动升级")
    first_manual = manual[0]
    if first_manual.day != 1 or not 30 <= first_manual.minute <= 180:
        raise AssertionError("首次升级应在 D1 开始后的约 1 小时内自然出现")
    if max(len(event.orders) for event in manual) > 3:
        raise AssertionError("前期单条升级消息不应塞入超过 3 个项目")

    early_amounts = Counter(
        amount for event in manual if event.day <= 3 for _, amount in event.orders
    )
    all_amounts = Counter(amount for event in manual for _, amount in event.orders)
    if early_amounts[1] < 2:
        raise AssertionError("D1-D3 缺少自然的 +1 升级")
    if not all_amounts[2] or not all_amounts[3]:
        raise AssertionError("前十天应自然混合出现 +1、+2、+3")
    if all_amounts[3] > all_amounts[1] + all_amounts[2]:
        raise AssertionError("+3 升级占比过高，升级策略再次退化为机械批量购买")
    direct_three_by_day = Counter(
        event.day for event in manual if any(amount == 3 for _, amount in event.orders)
    )
    if any(count > 1 for count in direct_three_by_day.values()):
        raise AssertionError("同一天连续直接 +3，策略没有给新科技留下体验空间")

    last_message_by_day = {
        day: max((event.minute for event in manual if event.day == day), default=0)
        for day in range(1, 11)
    }
    if sum(minute >= 720 for minute in last_message_by_day.values()) < 5:
        raise AssertionError("升级消息仍过度集中在凌晨，没有为白天的新路线保留机会")
    if sum(minute <= 180 for minute in last_message_by_day.values()) > 1:
        raise AssertionError("多数日期仍在前三小时机械用完升级消息")

    industrial_day = first_era_day(first_ten, "industrial")
    if industrial_day is None or not 4 <= industrial_day <= 6:
        raise AssertionError(f"工业时代应在 D4-D6 进入，实际为 {industrial_day}")
    if first_era_day(first_ten, "electrical") is not None:
        raise AssertionError("D10 仍应处于工业时代，D9 进入电力也属于过快")
    if any(check.acted and not check.orders for check in checks):
        raise AssertionError("查看记录状态不一致")


def audit_profile_matrix(
    results: dict[str, tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent], list[DecisionCheck]]],
) -> None:
    """确认不同查看习惯只改变路线效率，不破坏前十天阶段结构。"""
    for profile_key, (_, snapshots, events, _) in results.items():
        profile = PLAYER_PROFILES[profile_key]
        if len(snapshots) < 10:
            raise AssertionError(f"{profile.name} 未完成前十天模拟")
        if any(snapshot.manual_messages > 3 for snapshot in snapshots[:10]):
            raise AssertionError(f"{profile.name} 超过每日三条升级消息")
        if first_era_day(snapshots[:10], "electrical") is not None:
            raise AssertionError(f"{profile.name} 在 D10 前过早进入电力时代")
        industrial_day = first_era_day(snapshots[:10], "industrial")
        if industrial_day is None or not 4 <= industrial_day <= 6:
            raise AssertionError(f"{profile.name} 工业时代应在 D4-D6 进入，实际为 {industrial_day}")
        if snapshots[9].nodes_reached < 12:
            raise AssertionError(f"{profile.name} D10 科技接触量过低")
        manual = [event for event in events if event.source == "manual" and event.day <= 10]
        amounts = Counter(amount for event in manual for _, amount in event.orders)
        if not amounts[1] or not amounts[2] or not amounts[3]:
            raise AssertionError(f"{profile.name} 缺少 +1/+2/+3 的自然混合")
        direct_three_by_day = Counter(
            event.day for event in manual if any(amount == 3 for _, amount in event.orders)
        )
        if any(count > 1 for count in direct_three_by_day.values()):
            raise AssertionError(f"{profile.name} 同一天多次直接 +3")


def format_clock(minute: int) -> str:
    if minute == 1440:
        return "24:00"
    return f"{minute // 60:02d}:{minute % 60:02d}"


def format_orders(orders: tuple[tuple[str, int], ...]) -> str:
    return "、".join(f"{SPECS[key].name}+{amount}" for key, amount in orders)


def format_amounts(amounts: tuple[tuple[int, int], ...]) -> str:
    counts = dict(amounts)
    return f"+1×{counts.get(1, 0)} / +2×{counts.get(2, 0)} / +3×{counts.get(3, 0)}"


def format_snapshot(snapshot: DaySnapshot) -> str:
    era_text = "、".join(ERA_LABELS[era] for era in snapshot.eras)
    resources = snapshot.resources
    return (
        f"D{snapshot.day:02d} 进度={snapshot.progress:.4%} 星球={snapshot.planets} "
        f"检查={snapshot.checks} 消息={snapshot.manual_messages}/3 手动+{snapshot.manual_levels}级 "
        f"({format_amounts(snapshot.manual_amounts)}) 自动+{snapshot.auto_levels}级 "
        f"节点={snapshot.nodes_reached}/{len(LOCAL_KEYS)}(+{snapshot.new_nodes}) 自动线={snapshot.auto_nodes} "
        f"矿币={resources['credits']:.0f} Sn={resources['tin']:.0f} Cu={resources['copper']:.0f} "
        f"Qz={resources['quartz']:.0f} Au={resources['gold']:.0f} ◇={resources['coreshard']:.0f} "
        f"时代=[{era_text}]"
    )


def event_groups(events: list[UpgradeEvent], day: int, source: str) -> list[UpgradeEvent]:
    return [event for event in events if event.day == day and event.source == source]


def run_profile_matrix(
    days: int = 10,
    seed: int = 42,
) -> dict[str, tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent], list[DecisionCheck]]]:
    return {key: run(days, seed, profile=key) for key in PLAYER_PROFILES}


def render_markdown(
    snapshots: list[DaySnapshot],
    events: list[UpgradeEvent],
    checks: list[DecisionCheck],
    seed: int,
    profile: PlayerProfile,
    profile_results: dict[
        str,
        tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent], list[DecisionCheck]],
    ]
    | None = None,
) -> str:
    lines = [
        "# S2 前十天操作时间线",
        "",
        f"固定随机种子：`{seed}`。主时间线使用“{profile.name}”画像；只有成功购买升级才消耗每天三条消息额度。挖矿与自动采购每 10 分钟结算。",
        "",
        "| 天数 | 星球进度 | 查看次数 | 成功消息 | 手动等级 | +1/+2/+3 | 自动等级 | 新节点 | 当前时代 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for snapshot in snapshots:
        era = ERA_LABELS[snapshot.eras[-1]]
        lines.append(
            f"| D{snapshot.day} | {snapshot.progress:.4%} | {snapshot.checks} | "
            f"{snapshot.manual_messages}/3 | {snapshot.manual_levels} | {format_amounts(snapshot.manual_amounts)} | "
            f"{snapshot.auto_levels} | {snapshot.new_nodes} | {era} |"
        )

    for snapshot in snapshots:
        manual = event_groups(events, snapshot.day, "manual")
        automatic = event_groups(events, snapshot.day, "auto")
        day_checks = [check for check in checks if check.day == snapshot.day]
        totals: Counter[str] = Counter()
        for event in automatic:
            totals.update(dict(event.orders))
        lines.extend(
            [
                "",
                f"## D{snapshot.day}",
                "",
                f"查看 `{snapshot.checks}` 次，实际升级 `{snapshot.manual_messages}` 次，空查看 `{len(day_checks) - snapshot.manual_messages}` 次；日终进度 `{snapshot.progress:.4%}`。",
                "",
                "**手动升级**",
                "",
            ]
        )
        if manual:
            lines.extend(f"- `{format_clock(event.minute)}` {format_orders(event.orders)}" for event in manual)
        else:
            lines.append("- 无：当天各次查看都没有足够资源或没有合适的新路线。")
        lines.extend(
            [
                "",
                f"<details><summary>展开 {len(day_checks)} 次查看记录</summary>",
                "",
            ]
        )
        lines.extend(
            f"- `{format_clock(check.minute)}` "
            + (format_orders(check.orders) if check.acted else "未升级：保留消息或暂无合适路线")
            for check in day_checks
        )
        lines.extend(["", "</details>"])
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

    totals = Counter(amount for event in events if event.source == "manual" for _, amount in event.orders)
    era_days = {
        ERA_LABELS[era]: first_era_day(snapshots, era)
        for era in ("industrial", "electrical", "modern")
    }
    if profile_results:
        lines.extend(
            [
                "",
                "## 三种玩家画像对比",
                "",
                "| 画像 | 每日查看 | D1 首次升级 | 工业时代 | D10 节点 | D10 进度 | +1/+2/+3 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for key, (_, profile_snapshots, profile_events, profile_checks) in profile_results.items():
            manual_events = [event for event in profile_events if event.source == "manual"]
            first_manual = manual_events[0]
            amounts = Counter(amount for event in manual_events for _, amount in event.orders)
            check_count = len([check for check in profile_checks if check.day == 1])
            industrial_day = first_era_day(profile_snapshots, "industrial")
            lines.append(
                f"| {PLAYER_PROFILES[key].name} | {check_count} | {format_clock(first_manual.minute)} | "
                f"D{industrial_day} | {profile_snapshots[9].nodes_reached}/{len(LOCAL_KEYS)} | "
                f"{profile_snapshots[9].progress:.4%} | {amounts[1]}/{amounts[2]}/{amounts[3]} |"
            )
    lines.extend(
        [
            "",
            "## 验收摘要",
            "",
            f"- 前十天手动数量分布：`+1×{totals[1]}`、`+2×{totals[2]}`、`+3×{totals[3]}`。",
            "- 工业时代首次进入："
            f"`{('D' + str(era_days['工业时代'])) if era_days['工业时代'] else '前十天未进入'}`；"
            "电力时代首次进入："
            f"`{('D' + str(era_days['电力时代'])) if era_days['电力时代'] else '前十天未进入'}`。",
            f"- 现代时代首次进入：`{('D' + str(era_days['现代时代'])) if era_days['现代时代'] else '前十天未进入'}`。",
            "- 自动采购不占 QQ 消息额度；正式展示应按小时或按日聚合，不逐条打扰玩家。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 S2 前十天真实三消息规则验收")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile", choices=tuple(PLAYER_PROFILES), default="active")
    parser.add_argument("--check-interval", type=int, default=None, help="覆盖画像，按固定分钟间隔查看")
    parser.add_argument(
        "--trace-output",
        type=pathlib.Path,
        default=MODULE_DIR / "FIRST_TEN_DAYS_TRACE.md",
    )
    parser.add_argument("--no-write-trace", action="store_true")
    args = parser.parse_args()

    profile_results = None
    if args.days >= 10 and args.check_interval is None:
        profile_results = run_profile_matrix(args.days, args.seed)
        audit_profile_matrix(profile_results)
        audit_first_ten_days(*profile_results["active"][1:])
        state, snapshots, events, checks = profile_results[args.profile]
        profile = PLAYER_PROFILES[args.profile]
    else:
        state, snapshots, events, checks = run(
            args.days,
            args.seed,
            args.check_interval,
            args.profile,
        )
        profile = PLAYER_PROFILES[args.profile]
        if args.check_interval is not None:
            profile = PlayerProfile(
                "custom",
                f"每 {args.check_interval} 分钟查看",
                tuple(range(args.check_interval, 1440, args.check_interval)),
            )
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
        args.trace_output.write_text(
            render_markdown(snapshots, events, checks, args.seed, profile, profile_results),
            encoding="utf-8",
        )
        print(f"\n完整时间线已写入: {args.trace_output}")
    print(
        f"验收结果: days={args.days} depth={state.depth:.0f} "
        f"local_nodes={len(state.ever_local_keys)}/{len(state.local_levels)}"
    )


if __name__ == "__main__":
    main()
