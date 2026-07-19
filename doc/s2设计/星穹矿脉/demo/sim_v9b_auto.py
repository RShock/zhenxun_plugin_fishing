# -*- coding: utf-8 -*-
"""
S2 v9b · 手动 3 次 + 自动无限（可开关）· 约 30 日节奏
====================================================

定案
----
1. 手动：每天硬顶 3（点按钮）
2. 自动采购协议 lv≥1：开启后可无限自动买（非 +日额度）
3. 自动可开关
4. 自动 **不会** 自己升级「自动采购协议」（协议只能手动升）
5. 每次产出后自动连买 burst 次；**无日末扫光**（避免一天吃穿科技树）
6. 大胆指数 + 常数维度化

burst = floor(BASE * GROW^(auto_lv-1))
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
AUTO_MAX = 15
AUTO_BURST_BASE = 3
AUTO_BURST_GROW = 1.22
START_COINS = 50.0
MAX_DAYS = 45
WIN_LO, WIN_HI = 26, 34
# 每天生产结算次数（模拟日内多次挂机结算触发 auto）
PRODUCE_PULSES = 4

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
    per: float = 0.0
    qty_m: float = 1.0
    rate_m: float = 1.0
    depth_m: float = 1.0


def build_shop() -> List[Item]:
    return [
        Item("blast", "浅层爆破", "depth", 3.0, 12, 2.55, 200, "深度 ×3"),
        Item("strata", "岩层许可", "strata", 3.0, 18, 2.60, 180, "地层 ×3"),
        Item("cart", "矿车车厢", "qty", 3.0, 14, 2.55, 200, "产量 ×3"),
        Item("pick", "镐速齿轮", "rate", 2.0, 10, 2.40, 180, "速度 ×2"),
        Item("sorter", "分拣爪", "value", 2.0, 16, 2.50, 160, "售价 ×2"),
        Item("market", "矿市特许", "market", 2.0, 22, 2.55, 140, "市价 ×2"),
        Item("shift", "加班班次", "hours", 2.0, 20, 2.45, 100, "工时 ×2"),
        Item("chrono", "时序齿轮", "interval", 2.0, 22, 2.45, 100, "间隔 /2"),
        Item("rebate", "财税返还", "rebate", 2.0, 26, 2.50, 100, "结算 ×2"),
        Item("belt", "星尘传送带", "rate", 1.5, 30, 2.45, 120, "速度 ×1.5"),
        Item("brace", "巷道支架", "depth", 1.5, 28, 2.45, 120, "深度 ×1.5"),
        Item("lamp", "巷道工灯", "qty", 1.5, 28, 2.45, 120, "产量 ×1.5"),
        Item("polish", "虹核抛光", "refine", 2.0, 40, 2.70, 40, "精矿 ×2"),
        Item("drill", "猫钻头", "rare", 1.0, 24, 2.45, 30, "稀有↑", per=1.0),
        Item("whisker", "猫须探针", "luck", 1.0, 26, 2.50, 25, "幸运↑", per=1.0),
        Item(
            "canteen", "工地罐头铺", "hybrid", 1.25, 32, 2.50, 80, "全属性 ×1.25",
            qty_m=1.25, rate_m=1.25, depth_m=1.25,
        ),
        Item("auto", "自动采购协议", "auto", 1.0, 100, 3.2, AUTO_MAX, "解锁/强化自动"),
    ]


SHOP: List[Item] = []
SHOP_MAP: Dict[str, Item] = {}


def clog(it: Item, lv: int) -> float:
    return math.log10(it.base) + lv * math.log10(it.growth)


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


def auto_burst(auto_lv: int) -> int:
    if auto_lv <= 0:
        return 0
    return max(1, int(round(AUTO_BURST_BASE * (AUTO_BURST_GROW ** (auto_lv - 1)))))


def rarity_probs(drill: int, luck: int) -> Dict[str, float]:
    t = min(1.0, drill / 30.0)
    lk = min(1.0, luck / 25.0)
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
    manual_today: int = 0
    auto_buys_today: int = 0
    total_up: int = 0
    total_manual: int = 0
    total_auto: int = 0
    auto_enabled: bool = True
    hit_inf1: bool = False
    inf2: int = 0
    win: bool = False
    win_day: Optional[int] = None
    hist: List[dict] = field(default_factory=list)


def new_state() -> State:
    return State(lv={i.key: 0 for i in SHOP}, coins_log=math.log10(START_COINS))


def auto_unlocked(st: State) -> bool:
    return st.lv.get("auto", 0) >= 1


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

    interval = BASE_INTERVAL / max(10 ** (rate_l + interval_l), 1e-40)
    mining_sec = BASE_MINING_SEC * (10 ** hours_l)
    ticks = mining_sec / interval
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
    day_depth_l = math.log10(max(ticks, 1e-40)) + depth_tick_l
    day_coin_l = math.log10(max(ticks, 1e-40)) + coins_tick_l
    return {
        "interval": interval,
        "ticks": ticks,
        "mining_sec": mining_sec,
        "depth_tick_l": depth_tick_l,
        "coins_tick_l": coins_tick_l,
        "day_depth_l": day_depth_l,
        "day_coin_l": day_coin_l,
        "probs": probs,
    }


def max_day_depth() -> float:
    st = new_state()
    for it in SHOP:
        if it.kind != "auto":
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
    if it.kind == "auto":
        return 0.65 if st.lv.get("auto", 0) == 0 else 0.12
    return 0.01


def score(st: State, it: Item, source: str) -> float:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return -1e300
    # 自动流程禁止升级协议本身
    if source == "auto" and it.kind == "auto":
        return -1e300

    c = max(clog(it, lv), 1e-12)
    s = delta_log(st, it) / c
    dlog = st.depth_log if math.isfinite(st.depth_log) else -5.0
    clog_ = st.coins_log if math.isfinite(st.coins_log) else -5.0
    depth_gap = CORE_LOG - dlog
    coin_gap = 0.0 if st.hit_inf1 else INF_LOG - clog_

    if depth_gap > 2:
        if it.kind in ("depth", "strata"):
            s *= 3.8 + min(3.0, depth_gap / 60.0)
        elif it.kind in ("rate", "interval", "hours"):
            s *= 3.0 + min(2.5, depth_gap / 80.0)
        elif it.kind == "hybrid":
            s *= 2.0
        elif it.kind in ("qty", "value", "market", "rebate"):
            s *= 0.95 + min(1.8, max(0.0, coin_gap) / 180.0)
        elif it.kind == "refine":
            s *= 0.4
    else:
        if it.kind in ("qty", "value", "market", "rebate", "rate"):
            s *= 2.8 + min(2.0, max(0.0, coin_gap) / 100.0)
        if it.kind in ("depth", "strata") and depth_gap < 0.5:
            s *= 0.2

    if it.kind == "auto" and source == "manual":
        if st.lv.get("auto", 0) == 0:
            # 尽早解锁
            if st.day >= 2 and math.isfinite(st.coins_log) and st.coins_log > c - 0.5:
                s *= 8.0
            else:
                s *= 2.0
        else:
            # 强化 burst：中期有价值
            s *= 1.4 if depth_gap > 30 else 0.7

    if it.kind in ("rare", "luck"):
        s *= 0.5 if st.total_up > 25 else 0.85
    return s


def best(st: State, source: str) -> Optional[Item]:
    b, bs = None, -1e300
    for it in SHOP:
        if st.lv[it.key] >= it.max_lv:
            continue
        if source == "auto" and it.kind == "auto":
            continue
        if not can_aff(st.coins_log, clog(it, st.lv[it.key]), st.hit_inf1):
            continue
        sc = score(st, it, source)
        if sc > bs:
            bs, b = sc, it
    return b


def buy_one(st: State, it: Item, source: str) -> bool:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return False
    if source == "manual":
        if st.manual_today >= MANUAL_PER_DAY:
            return False
    elif source == "auto":
        if not auto_unlocked(st) or not st.auto_enabled:
            return False
        if it.kind == "auto":
            return False
    else:
        return False
    c = clog(it, lv)
    if not can_aff(st.coins_log, c, st.hit_inf1):
        return False
    if not st.hit_inf1:
        st.coins_log = sub_log(st.coins_log, c)
    st.lv[it.key] = lv + 1
    st.total_up += 1
    if source == "manual":
        st.manual_today += 1
        st.total_manual += 1
    else:
        st.auto_buys_today += 1
        st.total_auto += 1
    return True


def auto_spend(st: State, limit: Optional[int] = None) -> int:
    if not auto_unlocked(st) or not st.auto_enabled:
        return 0
    if limit is None:
        limit = auto_burst(st.lv["auto"])
    n = 0
    for _ in range(max(0, limit)):
        it = best(st, "auto")
        if it is None:
            break
        if not buy_one(st, it, "auto"):
            break
        n += 1
    return n


def manual_spend_smart(st: State) -> int:
    n = 0
    while st.manual_today < MANUAL_PER_DAY:
        it = best(st, "manual")
        if it is None:
            break
        if not buy_one(st, it, "manual"):
            break
        n += 1
    return n


def run(verbose: bool = False, auto_on: bool = True) -> State:
    global SHOP, SHOP_MAP
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    st = new_state()
    st.auto_enabled = auto_on

    for day in range(1, MAX_DAYS + 1):
        st.day = day
        st.manual_today = 0
        st.auto_buys_today = 0

        # 日内多次产出脉冲 → 每次触发 auto burst（无限次数，仅 burst 限制单次）
        for pulse in range(PRODUCE_PULSES):
            d = derive(st)
            # 把一天的产出均分到脉冲
            cg = d["day_coin_l"] + math.log10(1.0 / PRODUCE_PULSES)
            dg = d["day_depth_l"] + math.log10(1.0 / PRODUCE_PULSES)
            apply_income(st, cg, dg)
            auto_spend(st)
            if st.win:
                break

        # 玩家手动 3 次（常用于点协议 / 补最高 ROI）
        man_n = manual_spend_smart(st)
        # 手动后可能刚解锁 auto
        auto_spend(st)

        d = derive(st)
        row = {
            "day": day,
            "coins": fmt(st.coins_log),
            "depth": fmt(st.depth_log),
            "manual": man_n,
            "auto": st.auto_buys_today,
            "auto_lv": st.lv["auto"],
            "auto_on": bool(st.auto_enabled and auto_unlocked(st)),
            "burst": auto_burst(st.lv["auto"]),
            "total_up": st.total_up,
            "total_manual": st.total_manual,
            "total_auto": st.total_auto,
            "inf2": st.inf2,
            "day_depth": round(d["day_depth_l"], 2),
            "levels": {k: v for k, v in st.lv.items() if v},
        }
        st.hist.append(row)
        if verbose:
            print(
                f"D{day:02d} c={row['coins']:>10} d={row['depth']:>10} "
                f"man={man_n}/3 auto={row['auto']:4d}(lv{st.lv['auto']},burst={row['burst']}) "
                f"up={st.total_up:4d} inf2={st.inf2} dd={d['day_depth_l']:.1f}"
            )
        if st.win:
            if verbose:
                print(
                    f"*** WIN day={day} up={st.total_up} "
                    f"manual={st.total_manual} auto={st.total_auto} ***"
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
        "inf2": st.inf2,
        "hit_inf1": st.hit_inf1,
        "coins": fmt(st.coins_log),
        "depth": fmt(st.depth_log),
        "depth_log": st.depth_log if math.isfinite(st.depth_log) else None,
        "levels": dict(st.lv),
        "last_day": st.hist[-1]["day"] if st.hist else 0,
        "BASE_MINING_SEC": BASE_MINING_SEC,
        "AUTO_BURST_BASE": AUTO_BURST_BASE,
        "AUTO_BURST_GROW": AUTO_BURST_GROW,
        "PRODUCE_PULSES": PRODUCE_PULSES,
        "max_day_depth": round(max_day_depth(), 2),
    }


def util(st: State) -> None:
    print("\n=== 手动/自动 ===")
    for row in st.hist:
        if row["day"] % 5 == 0 or row["day"] <= 6 or row["day"] == st.hist[-1]["day"]:
            print(
                f"D{row['day']:02d}: man {row['manual']}/3 auto={row['auto']:4d} "
                f"lv={row['auto_lv']} burst={row['burst']} "
                f"c={row['coins']:>10} d={row['depth']:>10}"
            )


def sweep():
    global BASE_MINING_SEC, AUTO_BURST_BASE, AUTO_BURST_GROW, PRODUCE_PULSES
    best = None
    rows = []
    print("\n=== 扫参 ===")
    for ms in (1200, 1500, 1800):
        for burst in (2, 3, 4, 5):
            for grow in (1.15, 1.22, 1.28):
                for pulses in (3, 4, 5):
                    BASE_MINING_SEC = float(ms)
                    AUTO_BURST_BASE = burst
                    AUTO_BURST_GROW = grow
                    PRODUCE_PULSES = pulses
                    st = run(False, True)
                    s = summary(st)
                    s.update({"ms": ms, "burst": burst, "grow": grow, "pulses": pulses})
                    rows.append(s)
                    in_w = s["win"] and s["win_day"] and WIN_LO <= s["win_day"] <= WIN_HI
                    if in_w or (s["win"] and abs((s["win_day"] or 99) - 30) <= 4):
                        mark = " ★" if in_w else " ~"
                        print(
                            f"MS={ms} b={burst} g={grow} p={pulses}: "
                            f"day={s['win_day']} up={s['total_up']} "
                            f"man={s['total_manual']} auto={s['total_auto']}{mark}"
                        )
                    if in_w:
                        if best is None or abs(s["win_day"] - 30) < abs(best["win_day"] - 30):
                            best = s
    if not best:
        wins = [r for r in rows if r["win"]]
        if wins:
            wins.sort(key=lambda r: abs((r["win_day"] or 99) - 30))
            best = wins[0]
            print("最近30日:", best["win_day"], "params", best.get("ms"), best.get("burst"))
    BASE_MINING_SEC, AUTO_BURST_BASE, AUTO_BURST_GROW, PRODUCE_PULSES = 1500.0, 3, 1.22, 4
    return best, rows


def main():
    global SHOP, SHOP_MAP, BASE_MINING_SEC, AUTO_BURST_BASE, AUTO_BURST_GROW, PRODUCE_PULSES
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    print("满配 day_depth", max_day_depth())
    print("burst", {lv: auto_burst(lv) for lv in range(0, 10)})
    print("规则: 手动3/日 | 自动无限(burst/产出) | 协议仅手动升 | 可开关")

    print("\n=== 主模拟 ===")
    st = run(True, True)
    s = summary(st)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    util(st)

    print("\n=== auto OFF ===")
    print(json.dumps(summary(run(False, False)), ensure_ascii=False, indent=2))

    best, rows = sweep()
    if best:
        BASE_MINING_SEC = float(best["ms"])
        AUTO_BURST_BASE = best["burst"]
        AUTO_BURST_GROW = best["grow"]
        PRODUCE_PULSES = best["pulses"]
        print(
            f"\n=== 最佳 MS={BASE_MINING_SEC} b={AUTO_BURST_BASE} "
            f"g={AUTO_BURST_GROW} p={PRODUCE_PULSES} ==="
        )
        st2 = run(True, True)
        s2 = summary(st2)
        util(st2)
    else:
        st2, s2 = st, s

    out = {
        "rules": {
            "manual_per_day": 3,
            "auto_unlock": "auto_lv >= 1",
            "auto_unlimited": True,
            "auto_not_daily_quota": True,
            "auto_toggle": True,
            "auto_cannot_buy_auto": True,
            "auto_trigger": "after each produce pulse: up to burst buys",
            "burst": "BASE * GROW^(lv-1)",
        },
        "constants": {
            "INF_LOG": INF_LOG,
            "CORE_LOG": CORE_LOG,
            "BASE_INTERVAL": BASE_INTERVAL,
            "BASE_MINING_SEC": BASE_MINING_SEC,
            "MANUAL_PER_DAY": MANUAL_PER_DAY,
            "AUTO_MAX": AUTO_MAX,
            "AUTO_BURST_BASE": AUTO_BURST_BASE,
            "AUTO_BURST_GROW": AUTO_BURST_GROW,
            "PRODUCE_PULSES": PRODUCE_PULSES,
            "START_COINS": START_COINS,
            "max_day_depth": max_day_depth(),
        },
        "shop": [
            {
                "key": i.key, "label": i.label, "kind": i.kind, "mult": i.mult,
                "base": i.base, "growth": i.growth, "max_lv": i.max_lv, "bump": i.bump,
                "per": i.per, "qty_m": i.qty_m, "rate_m": i.rate_m, "depth_m": i.depth_m,
            }
            for i in build_shop()
        ],
        "summary": s2,
        "history": st2.hist,
        "sweep_near": [
            {
                "win_day": r["win_day"], "total_up": r["total_up"],
                "total_manual": r["total_manual"], "total_auto": r["total_auto"],
                "ms": r.get("ms"), "burst": r.get("burst"),
                "grow": r.get("grow"), "pulses": r.get("pulses"),
            }
            for r in rows
            if r["win"] and r["win_day"] and 20 <= r["win_day"] <= 40
        ],
    }
    path = r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v9b_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    import shutil
    demo = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo"
    shutil.copyfile(
        r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v9b_auto.py",
        demo + r"\sim_v9b_auto.py",
    )
    with open(demo + r"\sim_v9b_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    ok = s2["win"] and s2["win_day"] and WIN_LO <= s2["win_day"] <= WIN_HI
    print(f"\n写出 {path}")
    print("ACCEPT" if ok else "CHECK", json.dumps(s2, ensure_ascii=False))
    return s2


if __name__ == "__main__":
    main()
