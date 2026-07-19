#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
星穹矿脉 · 数值自玩模拟器 v5.2
==============================
定案：
  - 定义 ∞ = 10^308
  - 每日升级硬顶 3（禁止第 4 次）
  - 破界：本轮进度全部清空，仅保留猫能/星核
  - 展示：科学计数；外壳是挖矿，内核是指数增长
  - 目标：约 30 天 / 约 60 次升级通关（逃离星穹）

数学骨架：
  Δ log10(S) = r · Δt
  r = (r0 + r1 · eff(P_run + P_flat(C,K))) · M(C,K)
  M = (1+C)^ρc · (1+K)^ρk
  破界奖励与过冲脱钩（触顶即封顶），避免雪崩。

用法：
  python simulate.py
  python simulate.py --verbose
  python simulate.py --tune --trials 300
  python simulate.py --apply-best   # 把 best_config 写回默认 Config 预览
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def fmt_sci(log_v: float, inf_log: float) -> str:
    """Scientific notation display; ∞ at threshold."""
    if log_v < -12:
        return "0"
    if log_v >= inf_log - 1e-9:
        return "∞"
    if log_v < 6:
        return f"{10 ** log_v:.3g}"
    exp = int(math.floor(log_v))
    mant = 10 ** (log_v - exp)
    return f"{mant:.3f}e{exp}"


@dataclass
class Config:
    # Defined infinity: 10^308
    inf_log10: float = 308.0

    # Mining channels (look like mining, act as power sources)
    n_dims: int = 5
    dim_names: tuple = ("拾星爪", "猫钻机", "采矿站", "跃迁拖车", "星锚井架")
    # 已调参：greedy 约 30 天 / 60 次升级 / 破界日 [16,25,30]
    dim_power: tuple = (2.26, 1.26, 2.19, 3.79, 8.93)
    dim_base_cost_log: tuple = (3.28, 2.37, 3.41, 5.19, 7.45)
    dim_cost_growth: float = 0.35

    # Run-local keystones (reset on prestige)
    boost_power: float = 1.05
    boost_base_cost_log: float = 14.1
    boost_cost_growth: float = 7.0
    max_boost: int = 2

    speed_power: float = 1.45
    speed_base_cost_log: float = 11.9
    speed_cost_growth: float = 5.15
    max_speed: int = 1

    # Growth: Δlog10(S) per day = r
    # r = (r0 + r1 * eff(P_run + flat)) * M_prestige
    r0: float = 0.284
    r1: float = 0.48
    soft_cap: float = 110.0
    soft_mix: float = 0.11

    # Prestige permanent multipliers (kept across full reset)
    rho_c: float = 0.36
    rho_k: float = 0.32
    cat_power_flat: float = 0.76
    core_power_flat: float = 1.76

    # 破界猫能：与过冲脱钩，按破界序号温和递增
    ip_alpha: float = 2.61
    ip_beta: float = 0.69
    core_base: float = 2.0
    core_log_div: float = 4.0
    cores_to_win: float = 3.0
    min_prestiges_to_win: int = 3

    start_power: float = 0.40
    start_stardust_log: float = 0.0
    upgrades_per_day: int = 3  # HARD CAP
    unlock_need: int = 1
    same_day_dimish: bool = True


@dataclass
class State:
    day: int = 0
    stardust_log: float = 0.0
    raw_power: float = 0.7  # this-run only
    dim_bought: list = field(default_factory=list)
    boost_level: int = 0
    speed_level: int = 0
    cat_energy: float = 0.0
    star_cores: float = 0.0
    total_prestiges: int = 0
    upgrades_today: int = 0
    total_upgrades: int = 0
    best_log: float = 0.0
    prestige_days: list = field(default_factory=list)
    win: bool = False
    win_day: int | None = None
    shaft_resets: int = 0

    def init(self, cfg: Config) -> None:
        self.dim_bought = [0] * cfg.n_dims
        self.raw_power = cfg.start_power
        self.stardust_log = cfg.start_stardust_log
        self.boost_level = 0
        self.speed_level = 0
        self.best_log = self.stardust_log


