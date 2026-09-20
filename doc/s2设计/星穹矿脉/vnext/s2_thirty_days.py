"""Repeatable D1-D30 audit for the S2 vNext economy."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from s2_first_ten_days import (
    PLAYER_PROFILES,
    DaySnapshot,
    UpgradeEvent,
    format_clock,
    run,
    run_opportunity_matrix,
)
from s2_mining_simulator import (
    ERA_LABELS,
    ERA_SEQUENCE,
    SETTLEMENT_MINUTES,
    SPECS,
    STRATEGY_CONFIG,
    SimulationState,
    strategy_visit,
)


DAYS = 30
D11_MINUTE = 10 * 1440
END_MINUTE = DAYS * 1440
DEFAULT_SEEDS = (1, 7, 42, 99, 2026)
CORE_PROFILES = ("daily", "absent", "active")
HERE = Path(__file__).resolve().parent
RUNNER = HERE / "s2_web_parity_runner.mjs"


@dataclass(frozen=True)
class VisitDrain:
    day: int
    minute: int
    purchased_levels: int
    stop_reason: str


@dataclass(frozen=True)
class FirstPurchaseGap:
    start_minute: int
    end_minute: int
    start_label: str
    end_label: str

    @property
    def minutes(self) -> int:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class ProfileAudit:
    profile: str
    state: SimulationState
    snapshots: tuple[DaySnapshot, ...]
    events: tuple[UpgradeEvent, ...]
    visits: tuple[VisitDrain, ...]
    era_first_minutes: dict[str, int]
    longest_first_purchase_gap: FirstPurchaseGap
    longest_first_purchase_gap_d11_plus: FirstPurchaseGap


def absolute_event_minute(event: UpgradeEvent) -> int:
    return (event.day - 1) * 1440 + event.minute


def format_absolute_minute(minute: int) -> str:
    day = minute // 1440 + 1
    day_minute = minute % 1440
    if minute == END_MINUTE:
        return "D31 00:00"
    return f"D{day} {format_clock(day_minute)}"


def _visit_stop_reason(state: SimulationState) -> str:
    candidates = state.manual_candidates()
    if not candidates:
        return "无可建科技"
    if any(state.cost_for(key) <= state.credits + 1e-9 for key in candidates):
        return "仍有可负担科技"
    return "矿币不足"


def audit_visit_drains(
    days: int,
    seed: int,
    profile: str,
    route: str,
) -> tuple[VisitDrain, ...]:
    """Replay visits and record that each one drains all affordable purchases."""
    state = SimulationState(seed=seed)
    checks = set(PLAYER_PROFILES[profile].check_minutes)
    visits: list[VisitDrain] = []
    for day in range(1, days + 1):
        for minute in range(SETTLEMENT_MINUTES, 1441, SETTLEMENT_MINUTES):
            state.mine_block()
            if minute not in checks:
                continue
            purchases = strategy_visit(state, route)
            visits.append(VisitDrain(
                day=day,
                minute=minute,
                purchased_levels=len(purchases),
                stop_reason=_visit_stop_reason(state),
            ))
    return tuple(visits)


def _first_purchase_points(
    events: Iterable[UpgradeEvent],
) -> list[tuple[int, str]]:
    seen: set[str] = set()
    points: list[tuple[int, str]] = []
    for event in events:
        if event.key in seen:
            continue
        seen.add(event.key)
        points.append((absolute_event_minute(event), SPECS[event.key].name))
    return points


def longest_first_purchase_gap(
    events: Iterable[UpgradeEvent],
    *,
    start_minute: int = 0,
    end_minute: int = END_MINUTE,
) -> FirstPurchaseGap:
    points = [
        (minute, label)
        for minute, label in _first_purchase_points(events)
        if start_minute <= minute <= end_minute
    ]
    boundaries = [(start_minute, "审计起点"), *points, (end_minute, "审计终点")]
    normalized: list[tuple[int, str]] = []
    for point in boundaries:
        if normalized and point[0] == normalized[-1][0]:
            normalized[-1] = point
        else:
            normalized.append(point)
    gaps = [
        FirstPurchaseGap(left[0], right[0], left[1], right[1])
        for left, right in zip(normalized, normalized[1:])
    ]
    return max(gaps, key=lambda item: item.minutes)


def run_profile_audit(
    seed: int = 42,
    profile: str = "daily",
    route: str = "balanced",
) -> ProfileAudit:
    state, snapshots, events = run(DAYS, seed, profile=profile, route=route)
    visits = audit_visit_drains(DAYS, seed, profile, route)
    return ProfileAudit(
        profile=profile,
        state=state,
        snapshots=tuple(snapshots),
        events=tuple(events),
        visits=visits,
        era_first_minutes=dict(snapshots[-1].era_first_minutes),
        longest_first_purchase_gap=longest_first_purchase_gap(events),
        longest_first_purchase_gap_d11_plus=longest_first_purchase_gap(
            events, start_minute=D11_MINUTE
        ),
    )


def run_core_audits(
    seed: int = 42,
    route: str = "balanced",
) -> dict[str, ProfileAudit]:
    return {
        profile: run_profile_audit(seed, profile, route)
        for profile in CORE_PROFILES
    }


def run_web_replay(
    seed: int,
    profile: str,
    route: str,
) -> dict[str, object]:
    completed = subprocess.run(
        ["node", str(RUNNER), str(seed), str(DAYS), profile, route],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
    )
    return json.loads(completed.stdout)


def assert_web_parity(audit: ProfileAudit, route: str = "balanced") -> None:
    web = run_web_replay(audit.state.seed, audit.profile, route)
    web_snapshots = web["snapshots"]
    if len(audit.snapshots) != len(web_snapshots):
        raise AssertionError("Python/JS snapshot count mismatch")
    for py, js in zip(audit.snapshots, web_snapshots, strict=True):
        exact = {
            "day": py.day,
            "manualLevels": py.manual_levels,
            "autoLevels": py.auto_levels,
            "helperLevels": py.helper_levels,
            "manualCommands": py.manual_commands,
            "visits": py.visits,
            "currentEra": py.current_era,
        }
        for key, value in exact.items():
            if js[key] != value:
                raise AssertionError(f"D{py.day} Python/JS {key} mismatch")
        floats = {
            "depth": py.depth,
            "credits": py.credits,
            "incomeMultiplier": py.income_multiplier,
            "depthMultiplier": py.depth_multiplier,
        }
        for key, value in floats.items():
            if not math.isclose(value, js[key], rel_tol=1e-12):
                raise AssertionError(f"D{py.day} Python/JS {key} mismatch")

    py_events = [
        (item.day, item.minute, item.source, item.key, item.level, item.cost)
        for item in audit.events
    ]
    js_events = [
        (
            item["day"], item["minute"], item["source"],
            item["key"], item["level"], item["cost"],
        )
        for item in web["events"]
    ]
    if len(py_events) != len(js_events):
        raise AssertionError("Python/JS event count mismatch")
    for index, (py, js) in enumerate(zip(py_events, js_events, strict=True)):
        if py[:5] != js[:5] or not math.isclose(py[5], js[5], rel_tol=1e-12):
            raise AssertionError(f"Python/JS event mismatch at index {index}")

    final_exact = {
        "levels": audit.state.levels,
        "manualLevels": audit.state.manual_levels,
        "autoUnlocked": sorted(audit.state.auto_unlocked),
        "helperEnabled": audit.state.helper_enabled,
        "nextHelperMinute": audit.state._next_helper_minute,
        "totalHelperLevels": audit.state.total_helper_levels,
        "totalManualLevels": audit.state.total_manual_levels,
        "totalManualCommands": audit.state.total_manual_commands,
        "totalAutoLevels": audit.state.total_auto_levels,
    }
    for key, value in final_exact.items():
        if web[key] != value:
            raise AssertionError(f"Python/JS final {key} mismatch")

    py_report = audit.state.last_helper_report
    js_report = web["lastHelperReport"]
    if py_report is None or js_report is None:
        if py_report != js_report:
            raise AssertionError("Python/JS final lastHelperReport mismatch")
        return
    for key in ("minute", "levels"):
        if py_report[key] != js_report[key]:
            raise AssertionError(f"Python/JS helper report {key} mismatch")
    if not math.isclose(py_report["spent"], js_report["spent"], rel_tol=1e-12):
        raise AssertionError("Python/JS helper report spent mismatch")
    if len(py_report["items"]) != len(js_report["items"]):
        raise AssertionError("Python/JS helper report item count mismatch")
    for index, (py_item, js_item) in enumerate(
        zip(py_report["items"], js_report["items"], strict=True)
    ):
        if (
            py_item["key"] != js_item["key"]
            or py_item["level"] != js_item["level"]
            or not math.isclose(py_item["cost"], js_item["cost"], rel_tol=1e-12)
        ):
            raise AssertionError(
                f"Python/JS helper report item mismatch at index {index}"
            )


def assert_finite_nonnegative(audit: ProfileAudit) -> None:
    values = [
        value
        for item in audit.snapshots
        for value in (
            item.depth,
            item.credits,
            item.income_multiplier,
            item.depth_multiplier,
            *item.multipliers.values(),
        )
    ]
    values.extend((audit.state.depth, audit.state.credits))
    if not all(math.isfinite(value) for value in values):
        raise AssertionError(f"{audit.profile} contains non-finite values")
    if min(item.credits for item in audit.snapshots) < -1e-9:
        raise AssertionError(f"{audit.profile} contains a negative balance")


def acceptance_failures(
    audits: dict[str, ProfileAudit],
    opportunity: dict[tuple[int, str], list[int]] | None = None,
) -> list[str]:
    failures: list[str] = []
    for profile, audit in audits.items():
        try:
            assert_finite_nonnegative(audit)
        except AssertionError as exc:
            failures.append(str(exc))
        bad_visits = [
            item for item in audit.visits
            if item.stop_reason == "仍有可负担科技"
        ]
        if bad_visits:
            failures.append(f"{profile} has {len(bad_visits)} visits that did not drain")
    for profile in ("daily", "absent"):
        if "future" not in audits[profile].era_first_minutes:
            failures.append(f"{profile} did not unlock future by D30")
        gap = audits[profile].longest_first_purchase_gap_d11_plus
        if gap.minutes > 72 * 60:
            failures.append(
                f"{profile} D11+ new-technology gap is "
                f"{gap.minutes / 60:.1f}h (>72h)"
            )
    if opportunity is not None:
        for (seed, route), counts in opportunity.items():
            maximum = max(counts[10:], default=0)
            if maximum > 12:
                failures.append(
                    f"seed={seed} route={route} D11+ manual opportunity "
                    f"max is {maximum} (>12)"
                )
    return failures


def _window_counts(
    snapshots: tuple[DaySnapshot, ...],
    first_day: int,
    last_day: int,
) -> tuple[int, int, int]:
    selected = snapshots[first_day - 1:last_day]
    return (
        sum(item.manual_levels for item in selected),
        sum(item.helper_levels for item in selected),
        sum(item.auto_levels for item in selected),
    )


def _format_gap(gap: FirstPurchaseGap) -> str:
    return (
        f"{gap.minutes / 60:.1f}h "
        f"({format_absolute_minute(gap.start_minute)} {gap.start_label} -> "
        f"{format_absolute_minute(gap.end_minute)} {gap.end_label})"
    )


def _format_milestone(minute: int | None) -> str:
    return "D30内未到达" if minute is None else format_absolute_minute(minute)


def render_markdown(
    audits: dict[str, ProfileAudit],
    seed: int,
    route: str,
    opportunity: dict[tuple[int, str], list[int]] | None = None,
) -> str:
    lines = [
        "# S2 vNext 三十天审计",
        "",
        f"> seed={seed}，路线={route}。数据来自 `s2_first_ten_days.run(days=30)`；"
        "首次科技间隔包含审计起点、D30 末尾和 D11 边界。",
        "",
        "## D11-D30 购买窗口",
        "",
        "| 画像 | D11-D20 手动/助手/自动 | D21-D30 手动/助手/自动 | D30 深度 | D30 矿币 |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile, audit in audits.items():
        first = "/".join(map(str, _window_counts(audit.snapshots, 11, 20)))
        second = "/".join(map(str, _window_counts(audit.snapshots, 21, 30)))
        lines.append(
            f"| {PLAYER_PROFILES[profile].name} | {first} | {second} | "
            f"{audit.state.depth:,.0f} | {audit.state.credits:,.0f} |"
        )

    lines += [
        "",
        "## 时代首次到达",
        "",
        "| 画像 | " + " | ".join(ERA_LABELS[era] for era in ERA_SEQUENCE) + " |",
        "|---|" + "---:|" * len(ERA_SEQUENCE),
    ]
    for profile, audit in audits.items():
        milestones = " | ".join(
            _format_milestone(audit.era_first_minutes.get(era))
            for era in ERA_SEQUENCE
        )
        lines.append(f"| {PLAYER_PROFILES[profile].name} | {milestones} |")

    lines += [
        "",
        "## 最长无新科技首次购买间隔",
        "",
        "| 画像 | D1-D30（含末尾） | D11-D30（含边界与末尾） |",
        "|---|---|---|",
    ]
    for profile, audit in audits.items():
        lines.append(
            f"| {PLAYER_PROFILES[profile].name} | "
            f"{_format_gap(audit.longest_first_purchase_gap)} | "
            f"{_format_gap(audit.longest_first_purchase_gap_d11_plus)} |"
        )

    daily = audits["daily"]
    visits_by_day = {item.day: item for item in daily.visits}
    lines += [
        "",
        "## 每日一次画像买到买不起",
        "",
        "| 日 | 20:00 买入级数 | 停止原因 | 手动/助手/自动 |",
        "|---:|---:|---|---:|",
    ]
    for snapshot in daily.snapshots:
        visit = visits_by_day[snapshot.day]
        lines.append(
            f"| D{snapshot.day} | {visit.purchased_levels} | {visit.stop_reason} | "
            f"{snapshot.manual_levels}/{snapshot.helper_levels}/{snapshot.auto_levels} |"
        )

    if opportunity is not None:
        lines += [
            "",
            "## 五 seed / 四路线 opportunity 次数",
            "",
            "| Seed | 路线 | D1-D10 | D11-D20 | D21-D30 | D11+ 单日最大 |",
            "|---:|---|---:|---:|---:|---:|",
        ]
        for (matrix_seed, matrix_route), counts in opportunity.items():
            lines.append(
                f"| {matrix_seed} | {matrix_route} | {sum(counts[:10])} | "
                f"{sum(counts[10:20])} | {sum(counts[20:30])} | "
                f"{max(counts[10:])} |"
            )

    lines += ["", "## 验收", ""]
    failures = acceptance_failures(audits, opportunity)
    if failures:
        lines.extend(f"- FAIL: {item}" for item in failures)
    else:
        matrix_clause = (
            "，五 seed / 四路线 D11+ 单日 opportunity 不超过 12"
            if opportunity is not None
            else ""
        )
        lines.append(
            "- PASS: 数值有限且余额非负，daily/absent 在 D30 前到达未来时代，"
            f"D11+ 新科技空档不超过 72 小时{matrix_clause}。"
        )
    lines.append("")
    return "\n".join(lines)


def resolve_output_path(output: Path) -> Path:
    if not output.is_absolute():
        output = HERE / output if output.parent == Path(".") else Path.cwd() / output
    return output.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S2 vNext 三十天审计")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--route",
        choices=tuple(STRATEGY_CONFIG["routeVariants"]),
        default="balanced",
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="运行五 seed x 四路线 opportunity 统计",
    )
    parser.add_argument(
        "--output",
        nargs="?",
        type=Path,
        const=Path("THIRTY_DAYS_TRACE.md"),
        help="显式写出 Markdown；省略路径时写 THIRTY_DAYS_TRACE.md",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    audits = run_core_audits(args.seed, args.route)
    for audit in audits.values():
        assert_web_parity(audit, args.route)
    opportunity = (
        run_opportunity_matrix(DAYS, DEFAULT_SEEDS)
        if args.matrix
        else None
    )

    for profile, audit in audits.items():
        d11_20 = _window_counts(audit.snapshots, 11, 20)
        d21_30 = _window_counts(audit.snapshots, 21, 30)
        print(
            f"{profile}: era={audit.snapshots[-1].current_era} "
            f"D11-20={d11_20[0]}/{d11_20[1]}/{d11_20[2]} "
            f"D21-30={d21_30[0]}/{d21_30[1]}/{d21_30[2]} "
            f"gap(all/D11+)={audit.longest_first_purchase_gap.minutes / 60:.1f}h/"
            f"{audit.longest_first_purchase_gap_d11_plus.minutes / 60:.1f}h"
        )
    if opportunity is not None:
        for (matrix_seed, matrix_route), counts in opportunity.items():
            print(
                f"matrix seed={matrix_seed} route={matrix_route}: "
                f"D1-10={sum(counts[:10])} D11-20={sum(counts[10:20])} "
                f"D21-30={sum(counts[20:30])} D11+max={max(counts[10:])}"
            )
        maximum = max(max(counts[10:]) for counts in opportunity.values())
        print(f"matrix: {len(opportunity)} cases, D11+ max opportunity={maximum}")
    failures = acceptance_failures(audits, opportunity)
    print("acceptance: PASS" if not failures else "acceptance: FAIL")
    for item in failures:
        print(f"- {item}")

    if args.output is not None:
        output = resolve_output_path(args.output)
        output.write_text(
            render_markdown(audits, args.seed, args.route, opportunity),
            encoding="utf-8",
        )
        print(f"wrote: {output}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
