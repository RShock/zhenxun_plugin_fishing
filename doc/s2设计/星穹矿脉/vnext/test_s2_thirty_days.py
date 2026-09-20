from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

import s2_thirty_days as thirty_days
from s2_mining_simulator import GAME_DATA
from s2_thirty_days import (
    CORE_PROFILES,
    DAYS,
    DEFAULT_SEEDS,
    acceptance_failures,
    assert_finite_nonnegative,
    assert_web_parity,
    build_parser,
    render_markdown,
    run_core_audits,
    run_opportunity_matrix,
    run_profile_audit,
)


@pytest.fixture(scope="module")
def audits():
    return run_core_audits()


@pytest.fixture(scope="module")
def opportunity():
    return run_opportunity_matrix(DAYS, DEFAULT_SEEDS)


def test_default_audit_is_repeatable_and_does_not_select_output() -> None:
    args = build_parser().parse_args([])
    assert args.seed == 42
    assert args.output is None
    assert not args.matrix

    first = run_profile_audit()
    second = run_profile_audit()
    assert first.snapshots == second.snapshots
    assert first.events == second.events
    assert first.visits == second.visits
    assert first.state.levels == second.state.levels


def test_output_requires_explicit_flag_and_uses_canonical_name() -> None:
    args = build_parser().parse_args(["--output"])
    assert args.output == Path("THIRTY_DAYS_TRACE.md")


def test_thirty_daily_snapshots_have_finite_nonnegative_economy(audits) -> None:
    assert set(audits) == set(CORE_PROFILES)
    for audit in audits.values():
        assert len(audit.snapshots) == DAYS
        assert audit.state.minute == DAYS * 1440
        assert_finite_nonnegative(audit)
        assert all(math.isfinite(event.cost) and event.cost >= 0 for event in audit.events)


def test_daily_and_absent_unlock_future_by_day_30(audits) -> None:
    for profile in ("daily", "absent"):
        assert "future" in audits[profile].era_first_minutes
        assert audits[profile].era_first_minutes["future"] <= DAYS * 1440


def test_daily_visits_buy_until_nothing_affordable(audits) -> None:
    daily = audits["daily"]
    assert len(daily.visits) == DAYS
    assert all(item.stop_reason in {"矿币不足", "无可建科技"} for item in daily.visits)
    assert [item.purchased_levels for item in daily.visits] == [
        item.manual_levels for item in daily.snapshots
    ]


def test_d11_plus_manual_opportunity_is_at_most_twelve_per_day(opportunity) -> None:
    assert len(opportunity) == 5 * 4
    assert {seed for seed, _ in opportunity} == set(DEFAULT_SEEDS)
    assert {route for _, route in opportunity} == set(
        GAME_DATA["strategy"]["routeVariants"]
    )
    assert all(len(counts) == DAYS for counts in opportunity.values())
    assert max(max(counts[10:]) for counts in opportunity.values()) <= 12


def test_no_new_technology_first_purchase_gap_exceeds_72_hours(audits) -> None:
    for profile in ("daily", "absent"):
        assert audits[profile].longest_first_purchase_gap.minutes <= 72 * 60
        assert audits[profile].longest_first_purchase_gap_d11_plus.minutes <= 72 * 60


@pytest.mark.parametrize("profile", CORE_PROFILES)
def test_python_and_web_match_for_all_30_days(audits, profile: str) -> None:
    assert_web_parity(audits[profile])


def test_trace_contains_required_windows_milestones_gaps_and_optional_matrix(
    audits,
    opportunity,
) -> None:
    markdown = render_markdown(audits, 42, "balanced", opportunity)
    assert "D11-D20" in markdown
    assert "D21-D30" in markdown
    assert "时代首次到达" in markdown
    assert "D11-D30（含边界与末尾）" in markdown
    assert "每日一次画像买到买不起" in markdown
    assert "五 seed / 四路线 opportunity 次数" in markdown
    assert "## 验收" in markdown


def test_opportunity_over_twelve_is_an_acceptance_failure(audits) -> None:
    opportunity = {(42, "balanced"): [0] * 10 + [13] + [0] * 19}
    failures = acceptance_failures(audits, opportunity)
    assert failures == [
        "seed=42 route=balanced D11+ manual opportunity max is 13 (>12)"
    ]
    markdown = render_markdown(audits, 42, "balanced", opportunity)
    assert "- FAIL: seed=42 route=balanced D11+ manual opportunity max is 13 (>12)" in markdown


def test_main_writes_failure_report_then_exits_one(
    audits,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "failed.md"
    opportunity = {(42, "balanced"): [0] * 10 + [13] + [0] * 19}
    monkeypatch.setattr(thirty_days, "run_core_audits", lambda *_: audits)
    monkeypatch.setattr(thirty_days, "assert_web_parity", lambda *_: None)
    monkeypatch.setattr(
        thirty_days,
        "run_opportunity_matrix",
        lambda *_: opportunity,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["s2_thirty_days.py", "--matrix", "--output", str(output)],
    )

    with pytest.raises(SystemExit) as exc_info:
        thirty_days.main()

    assert exc_info.value.code == 1
    assert output.exists()
    assert "manual opportunity max is 13 (>12)" in output.read_text(encoding="utf-8")
