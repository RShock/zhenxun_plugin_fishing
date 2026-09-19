"""D1-D10 replay and economic opportunity audit for S2 vNext."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from s2_mining_simulator import (
    ERA_LABELS,
    ERA_SEQUENCE,
    LOCAL_KEYS,
    RULES,
    SETTLEMENT_MINUTES,
    SPECS,
    STRATEGY_CONFIG,
    SimulationState,
    strategy_visit,
)


@dataclass(frozen=True)
class PlayerProfile:
    key: str
    name: str
    check_minutes: tuple[int, ...]


PLAYER_PROFILES = {
    key: PlayerProfile(key, item["name"], tuple(int(value) for value in item["checkMinutes"]))
    for key, item in STRATEGY_CONFIG["profiles"].items()
}


@dataclass(frozen=True)
class UpgradeEvent:
    day: int
    minute: int
    source: Literal["manual", "auto", "helper"]
    key: str
    level: int
    cost: float


@dataclass(frozen=True)
class DaySnapshot:
    day: int
    depth: float
    credits: float
    manual_levels: int
    auto_levels: int
    helper_levels: int
    manual_commands: int
    visits: int
    auto_technologies: int
    nodes_reached: int
    current_era: str
    income_multiplier: float
    depth_multiplier: float
    multipliers: dict[str, float]
    era_first_minutes: dict[str, int]


@dataclass(frozen=True)
class HelperMatrixResult:
    seed: int
    route: str
    daily_industrial_minute: int | None
    absent_industrial_minute: int | None
    daily_electrical_minute: int | None
    absent_electrical_minute: int | None
    electrical_lag_minutes: int | None
    daily_max_manual_levels: int
    daily_max_helper_levels: int
    daily_max_total_purchases: int
    absent_max_helper_levels: int
    absent_max_total_purchases: int
    daily_depth: float
    absent_depth: float


def format_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def run(
    days: int = 10,
    seed: int = 42,
    *,
    profile: str = "daily",
    route: str = "balanced",
) -> tuple[SimulationState, list[DaySnapshot], list[UpgradeEvent]]:
    if type(days) is not int or days <= 0:
        raise ValueError("days must be a positive integer")
    if profile not in PLAYER_PROFILES:
        raise ValueError(f"未知玩家画像: {profile}")
    if route not in STRATEGY_CONFIG["routeVariants"]:
        raise ValueError(f"未知路线: {route}")
    state = SimulationState(seed=seed)
    checks = set(PLAYER_PROFILES[profile].check_minutes)
    snapshots: list[DaySnapshot] = []
    events: list[UpgradeEvent] = []
    era_first_minutes = {ERA_SEQUENCE[0]: 0}

    def record_eras() -> None:
        for era in ERA_SEQUENCE:
            if state.era_unlocked(era):
                era_first_minutes.setdefault(era, state.minute)

    for day in range(1, days + 1):
        manual_before = state.total_manual_levels
        auto_before = state.total_auto_levels
        helper_before = state.total_helper_levels
        commands_before = state.total_manual_commands
        visits = 0
        for minute in range(SETTLEMENT_MINUTES, 1441, SETTLEMENT_MINUTES):
            state.mine_block()
            record_eras()
            for item in state.last_block_events:
                events.append(UpgradeEvent(
                    day, int(item["minute"]) - (day - 1) * 1440,
                    item["source"], item["key"], item["level"], item["cost"]
                ))
            if minute in checks:
                visits += 1
                for key, level, cost in strategy_visit(state, route):
                    events.append(UpgradeEvent(day, minute, "manual", key, level, cost))
                record_eras()
        factors = state.multiplier_breakdown()
        snapshots.append(DaySnapshot(
            day=day,
            depth=state.depth,
            credits=state.credits,
            manual_levels=state.total_manual_levels - manual_before,
            auto_levels=state.total_auto_levels - auto_before,
            helper_levels=state.total_helper_levels - helper_before,
            manual_commands=state.total_manual_commands - commands_before,
            visits=visits,
            auto_technologies=len(state.auto_unlocked),
            nodes_reached=len(state.ever_keys),
            current_era=state.current_era(),
            income_multiplier=state.income_multiplier(),
            depth_multiplier=state.depth_multiplier(),
            multipliers=factors,
            era_first_minutes=dict(era_first_minutes),
        ))
    return state, snapshots, events


def run_profile_matrix(days: int = 10, seed: int = 42, route: str = "balanced"):
    return {key: run(days, seed, profile=key, route=route) for key in PLAYER_PROFILES}


def run_opportunity_matrix(
    days: int = 10,
    seeds: tuple[int, ...] = (1, 7, 42, 99, 2026),
) -> dict[tuple[int, str], list[int]]:
    """Measure how many commissioning levels high-frequency routes can buy."""
    result: dict[tuple[int, str], list[int]] = {}
    check_interval = int(STRATEGY_CONFIG["opportunityCheckIntervalMinutes"])
    for seed in seeds:
        for route in STRATEGY_CONFIG["routeVariants"]:
            state = SimulationState(seed=seed)
            counts: list[int] = []
            for day in range(1, days + 1):
                before = state.total_manual_levels
                for minute in range(SETTLEMENT_MINUTES, 1441, SETTLEMENT_MINUTES):
                    state.mine_block()
                    if minute % check_interval == 0:
                        strategy_visit(state, route)
                counts.append(state.total_manual_levels - before)
            result[(seed, route)] = counts
    return result


def run_helper_ten_day_matrix(
    seeds: tuple[int, ...] = (1, 7, 42, 99, 2026),
) -> list[HelperMatrixResult]:
    results: list[HelperMatrixResult] = []
    for seed in seeds:
        for route in STRATEGY_CONFIG["routeVariants"]:
            _, daily, _ = run(10, seed, profile="daily", route=route)
            _, absent, _ = run(10, seed, profile="absent", route=route)
            daily_electrical = daily[-1].era_first_minutes.get("electrical")
            absent_electrical = absent[-1].era_first_minutes.get("electrical")
            lag = None
            if daily_electrical is not None and absent_electrical is not None:
                lag = absent_electrical - daily_electrical
            results.append(HelperMatrixResult(
                seed=seed,
                route=route,
                daily_industrial_minute=daily[-1].era_first_minutes.get("industrial"),
                absent_industrial_minute=absent[-1].era_first_minutes.get("industrial"),
                daily_electrical_minute=daily_electrical,
                absent_electrical_minute=absent_electrical,
                electrical_lag_minutes=lag,
                daily_max_manual_levels=max(item.manual_levels for item in daily),
                daily_max_helper_levels=max(item.helper_levels for item in daily),
                daily_max_total_purchases=max(
                    item.manual_levels + item.helper_levels + item.auto_levels for item in daily
                ),
                absent_max_helper_levels=max(item.helper_levels for item in absent),
                absent_max_total_purchases=max(
                    item.helper_levels + item.auto_levels for item in absent
                ),
                daily_depth=daily[-1].depth,
                absent_depth=absent[-1].depth,
            ))
    return results


def audit_opportunities(matrix: dict[tuple[int, str], list[int]]) -> list[str]:
    warning = int(RULES["manualBurstWarningLevels"])
    return [
        f"seed={seed} route={route}: {counts}"
        for (seed, route), counts in matrix.items()
        if max(counts) > warning
    ]


def audit_profiles(results) -> None:
    for key, (_, snapshots, events) in results.items():
        if any(item.manual_levels > item.manual_commands * int(RULES["batchCommandMaxLevels"]) for item in snapshots):
            raise AssertionError(f"{key} 手动命令统计错误")
        if any(item.visits != len(PLAYER_PROFILES[key].check_minutes) for item in snapshots):
            raise AssertionError(f"{key} 查看次数与画像不符")
        if key == "absent" and any(item.manual_levels or item.manual_commands or item.visits for item in snapshots):
            raise AssertionError("缺席玩家发生了手动购买")
        is_ten_day_acceptance = len(snapshots) == 10
        if is_ten_day_acceptance and key in {"daily", "absent"} and not any(event.source == "helper" for event in events):
            raise AssertionError(f"{key} 没有触发笨助手")
        if is_ten_day_acceptance and key in {"daily", "absent"} and snapshots[-1].current_era != "electrical":
            raise AssertionError(f"{key} 玩家 D10 尚未进入电气时代")


def format_milestone(minute: int | None) -> str:
    if minute is None:
        return "D10内未到达"
    day = minute // 1440 + 1
    day_minute = minute % 1440
    return f"D{day} {format_clock(day_minute)}"


def format_lag(minutes: int | None) -> str:
    if minutes is None:
        return "不可比较"
    sign = "+" if minutes >= 0 else "-"
    absolute = abs(minutes)
    return f"{sign}{absolute // 1440}天{absolute % 1440 // 60}小时{absolute % 60}分"


def render_markdown(results, opportunity, helper_matrix, seed: int) -> str:
    _, daily, events = results["daily"]
    days = len(daily)
    lines = [
        f"# S2 vNext v3 前 {days} 天轨迹",
        "",
        f"> 固定 seed={seed}。玩家可批量升级；笨助手每天 24:00 为未自动化科技购买可负担的最低价等级。",
        "> 每小时自动采购仍保留未来 3 个建造等级预算；助手不保留预算，手动次数不设每日硬限。",
        "> Python 策略回放为了保留逐级事件与失败位置，每一级调用一次升级命令；网页可把同一访问中的这些等级合并成批量命令。因此经济结果可对拍，命令次数不应直接比较。",
        "",
        "## 每日一次玩家逐日摘要",
        "",
        "| 日 | 访问 | 手动级 | 命令 | 助手级 | 自动级 | 自动科技 | 深度 | 矿币 | 收入× | 深度× | 时代 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in daily:
        lines.append(
            f"| D{item.day} | {item.visits} | {item.manual_levels} | {item.manual_commands} | {item.helper_levels} | {item.auto_levels} | {item.auto_technologies} | "
            f"{item.depth:,.0f} | {item.credits:,.0f} | {item.income_multiplier:,.2f} | "
            f"{item.depth_multiplier:,.2f} | {ERA_LABELS[item.current_era]} |"
        )
    lines += ["", "## 每日玩家升级", ""]
    for day in range(1, len(daily) + 1):
        day_events = [event for event in events if event.day == day and event.source in {"manual", "helper"}]
        text = "；".join(f"{format_clock(event.minute)} {event.source} {SPECS[event.key].name}→L{event.level}" for event in day_events)
        lines.append(f"- **D{day}**：{text or '无'}")
    lines += ["", "## 查看画像", "", f"| 画像 | D1-D{days} 手动/助手级 | D{days} 深度 | D{days} 时代 |", "|---|---|---:|---|"]
    for key, (_, snapshots, _) in results.items():
        counts = "；".join(f"{item.manual_levels}/{item.helper_levels}" for item in snapshots)
        lines.append(f"| {PLAYER_PROFILES[key].name} | {counts} | {snapshots[-1].depth:,.0f} | {ERA_LABELS[snapshots[-1].current_era]} |")
    lines += [
        "",
        "## 多 seed / 多路线机会搜索",
        "",
        "> 这里仅采样固定的 5 个 seed 和 4 条启发式路线，用于发现明显的购买突增；20 条结果不是对全部可行玩家策略的穷尽证明。",
        "",
        f"| Seed | 路线 | D1-D{days} 可购级 | 诊断 |",
        "|---:|---|---|---|",
    ]
    for (matrix_seed, route), counts in opportunity.items():
        ok = max(counts) <= int(RULES["manualBurstWarningLevels"])
        lines.append(f"| {matrix_seed} | {route} | {'/'.join(map(str, counts))} | {'未触发爆发预警' if ok else '关注'} |")
    lines += [
        "",
        "## 独立固定十日矩阵",
        "",
        "> 缺席落后时间以双方首次进入电气时代的绝对分钟差计算；正数表示完全缺席更晚。这里只验证 D1-D10，不代表 120 天完整流程。",
        "",
        "| Seed | 路线 | 每日工业 | 缺席工业 | 每日电气 | 缺席电气 | 缺席落后 | 每日最大手动/助手/总购买 | 缺席最大助手/总购买 | D10深度 每日/缺席 |",
        "|---:|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for item in helper_matrix:
        lines.append(
            f"| {item.seed} | {item.route} | {format_milestone(item.daily_industrial_minute)} | "
            f"{format_milestone(item.absent_industrial_minute)} | {format_milestone(item.daily_electrical_minute)} | "
            f"{format_milestone(item.absent_electrical_minute)} | {format_lag(item.electrical_lag_minutes)} | "
            f"{item.daily_max_manual_levels}/{item.daily_max_helper_levels}/{item.daily_max_total_purchases} | "
            f"{item.absent_max_helper_levels}/{item.absent_max_total_purchases} | "
            f"{item.daily_depth:,.0f}/{item.absent_depth:,.0f} |"
        )
    lines += ["", "网页实操与独立 JS 测试记录见 `HELPER_PLAYTEST.md`；运行本生成器不代表已重新执行这些检查。"]
    lines += ["", f"## D{days} 乘区拆解", ""]
    for key, value in daily[-1].multipliers.items():
        if value > 1.000001:
            lines.append(f"- `{key}`：×{value:,.4f}")
    lines += ["", f"D{days} 已接触 {daily[-1].nodes_reached}/{len(LOCAL_KEYS)} 个科技定义；后续时代储备科技状态为 reserve，不参与购买。", ""]
    return "\n".join(lines)


def resolve_output_path(output: Path) -> Path:
    if not output.is_absolute():
        output = Path(__file__).parent / output if output.parent == Path(".") else Path.cwd() / output
    output = output.resolve()
    historical = Path(__file__).with_name("FIRST_TEN_DAYS_TRACE.md").resolve()
    if output == historical:
        raise ValueError("拒绝覆盖历史 FIRST_TEN_DAYS_TRACE.md；请使用 HELPER_TEN_DAYS_TRACE.md")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="S2 vNext 前十天审计")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile", choices=tuple(PLAYER_PROFILES), default="daily")
    parser.add_argument("--route", choices=tuple(STRATEGY_CONFIG["routeVariants"]), default="balanced")
    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument("--output", type=Path)
    output_options.add_argument("--no-write", action="store_true", help="兼容旧命令；默认不写文件")
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")
    output_path = resolve_output_path(args.output) if args.output else None
    results = run_profile_matrix(args.days, args.seed, args.route)
    opportunity = run_opportunity_matrix(args.days)
    audit_profiles(results)
    warnings = audit_opportunities(opportunity)
    if output_path:
        helper_matrix = run_helper_ten_day_matrix()
        markdown = render_markdown(results, opportunity, helper_matrix, args.seed)
        output_path.write_text(markdown, encoding="utf-8")
    _, snapshots, _ = results[args.profile]
    for item in snapshots:
        print(
            f"D{item.day}: 手动={item.manual_levels} 助手={item.helper_levels} 自动={item.auto_levels} "
            f"深度={item.depth:,.0f} 矿币={item.credits:,.0f} 时代={ERA_LABELS[item.current_era]}"
        )
    for warning in warnings:
        print(f"单日建造关注: {warning}")


if __name__ == "__main__":
    main()