def prestige_mult(state: State, cfg: Config) -> float:
    return ((1.0 + state.cat_energy) ** cfg.rho_c) * ((1.0 + state.star_cores) ** cfg.rho_k)


def prestige_flat_power(state: State, cfg: Config) -> float:
    # sqrt growth → 边际递减，呼应「极限 e」的平坦感
    c = cfg.cat_power_flat * math.sqrt(state.cat_energy) if state.cat_energy > 0 else 0.0
    k = cfg.core_power_flat * math.sqrt(state.star_cores) if state.star_cores > 0 else 0.0
    return c + k


def effective_run_power(state: State, cfg: Config) -> float:
    raw = max(0.0, state.raw_power + prestige_flat_power(state, cfg))
    linear = raw
    soft = cfg.soft_cap * math.log1p(raw / max(1e-9, cfg.soft_cap))
    return (1.0 - cfg.soft_mix) * linear + cfg.soft_mix * soft


def r_per_day(state: State, cfg: Config) -> float:
    base = cfg.r0 + cfg.r1 * effective_run_power(state, cfg)
    return base * prestige_mult(state, cfg)


def integrate(state: State, cfg: Config, day_fraction: float) -> None:
    state.stardust_log += r_per_day(state, cfg) * day_fraction
    # 触顶封顶：禁止靠巨大 r 过冲刷破界奖励
    if state.stardust_log > cfg.inf_log10:
        state.stardust_log = cfg.inf_log10
    state.best_log = max(state.best_log, state.stardust_log)


def dim_cost_log(cfg: Config, dim: int, bought: int) -> float:
    return cfg.dim_base_cost_log[dim] + bought * cfg.dim_cost_growth


def boost_cost_log(cfg: Config, level: int) -> float:
    return cfg.boost_base_cost_log + level * cfg.boost_cost_growth


def speed_cost_log(cfg: Config, level: int) -> float:
    return cfg.speed_base_cost_log + level * cfg.speed_cost_growth


def can_afford(state: State, cost_log: float) -> bool:
    return state.stardust_log + 1e-12 >= cost_log


def pay(state: State, cost_log: float) -> None:
    if state.stardust_log - cost_log > 10:
        return
    diff = cost_log - state.stardust_log
    factor = 1.0 - 10.0**diff
    if factor <= 1e-15:
        state.stardust_log = max(0.0, cost_log - 2.0)
        return
    state.stardust_log += math.log10(factor)


def unlocked(state: State, cfg: Config, dim: int) -> bool:
    if dim == 0:
        return True
    return state.dim_bought[dim - 1] >= cfg.unlock_need


@dataclass
class Action:
    kind: str
    dim: int = -1
    cost_log: float = 0.0
    power_gain: float = 0.0
    score: float = 0.0
    label: str = ""


def list_actions(state: State, cfg: Config) -> list[Action]:
    actions: list[Action] = []
    day_weight = 1.0 / (1.0 + state.upgrades_today) if cfg.same_day_dimish else 1.0

    for d in range(cfg.n_dims):
        if not unlocked(state, cfg, d):
            continue
        cost = dim_cost_log(cfg, d, state.dim_bought[d])
        if not can_afford(state, cost):
            continue
        gain = cfg.dim_power[d]
        score = (gain / max(0.3, 0.20 * cost + 0.4)) * day_weight
        if state.dim_bought[d] == 0:
            score += (1.5 + 0.45 * d) * day_weight
        actions.append(
            Action("dim", d, cost, gain, score, f"{cfg.dim_names[d]}#{state.dim_bought[d]+1}")
        )

    if state.boost_level < cfg.max_boost:
        cost = boost_cost_log(cfg, state.boost_level)
        if can_afford(state, cost):
            gain = cfg.boost_power
            score = (gain / max(0.3, 0.20 * cost + 0.4)) * day_weight
            actions.append(
                Action("boost", -1, cost, gain, score, f"加固钻头#{state.boost_level+1}")
            )

    if state.speed_level < cfg.max_speed:
        cost = speed_cost_log(cfg, state.speed_level)
        if can_afford(state, cost):
            gain = cfg.speed_power
            score = (gain / max(0.3, 0.20 * cost + 0.4)) * day_weight
            actions.append(
                Action("speed", -1, cost, gain, score, f"工时提速#{state.speed_level+1}")
            )
    return actions


