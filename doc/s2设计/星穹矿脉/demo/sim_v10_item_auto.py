# -*- coding: utf-8 -*-
"""
S2 v10 · 每项单独购买自动 · 仅开关 · 修深度结算
================================================

用户反馈
--------
1. 一开自动所有升级迅速买完 → 仍挖不穿星球
2. 自动不需要多段 burst，只要开关
3. 每个升级需 **单独购买** 自动能力，再开关

规则
----
- 手动：每天 3 次（点升级本体）
- 每项有：
    - 本体等级升级（手动 3/日 或 自动）
    - 自动解锁：单独买一次 `auto_unlock[key]`（花费矿币，手动也占 3 次？默认 **不占** 手动额度，算商店另一按钮；或占手动——用户说「单独购买」，按 **占手动次数** 更克制）
  这里定案：**购买自动解锁 也算手动操作（占 3 次）**，避免一天全开自动。
- 总自动总闸：可选，简化为「任意项解锁后该项可独立开关」
- 自动触发：产出结算后，对 **已解锁且开关开** 的项各尝试买 1 级（每波每项最多 1 级，避免一帧扫光；一天多波产出）

深度修复
--------
禁止把 tick 截断成 2e6。
日产出直接用：
  day_depth_log = log10(mining_sec/interval) + depth_tick_log
  day_coin_log  = log10(mining_sec/interval) + coins_tick_log
满配必须 day_depth ≥ 310，且模拟必须通关。
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INF_LOG = 308.0
CORE_LOG = 306.0
BASE_INTERVAL = 8.0
BASE_MINING_SEC = 1500.0
BASE_Q = 1.0
BASE_DEPTH = 1.0
MANUAL_PER_DAY = 3
START_COINS = 80.0
MAX_DAYS = 40
WIN_LO, WIN_HI = 26, 34
# 一天几次产出结算（每次后跑一轮「每项自动买 1 级」）
PULSES = 6

PRICE = {"N": 1.0, "R": 2.0, "SR": 4.0, "SSR": 8.0, "UR": 16.0}


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    kind: str
    mult: float
    base: float
    growth: float
    max_lv: int
    bump: str
    # 自动解锁价格：单独购买
    auto_base: float
    per: float = 0.0
    qty_m: float = 1.0
    rate_m: float = 1.0
    depth_m: float = 1.0


def build_shop() -> List[Item]:
    # 满配 day_depth 必须明显 > 306
    # 深度链：blast×3, strata×3, brace×1.5, canteen depth
    # 速度链：pick×2, belt×1.5, chrono/2, hours×2
    return [
        Item("blast", "浅层爆破", "depth", 3.0, 15, 2.4, 220, "深度 ×3", auto_base=200),
        Item("strata", "岩层许可", "strata", 3.0, 20, 2.45, 200, "地层 ×3", auto_base=220),
        Item("cart", "矿车车厢", "qty", 3.0, 16, 2.4, 220, "产量 ×3", auto_base=200),
        Item("pick", "镐速齿轮", "rate", 2.0, 12, 2.25, 200, "速度 ×2", auto_base=180),
        Item("sorter", "分拣爪", "value", 2.0, 18, 2.35, 180, "售价 ×2", auto_base=210),
        Item("market", "矿市特许", "market", 2.0, 24, 2.4, 160, "市价 ×2", auto_base=230),
        Item("shift", "加班班次", "hours", 2.0, 22, 2.3, 120, "工时 ×2", auto_base=190),
        Item("chrono", "时序齿轮", "interval", 2.0, 24, 2.3, 120, "间隔 /2", auto_base=190),
        Item("rebate", "财税返还", "rebate", 2.0, 28, 2.35, 120, "结算 ×2", auto_base=240),
        Item("belt", "星尘传送带", "rate", 1.5, 32, 2.3, 140, "速度 ×1.5", auto_base=160),
        Item("brace", "巷道支架", "depth", 1.5, 30, 2.3, 140, "深度 ×1.5", auto_base=160),
        Item("lamp", "巷道工灯", "qty", 1.5, 30, 2.3, 140, "产量 ×1.5", auto_base=160),
        Item("polish", "虹核抛光", "refine", 2.0, 45, 2.55, 50, "精矿 ×2", auto_base=260),
        Item("drill", "猫钻头", "rare", 1.0, 26, 2.35, 35, "稀有↑", auto_base=150, per=1.0),
        Item("whisker", "猫须探针", "luck", 1.0, 28, 2.4, 30, "幸运↑", auto_base=150, per=1.0),
        Item(
            "canteen", "工地罐头铺", "hybrid", 1.25, 35, 2.35, 100, "全属性 ×1.25",
            auto_base=250, qty_m=1.25, rate_m=1.25, depth_m=1.25,
        ),
    ]


SHOP: List[Item] = []
SHOP_MAP: Dict[str, Item] = {}


def clog(it: Item, lv: int) -> float:
    return math.log10(it.base) + lv * math.log10(it.growth)


def auto_unlock_cost_log(it: Item) -> float:
    return math.log10(it.auto_base)


def add_log(a: float, b: float) -> float:
    if not math.isfinite(b):
        return a
    if not math.isfinite(a):
        return b
    m = max(a, b)
    if a < m - 60:
        return b
    if b < m - 60:
        return a
    return m + math.log10(10 ** (a - m) + 10 ** (b - m))


def sub_log(a: float, c: float) -> float:
    if not math.isfinite(c):
        return a
    if not math.isfinite(a) or a + 1e-12 < c:
        return float("-inf")
    if abs(a - c) < 1e-12:
        return float("-inf")
    if a > c + 60:
        return a
    return a + math.log10(1.0 - 10 ** (c - a))


def can_aff(coins: float, c: float, inf: bool) -> bool:
    if inf:
        return True
    return math.isfinite(c) and math.isfinite(coins) and coins + 1e-12 >= c


def fmt(x: float) -> str:
    if not math.isfinite(x) or x < -12:
        return "0"
    if x >= INF_LOG - 1e-9:
        return "∞"
    if x < 6:
        return f"{10 ** x:.3g}"
    e = int(math.floor(x + 1e-12))
    return f"{10 ** (x - e):.2f}e{e}"


def rarity_probs(drill: int, luck: int) -> Dict[str, float]:
    t = min(1.0, drill / 35.0)
    lk = min(1.0, luck / 30.0)
    w = {
        "N": max(1e-9, 0.68 - 0.50 * t - 0.06 * lk),
        "R": max(1e-9, 0.20 - 0.04 * t),
        "SR": max(1e-9, 0.07 + 0.16 * t + 0.02 * lk),
        "SSR": max(1e-9, 0.03 + 0.22 * t + 0.04 * lk),
        "UR": max(1e-9, 0.02 + 0.16 * t + 0.05 * lk),
    }
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


@dataclass
class State:
    day: int = 1
    coins_log: float = float("-inf")
    depth_log: float = float("-inf")
    lv: Dict[str, int] = field(default_factory=dict)
    # 每项是否已购买自动能力
    auto_bought: Dict[str, bool] = field(default_factory=dict)
    # 每项开关（仅已购买时有效）
    auto_on: Dict[str, bool] = field(default_factory=dict)
    manual_today: int = 0
    total_up: int = 0
    total_manual: int = 0
    total_auto: int = 0
    total_auto_unlocks: int = 0
    hit_inf1: bool = False
    inf2: int = 0
    win: bool = False
    win_day: Optional[int] = None
    hist: List[dict] = field(default_factory=list)


def new_state() -> State:
    st = State(
        lv={i.key: 0 for i in SHOP},
        auto_bought={i.key: False for i in SHOP},
        auto_on={i.key: True for i in SHOP},  # 买了之后默认开
        coins_log=math.log10(START_COINS),
    )
    return st


def derive(st: State) -> dict:
    qty_l = rate_l = dep_l = val_l = ref_l = 0.0
    hours_l = interval_l = strata_l = market_l = rebate_l = 0.0
    drill = luck = 0
    for it in SHOP:
        lv = st.lv[it.key]
        if lv <= 0:
            continue
        if it.kind == "qty":
            qty_l += lv * math.log10(it.mult)
        elif it.kind == "rate":
            rate_l += lv * math.log10(it.mult)
        elif it.kind == "depth":
            dep_l += lv * math.log10(it.mult)
        elif it.kind == "value":
            val_l += lv * math.log10(it.mult)
        elif it.kind == "refine":
            ref_l += lv * math.log10(it.mult)
        elif it.kind == "hours":
            hours_l += lv * math.log10(it.mult)
        elif it.kind == "interval":
            interval_l += lv * math.log10(it.mult)
        elif it.kind == "strata":
            strata_l += lv * math.log10(it.mult)
        elif it.kind == "market":
            market_l += lv * math.log10(it.mult)
        elif it.kind == "rebate":
            rebate_l += lv * math.log10(it.mult)
        elif it.kind == "rare":
            drill += int(it.per * lv)
        elif it.kind == "luck":
            luck += int(it.per * lv)
        elif it.kind == "hybrid":
            qty_l += lv * math.log10(it.qty_m)
            rate_l += lv * math.log10(it.rate_m)
            dep_l += lv * math.log10(it.depth_m)

    # 用 log 避免 interval 下溢
    # interval = BASE / 10^(rate+chrono)
    # ticks = mining_sec / interval = mining_sec / BASE * 10^(rate+chrono)
    # log10(ticks) = log10(mining_sec) - log10(BASE) + rate + chrono
    # mining_sec = BASE_MS * 10^hours
    log_ticks = (
        math.log10(BASE_MINING_SEC) + hours_l
        - math.log10(BASE_INTERVAL)
        + rate_l + interval_l
    )
    depth_tick_l = math.log10(BASE_DEPTH) + dep_l + strata_l
    probs = rarity_probs(drill, luck)
    e_price = 0.0
    for r, p in probs.items():
        u = PRICE[r] * (10 ** val_l) * (10 ** market_l)
        if r in ("SSR", "UR"):
            u *= 10 ** ref_l
        e_price += p * u
    e_price = max(e_price, 1e-15)
    qty_tick_l = math.log10(BASE_Q) + qty_l
    coins_tick_l = qty_tick_l + math.log10(e_price) + rebate_l
    day_depth_l = log_ticks + depth_tick_l
    day_coin_l = log_ticks + coins_tick_l
    return {
        "log_ticks": log_ticks,
        "depth_tick_l": depth_tick_l,
        "coins_tick_l": coins_tick_l,
        "day_depth_l": day_depth_l,
        "day_coin_l": day_coin_l,
        "probs": probs,
        "rate_l": rate_l,
        "dep_l": dep_l,
        "hours_l": hours_l,
        "strata_l": strata_l,
    }


def max_day_depth() -> float:
    st = new_state()
    for it in SHOP:
        st.lv[it.key] = it.max_lv
    return derive(st)["day_depth_l"]


def apply_income(st: State, cg: float, dg: float) -> None:
    st.coins_log = add_log(st.coins_log, cg)
    st.depth_log = add_log(st.depth_log, dg)
    if math.isfinite(st.depth_log):
        st.depth_log = min(st.depth_log, CORE_LOG)
    if not st.hit_inf1 and math.isfinite(st.coins_log) and st.coins_log >= INF_LOG - 1e-9:
        st.hit_inf1 = True
        st.inf2 += 1
        st.coins_log = INF_LOG
    elif st.hit_inf1:
        st.coins_log = INF_LOG
    if (
        not st.win
        and math.isfinite(st.depth_log)
        and st.depth_log >= CORE_LOG - 1e-9
        and st.inf2 >= 1
    ):
        st.win = True
        st.win_day = st.day


def delta_log(st: State, it: Item) -> float:
    if it.kind in (
        "qty", "rate", "depth", "value", "hours", "interval",
        "strata", "market", "rebate",
    ):
        return math.log10(it.mult)
    if it.kind == "refine":
        phi = derive(st)["probs"]["SSR"] + derive(st)["probs"]["UR"]
        return math.log10(max(1.0001, 1.0 + phi * (it.mult - 1.0)))
    if it.kind == "hybrid":
        return math.log10(it.qty_m) + math.log10(it.rate_m) + 0.5 * math.log10(it.depth_m)
    if it.kind == "rare":
        return 0.03
    if it.kind == "luck":
        return 0.022
    return 0.01


def score_level(st: State, it: Item) -> float:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return -1e300
    c = max(clog(it, lv), 1e-12)
    s = delta_log(st, it) / c
    dlog = st.depth_log if math.isfinite(st.depth_log) else -5.0
    clog_ = st.coins_log if math.isfinite(st.coins_log) else -5.0
    depth_gap = CORE_LOG - dlog
    coin_gap = 0.0 if st.hit_inf1 else INF_LOG - clog_
    if depth_gap > 2:
        if it.kind in ("depth", "strata"):
            s *= 4.0 + min(3.0, depth_gap / 50.0)
        elif it.kind in ("rate", "interval", "hours"):
            s *= 3.2 + min(2.5, depth_gap / 70.0)
        elif it.kind == "hybrid":
            s *= 2.0
        elif it.kind in ("qty", "value", "market", "rebate"):
            s *= 1.0 + min(2.0, max(0.0, coin_gap) / 150.0)
        elif it.kind == "refine":
            s *= 0.45
    else:
        if it.kind in ("qty", "value", "market", "rebate", "rate"):
            s *= 3.0 + min(2.0, max(0.0, coin_gap) / 100.0)
        if it.kind in ("depth", "strata") and depth_gap < 0.5:
            s *= 0.2
    if it.kind in ("rare", "luck"):
        s *= 0.45 if st.total_up > 30 else 0.8
    return s


def score_unlock(st: State, it: Item) -> float:
    """买自动解锁的 ROI：深度缺口大时优先给深度/速度项买自动。"""
    if st.auto_bought[it.key]:
        return -1e300
    if st.lv[it.key] <= 0 and st.day < 3:
        # 还没点过本体，早期略降
        pass
    c = max(auto_unlock_cost_log(it), 1e-12)
    # 解锁价值 ≈ 未来省手动 × 该项强度
    base = delta_log(st, it) * 3.0 / c
    dlog = st.depth_log if math.isfinite(st.depth_log) else -5.0
    depth_gap = CORE_LOG - dlog
    if it.kind in ("depth", "strata", "rate", "interval", "hours"):
        base *= 1.5 + min(2.0, depth_gap / 100.0)
    # 已有一些自动后，继续铺开
    unlocked = sum(1 for v in st.auto_bought.values() if v)
    if unlocked == 0 and st.day >= 2:
        base *= 2.0
    return base


def best_manual_action(st: State) -> Optional[Tuple[str, str]]:
    """返回 (kind, key) kind in level|unlock"""
    best = None
    best_s = -1e300
    for it in SHOP:
        # 升级本体
        if st.lv[it.key] < it.max_lv and can_aff(st.coins_log, clog(it, st.lv[it.key]), st.hit_inf1):
            sc = score_level(st, it)
            if sc > best_s:
                best_s = sc
                best = ("level", it.key)
        # 买自动解锁（占手动）
        if not st.auto_bought[it.key] and can_aff(st.coins_log, auto_unlock_cost_log(it), st.hit_inf1):
            sc = score_unlock(st, it)
            if sc > best_s:
                best_s = sc
                best = ("unlock", it.key)
    return best


def do_level(st: State, key: str, source: str) -> bool:
    it = SHOP_MAP[key]
    lv = st.lv[key]
    if lv >= it.max_lv:
        return False
    if source == "manual":
        if st.manual_today >= MANUAL_PER_DAY:
            return False
    elif source == "auto":
        if not st.auto_bought.get(key) or not st.auto_on.get(key, True):
            return False
    else:
        return False
    c = clog(it, lv)
    if not can_aff(st.coins_log, c, st.hit_inf1):
        return False
    if not st.hit_inf1:
        st.coins_log = sub_log(st.coins_log, c)
    st.lv[key] = lv + 1
    st.total_up += 1
    if source == "manual":
        st.manual_today += 1
        st.total_manual += 1
    else:
        st.total_auto += 1
    return True


def do_unlock(st: State, key: str) -> bool:
    """购买自动能力，占手动次数。"""
    if st.auto_bought[key]:
        return False
    if st.manual_today >= MANUAL_PER_DAY:
        return False
    it = SHOP_MAP[key]
    c = auto_unlock_cost_log(it)
    if not can_aff(st.coins_log, c, st.hit_inf1):
        return False
    if not st.hit_inf1:
        st.coins_log = sub_log(st.coins_log, c)
    st.auto_bought[key] = True
    st.auto_on[key] = True
    st.manual_today += 1
    st.total_manual += 1
    st.total_auto_unlocks += 1
    return True


def auto_round(st: State) -> int:
    """
    每波：对每个已解锁且开关开的项，最多买 1 级。
    无多段 burst，无全扫。
    """
    n = 0
    # 按 ROI 排序，但每项最多 1
    cands = []
    for it in SHOP:
        if not st.auto_bought.get(it.key) or not st.auto_on.get(it.key, True):
            continue
        if st.lv[it.key] >= it.max_lv:
            continue
        if not can_aff(st.coins_log, clog(it, st.lv[it.key]), st.hit_inf1):
            continue
        cands.append((score_level(st, it), it.key))
    cands.sort(reverse=True)
    for _, key in cands:
        if do_level(st, key, "auto"):
            n += 1
    return n


def manual_spend(st: State) -> Tuple[int, int]:
    """用满手动 3 次。返回 (升级次数, 解锁次数)"""
    ups = unl = 0
    while st.manual_today < MANUAL_PER_DAY:
        act = best_manual_action(st)
        if act is None:
            break
        kind, key = act
        if kind == "level":
            if not do_level(st, key, "manual"):
                break
            ups += 1
        else:
            if not do_unlock(st, key):
                break
            unl += 1
    return ups, unl


def run(verbose: bool = False) -> State:
    global SHOP, SHOP_MAP
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    st = new_state()

    for day in range(1, MAX_DAYS + 1):
        st.day = day
        st.manual_today = 0
        auto_buys = 0

        # 日内多脉冲产出 + 每波每项自动最多 +1
        for _ in range(PULSES):
            d = derive(st)
            # 均分日产出（log 空间：log10(1/P)）
            cg = d["day_coin_l"] + math.log10(1.0 / PULSES)
            dg = d["day_depth_l"] + math.log10(1.0 / PULSES)
            apply_income(st, cg, dg)
            auto_buys += auto_round(st)
            if st.win:
                break

        # 手动 3 次
        man_up, man_unl = manual_spend(st)
        # 手动后可能新解锁自动 → 再跑一波
        auto_buys += auto_round(st)

        d = derive(st)
        row = {
            "day": day,
            "coins": fmt(st.coins_log),
            "depth": fmt(st.depth_log),
            "dL": round(st.depth_log, 2) if math.isfinite(st.depth_log) else None,
            "manual_up": man_up,
            "manual_unlock": man_unl,
            "auto": auto_buys,
            "unlocked": sum(1 for v in st.auto_bought.values() if v),
            "total_up": st.total_up,
            "inf2": st.inf2,
            "day_depth": round(d["day_depth_l"], 2),
            "levels": {k: v for k, v in st.lv.items() if v},
            "auto_bought": [k for k, v in st.auto_bought.items() if v],
        }
        st.hist.append(row)
        if verbose:
            print(
                f"D{day:02d} c={row['coins']:>10} d={row['depth']:>10} "
                f"man={man_up}+U{man_unl}/3 auto={auto_buys:3d} unlock={row['unlocked']:2d} "
                f"up={st.total_up:4d} inf2={st.inf2} dd={d['day_depth_l']:.1f}"
            )
        if st.win:
            if verbose:
                print(
                    f"*** WIN day={day} up={st.total_up} "
                    f"manual={st.total_manual} auto={st.total_auto} "
                    f"unlocks={st.total_auto_unlocks} ***"
                )
            break
    return st


def summary(st: State) -> dict:
    return {
        "win": st.win,
        "win_day": st.win_day,
        "total_up": st.total_up,
        "total_manual": st.total_manual,
        "total_auto": st.total_auto,
        "total_auto_unlocks": st.total_auto_unlocks,
        "inf2": st.inf2,
        "hit_inf1": st.hit_inf1,
        "coins": fmt(st.coins_log),
        "depth": fmt(st.depth_log),
        "depth_log": st.depth_log if math.isfinite(st.depth_log) else None,
        "levels": dict(st.lv),
        "auto_bought": {k: v for k, v in st.auto_bought.items() if v},
        "last_day": st.hist[-1]["day"] if st.hist else 0,
        "max_day_depth": round(max_day_depth(), 2),
        "PULSES": PULSES,
        "BASE_MINING_SEC": BASE_MINING_SEC,
    }


def util(st: State) -> None:
    print("\n=== 切片 ===")
    for row in st.hist:
        if row["day"] % 5 == 0 or row["day"] <= 5 or row["day"] == st.hist[-1]["day"]:
            print(
                f"D{row['day']:02d}: man {row['manual_up']}+U{row['manual_unlock']}/3 "
                f"auto={row['auto']:3d} unlock={row['unlocked']:2d} "
                f"c={row['coins']:>10} d={row['depth']:>10} dd={row['day_depth']}"
            )


def main():
    global SHOP, SHOP_MAP, BASE_MINING_SEC, PULSES
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    mdd = max_day_depth()
    print(f"满配 day_depth_log = {mdd:.2f} (需≥310)")
    if mdd < 310:
        print("FATAL: 满配不够通关")
        return

    # 满配单日应能通关深度
    st_max = new_state()
    for it in SHOP:
        st_max.lv[it.key] = it.max_lv
    d = derive(st_max)
    print(f"满配单日 depth 增益 log = {d['day_depth_l']:.2f}")
    print(f"满配单日 coin 增益 log = {d['day_coin_l']:.2f}")

    print("\n=== 主模拟 ===")
    st = run(True)
    s = summary(st)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    util(st)

    # 扫参
    best = None
    rows = []
    print("\n=== 扫参 ===")
    for ms in (1200, 1500, 1800):
        for pulses in (4, 6, 8):
            BASE_MINING_SEC = float(ms)
            PULSES = pulses
            st2 = run(False)
            s2 = summary(st2)
            s2["ms"] = ms
            s2["pulses"] = pulses
            rows.append(s2)
            in_w = s2["win"] and s2["win_day"] and WIN_LO <= s2["win_day"] <= WIN_HI
            mark = " ★" if in_w else (" W" if s2["win"] else "")
            print(
                f"MS={ms} P={pulses}: win={s2['win']} day={s2['win_day']} "
                f"up={s2['total_up']} auto={s2['total_auto']} unlock={s2['total_auto_unlocks']}{mark}"
            )
            if s2["win"]:
                if best is None or abs((s2["win_day"] or 99) - 30) < abs((best["win_day"] or 99) - 30):
                    best = s2

    if best:
        BASE_MINING_SEC = float(best["ms"])
        PULSES = best["pulses"]
        print(f"\n=== 最佳 MS={BASE_MINING_SEC} P={PULSES} ===")
        stf = run(True)
        sf = summary(stf)
        util(stf)
    else:
        stf, sf = st, s

    out = {
        "rules": {
            "manual_per_day": 3,
            "auto": "per-item unlock purchase (costs manual slot) + on/off switch only",
            "auto_per_pulse": "each enabled item at most +1 level per produce pulse",
            "no_global_auto_protocol": True,
            "no_multi_tier_burst": True,
            "depth_settle": "log-space full day ticks, no 2e6 cap",
        },
        "constants": {
            "INF_LOG": INF_LOG,
            "CORE_LOG": CORE_LOG,
            "BASE_INTERVAL": BASE_INTERVAL,
            "BASE_MINING_SEC": BASE_MINING_SEC,
            "PULSES": PULSES,
            "MANUAL_PER_DAY": MANUAL_PER_DAY,
            "START_COINS": START_COINS,
            "max_day_depth": max_day_depth(),
        },
        "shop": [
            {
                "key": i.key, "label": i.label, "kind": i.kind, "mult": i.mult,
                "base": i.base, "growth": i.growth, "max_lv": i.max_lv, "bump": i.bump,
                "auto_base": i.auto_base, "per": i.per,
                "qty_m": i.qty_m, "rate_m": i.rate_m, "depth_m": i.depth_m,
            }
            for i in build_shop()
        ],
        "summary": sf,
        "history": stf.hist,
    }
    path = r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v10_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    import shutil
    demo = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo"
    shutil.copyfile(
        r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v10_item_auto.py",
        demo + r"\sim_v10_item_auto.py",
    )
    with open(demo + r"\sim_v10_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    ok = sf["win"] and sf["win_day"] and WIN_LO <= sf["win_day"] <= WIN_HI
    # 硬验收：满配日深度够 + 模拟通关
    hard = max_day_depth() >= 310 and sf["win"]
    print(f"\n写出 {path}")
    print("ACCEPT" if ok else ("PASS_WIN" if hard else "REJECT"), json.dumps(sf, ensure_ascii=False))
    return sf


if __name__ == "__main__":
    main()