def apply_action(state: State, cfg: Config, act: Action) -> None:
    if state.upgrades_today >= cfg.upgrades_per_day:
        raise RuntimeError("HARD CAP: daily upgrades exhausted")
    pay(state, act.cost_log)
    if act.kind == "dim":
        state.dim_bought[act.dim] += 1
    elif act.kind == "boost":
        state.boost_level += 1
    elif act.kind == "speed":
        state.speed_level += 1
    state.raw_power += act.power_gain
    state.total_upgrades += 1
    state.upgrades_today += 1


def can_prestige(state: State, cfg: Config) -> bool:
    return state.stardust_log >= cfg.inf_log10 - 1e-12


def prestige_gain_c(state: State, cfg: Config) -> float:
    """与过冲脱钩：按破界序号温和给猫能。"""
    idx = state.total_prestiges  # 0 = 首次破界
    return max(1.0, math.floor(cfg.ip_alpha + cfg.ip_beta * idx + 1e-9))


def prestige_gain_k(state: State, cfg: Config, c_gain: float) -> float:
    """第二次破界起给星核；数量温和。"""
    if state.total_prestiges < 1:
        return 0.0
    # core_base + 微弱 log 项，避免 C 雪球直接抬 K
    extra = cfg.core_base + math.floor(
        math.log10(1.0 + state.cat_energy + c_gain) / max(0.5, cfg.core_log_div)
    )
    return max(1.0, float(extra))


def apply_prestige(state: State, cfg: Config) -> None:
    """Full shaft collapse: back to the beginning, keep only C/K memory."""
    c_gain = prestige_gain_c(state, cfg)
    k_gain = prestige_gain_k(state, cfg, c_gain)
    state.cat_energy += c_gain
    state.star_cores += k_gain
    state.total_prestiges += 1
    state.prestige_days.append(state.day)
    state.shaft_resets += 1

    # FULL RESET of this-run mining progress
    state.stardust_log = cfg.start_stardust_log
    state.raw_power = cfg.start_power
    state.dim_bought = [0] * cfg.n_dims
    state.boost_level = 0
    state.speed_level = 0

    if (
        state.star_cores >= cfg.cores_to_win
        and state.total_prestiges >= cfg.min_prestiges_to_win
    ):
        state.win = True
        state.win_day = state.day


@dataclass
class SimResult:
    win: bool
    win_day: int | None
    total_upgrades: int
    total_prestiges: int
    star_cores: float
    cat_energy: float
    best_log: float
    prestige_days: list
    daily: list
    cfg: dict
    final_raw_power: float = 0.0


def simulate(
    cfg: Config | None = None,
    max_days: int = 40,
    seed: int = 0,
    verbose: bool = False,
    strategy: str = "greedy",
) -> SimResult:
    cfg = cfg or Config()
    assert cfg.upgrades_per_day == 3 or cfg.upgrades_per_day > 0
    rng = random.Random(seed)
    st = State()
    st.init(cfg)
    daily = []

    for day in range(1, max_days + 1):
        st.day = day
        st.upgrades_today = 0
        prestiged_today = False

        for _ in range(3):
            integrate(st, cfg, 0.30)
            # prestige free; 同日可破界一次（避免半日连环破界）
            if not st.win and not prestiged_today and can_prestige(st, cfg):
                apply_prestige(st, cfg)
                prestiged_today = True
                if verbose:
                    print(
                        f"  [D{day}] 破界排空 矿场归零 | C={st.cat_energy:.0f} "
                        f"K={st.star_cores:.0f} M={prestige_mult(st, cfg):.2f} "
                        f"r={r_per_day(st, cfg):.2f}"
                    )
                if st.win:
                    break
            # hard-capped upgrade
            if st.upgrades_today < cfg.upgrades_per_day and not st.win:
                acts = list_actions(st, cfg)
                if acts:
                    acts.sort(key=lambda a: a.score, reverse=True)
                    chosen = (
                        acts[0]
                        if strategy == "greedy"
                        else rng.choice(acts[: min(3, len(acts))])
                    )
                    apply_action(st, cfg, chosen)
                    if verbose:
                        depth_pct = min(100.0, 100.0 * st.stardust_log / cfg.inf_log10)
                        print(
                            f"  [D{day}] 施工 {chosen.label:16s} "
                            f"产量={fmt_sci(st.stardust_log, cfg.inf_log10):>12s} "
                            f"深度={depth_pct:5.1f}% P={st.raw_power:.1f} "
                            f"r/日={r_per_day(st, cfg):.2f}"
                        )
            integrate(st, cfg, 0.033)
            if st.win:
                break

        if not st.win and not prestiged_today and can_prestige(st, cfg):
            apply_prestige(st, cfg)
            prestiged_today = True
            if verbose:
                print(
                    f"  [D{day}] 日终破界 | C={st.cat_energy:.0f} K={st.star_cores:.0f}"
                )

        depth_pct = min(100.0, 100.0 * max(0.0, st.stardust_log) / cfg.inf_log10)
        daily.append(
            {
                "day": day,
                "S": fmt_sci(st.stardust_log, cfg.inf_log10),
                "logS": st.stardust_log,
                "depth_pct": depth_pct,
                "C": st.cat_energy,
                "K": st.star_cores,
                "up": st.total_upgrades,
                "pr": st.total_prestiges,
                "rawP": st.raw_power,
                "r": r_per_day(st, cfg),
                "M": prestige_mult(st, cfg),
                "boost": st.boost_level,
                "speed": st.speed_level,
                "bought": st.dim_bought[:],
            }
        )
        if verbose:
            print(
                f"Day {day:02d} | 产量={fmt_sci(st.stardust_log, cfg.inf_log10):>12s} "
                f"log={st.stardust_log:7.2f} 深度={depth_pct:5.1f}% "
                f"C={st.cat_energy:6.1f} K={st.star_cores:4.1f} "
                f"up={st.total_upgrades:3d}/{cfg.upgrades_per_day}日硬顶 "
                f"pr={st.total_prestiges} r={r_per_day(st, cfg):.2f}"
            )
        if st.win:
            st.win_day = st.win_day or day
            break

    return SimResult(
        win=st.win,
        win_day=st.win_day,
        total_upgrades=st.total_upgrades,
        total_prestiges=st.total_prestiges,
        star_cores=st.star_cores,
        cat_energy=st.cat_energy,
        best_log=st.best_log,
        prestige_days=st.prestige_days[:],
        daily=daily,
        cfg=asdict(cfg),
        final_raw_power=st.raw_power,
    )


def score_result(res: SimResult, target_day: float = 30.0, target_up: float = 60.0) -> float:
    if not res.win:
        return (
            900.0
            + max(0.0, 320.0 - res.best_log) * 0.5
            + max(0.0, 3 - res.total_prestiges) * 60
            + max(0.0, 4.0 - res.star_cores) * 25
            + max(0.0, target_up - res.total_upgrades) * 0.05
            + max(0.0, target_day - (res.daily[-1]["day"] if res.daily else 0)) * 0.5
        )
    day_err = abs((res.win_day or 99) - target_day)
    up_err = abs(res.total_upgrades - target_up)
    pen = 0.0
    wd = res.win_day or 99
    if wd < 26:
        pen += (26 - wd) * 4
    if wd > 34:
        pen += (wd - 34) * 4
    if res.total_upgrades < 52:
        pen += (52 - res.total_upgrades) * 1.2
    if res.total_upgrades > 72:
        pen += (res.total_upgrades - 72) * 1.2
    if res.total_prestiges < 3:
        pen += 25
    if res.total_prestiges > 6:
        pen += (res.total_prestiges - 6) * 5
    # 首破宜在 10~16 天
    if res.prestige_days:
        first = res.prestige_days[0]
        if first < 9:
            pen += (9 - first) * 3
        if first > 16:
            pen += (first - 16) * 2
    return day_err * 3.5 + up_err * 1.4 + pen


def mutate_config(rng: random.Random, base: Config | None = None) -> Config:
    b = base or Config()
    # 在基线附近扰动，比纯随机更容易落到可玩区
    def j(x: float, lo: float, hi: float, scale: float = 0.15) -> float:
        return max(lo, min(hi, x * rng.uniform(1 - scale, 1 + scale)))

    dim_power = tuple(
        max(0.4, p * rng.uniform(0.85, 1.18)) for p in b.dim_power
    )
    dim_cost = tuple(
        max(0.15, c + rng.uniform(-0.35, 0.45)) for c in b.dim_base_cost_log
    )
    return Config(
        inf_log10=308.0,
        upgrades_per_day=3,
        dim_power=dim_power,
        dim_base_cost_log=dim_cost,
        dim_cost_growth=j(b.dim_cost_growth, 0.32, 0.62, 0.2),
        boost_power=j(b.boost_power, 1.0, 2.4, 0.2),
        boost_base_cost_log=j(b.boost_base_cost_log, 8.0, 22.0, 0.2),
        boost_cost_growth=j(b.boost_cost_growth, 3.0, 7.0, 0.2),
        max_boost=rng.choice([2, 3, 3, 4]),
        speed_power=j(b.speed_power, 0.8, 1.8, 0.2),
        speed_base_cost_log=j(b.speed_base_cost_log, 10.0, 24.0, 0.2),
        speed_cost_growth=j(b.speed_cost_growth, 3.5, 7.5, 0.2),
        max_speed=rng.choice([1, 2, 2, 3]),
        r0=j(b.r0, 0.22, 0.70, 0.22),
        r1=j(b.r1, 0.18, 0.48, 0.22),
        soft_cap=j(b.soft_cap, 70.0, 180.0, 0.2),
        soft_mix=max(0.0, min(0.35, b.soft_mix + rng.uniform(-0.08, 0.08))),
        rho_c=j(b.rho_c, 0.22, 0.65, 0.22),
        rho_k=j(b.rho_k, 0.12, 0.48, 0.22),
        cat_power_flat=j(b.cat_power_flat, 0.6, 2.5, 0.25),
        core_power_flat=j(b.core_power_flat, 0.8, 3.5, 0.25),
        ip_alpha=j(b.ip_alpha, 2.0, 5.0, 0.2),
        ip_beta=j(b.ip_beta, 0.6, 2.0, 0.25),
        core_base=rng.choice([1.0, 1.0, 1.0, 2.0]),
        core_log_div=j(b.core_log_div, 1.8, 4.0, 0.2),
        cores_to_win=rng.choice([3.0, 4.0, 4.0, 5.0]),
        min_prestiges_to_win=rng.choice([3, 3, 3, 4]),
        start_power=j(b.start_power, 0.4, 1.2, 0.2),
    )


def tune(
    target_day: float = 30.0,
    target_up: float = 60.0,
    trials: int = 300,
    seed: int = 0,
) -> tuple[Config, SimResult]:
    rng = random.Random(seed)
    best_cfg = Config()
    best_res = simulate(best_cfg, max_days=55, seed=0)
    best_score = score_result(best_res, target_day, target_up)
    print(
        f"tune start score={best_score:.2f} win={best_res.win} day={best_res.win_day} "
        f"up={best_res.total_upgrades} pr={best_res.total_prestiges} "
        f"K={best_res.star_cores} first_pr={best_res.prestige_days[:1]} "
        f"best_log={best_res.best_log:.1f}"
    )

    # 阶段性：先广撒，再围着最优细调
    for i in range(trials):
        if i < trials // 3:
            cfg = mutate_config(rng, Config())
        else:
            cfg = mutate_config(rng, best_cfg)

        scores = []
        results = []
        for s in range(3):
            res = simulate(cfg, max_days=55, seed=s)
            scores.append(score_result(res, target_day, target_up))
            results.append(res)
        sc = statistics.mean(scores)
        results.sort(
            key=lambda r: (not r.win, r.win_day or 99, abs(r.total_upgrades - target_up))
        )
        res0 = results[0]
        if sc < best_score:
            best_score = sc
            best_cfg = cfg
            best_res = res0
            print(
                f"tune[{i:03d}] score={sc:.2f} win={res0.win} day={res0.win_day} "
                f"up={res0.total_upgrades} pr={res0.total_prestiges} "
                f"K={res0.star_cores:.0f} pr_days={res0.prestige_days} "
                f"r0={cfg.r0:.2f} r1={cfg.r1:.2f} rho_c={cfg.rho_c:.2f} "
                f"cores_to_win={cfg.cores_to_win}"
            )
    return best_cfg, best_res


def write_report(path: Path, cfg: Config, res: SimResult, title: str) -> None:
    lines = [
        f"# 星穹矿脉 · {title}",
        "",
        "> 由 `demo/simulate.py` v5.2 生成 · 定案：∞=1e308 · 日升3硬顶 · 破界全重置 · 挖矿皮",
        "",
        "## 结果摘要",
        "",
        "| 项 | 值 |",
        "|----|----|",
        f"| 通关（逃离星穹） | {'是' if res.win else '否'} |",
        f"| 通关日 | {res.win_day} |",
        f"| 总升级次数 | {res.total_upgrades} |",
        f"| 破界次数 | {res.total_prestiges} |",
        f"| 破界日 | {res.prestige_days} |",
        f"| 猫能 C | {res.cat_energy:.2f} |",
        f"| 星核 K | {res.star_cores:.2f} |",
        f"| 历史最高 log10(产量) | {res.best_log:.2f} |",
        f"| 是否摸到 ∞(308) | {'是' if res.best_log >= cfg.inf_log10 - 1e-6 else '否'} |",
        "",
        "## 定案核对",
        "",
        "| 规则 | 值 |",
        "|------|----|",
        f"| 定义 ∞ | 10^{int(cfg.inf_log10)} |",
        f"| 日升级硬顶 | {cfg.upgrades_per_day} |",
        "| 第4次升级 | 禁止 |",
        "| 破界 | 本轮矿场全清空，仅留 C/K |",
        "| 展示 | 科学计数 / ∞ |",
        "| 破界奖励 | 与过冲脱钩，按破界序号给 C；二次起给 K |",
        "| 同日连环破界 | 禁止（每日最多破界 1 次） |",
        "",
        "## 数学人格",
        "",
        "1. **指数挂机**：`Δ log10(S) = r · Δt`，展示科学计数狂飙。",
        "2. **功率近线性 + softcap**：`eff` 混合线性与 `cap·ln(1+raw/cap)`。",
        "3. **同日边际**：评分 × `1/(1+今日已升级)`，呼应复利极限 e。",
        "4. **永久倍率温和**：`M=(1+C)^ρc·(1+K)^ρk`，flat 用平方根边际递减。",
        "5. **定义无穷**：`log10 S ≥ 308` 可破界；破界后全重置。",
        "6. **通关**：星核 ≥ 阈值 且 破界次数 ≥ min_prestiges → 逃离星穹。",
        "",
        "## 关键参数",
        "",
        "```",
    ]
    for k, v in asdict(cfg).items():
        lines.append(f"{k}: {v}")
    lines += [
        "```",
        "",
        "## 每日矿场轨迹",
        "",
        "| Day | 产量 | logS | 深度% | rawP | r/day | M | C | K | 升级 | 破界 |",
        "|----:|------|-----:|------:|-----:|------:|--:|--:|--:|-----:|-----:|",
    ]
    for row in res.daily:
        lines.append(
            f"| {row['day']} | {row['S']} | {row['logS']:.2f} | {row['depth_pct']:.1f} | "
            f"{row['rawP']:.2f} | {row['r']:.2f} | {row['M']:.2f} | {row['C']:.1f} | "
            f"{row['K']:.1f} | {row['up']} | {row['pr']} |"
        )
    lines += [
        "",
        "## 对照目标",
        "",
        "| 目标 | 期望 | 本次 |",
        "|------|------|------|",
        f"| 通关天数 | ~30 | {res.win_day} |",
        f"| 升级次数 | ~60 | {res.total_upgrades} |",
        f"| 日升级上限 | 3 硬顶 | {cfg.upgrades_per_day} |",
        f"| ∞ | 1e308 | 10^{int(cfg.inf_log10)} |",
        f"| 首破日 | 10~16 | {res.prestige_days[0] if res.prestige_days else '—'} |",
        "",
        "## 皮与骨",
        "",
        "- 皮：产量/深度%/钻头/井架 —— 读起来像挖矿。",
        "- 骨：Δlog10(S)=r·Δt，破界轮回，科学计数冲向 1e308。",
        "- 反差：按钮叫「加固钻头」，数值却在玩弄定义无穷。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote report: {path}")


def config_from_best_file(path: Path) -> Config | None:
    if not path.exists():
        return None
    raw = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        try:
            raw[k] = eval(v, {"__builtins__": {}})  # trusted local file
        except Exception:
            raw[k] = v
    known = {f.name for f in Config.__dataclass_fields__.values()}  # type: ignore
    kwargs = {k: raw[k] for k in raw if k in known}
    return Config(**kwargs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="星穹矿脉 demo v5.2")
    p.add_argument("--days", type=int, default=45)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--tune", action="store_true")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--target-day", type=float, default=30.0)
    p.add_argument("--target-up", type=float, default=60.0)
    p.add_argument("--from-best", action="store_true", help="load demo/best_config.txt")
    args = p.parse_args(argv)

    out_dir = Path(__file__).resolve().parents[1]
    report_path = out_dir / "BALANCE_REPORT.md"
    demo_dir = Path(__file__).resolve().parent
    best_path = demo_dir / "best_config.txt"

    if args.tune:
        print("Tuning for ∞=1e308, full reset, hard cap 3, ~30d/~60up...")
        cfg, res = tune(args.target_day, args.target_up, trials=args.trials, seed=args.seed)
        print("---- BEST ----")
        print(
            f"win={res.win} day={res.win_day} up={res.total_upgrades} "
            f"pr={res.total_prestiges} C={res.cat_energy} K={res.star_cores} "
            f"pr_days={res.prestige_days} best_log={res.best_log:.1f}"
        )
        res2 = simulate(cfg, max_days=max(args.days, 55), seed=0, verbose=args.verbose)
        write_report(report_path, cfg, res2, "平衡报告（自动调参 · v5.2）")
        best_path.write_text(
            "\n".join(f"{k}={v}" for k, v in asdict(cfg).items()), encoding="utf-8"
        )
        print(f"Wrote {best_path}")
        return 0

    if args.from_best:
        cfg = config_from_best_file(best_path)
        if cfg is None:
            print("best_config.txt not found")
            return 1
    else:
        cfg = Config()

    res = simulate(cfg, max_days=args.days, seed=args.seed, verbose=args.verbose)
    print(
        f"win={res.win} day={res.win_day} up={res.total_upgrades} "
        f"pr={res.total_prestiges} C={res.cat_energy:.1f} K={res.star_cores:.1f} "
        f"pr_days={res.prestige_days} best_log={res.best_log:.2f}"
    )
    title = "平衡报告（best_config · v5.2）" if args.from_best else "平衡报告（默认参数 · v5.2）"
    write_report(report_path, cfg, res, title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
