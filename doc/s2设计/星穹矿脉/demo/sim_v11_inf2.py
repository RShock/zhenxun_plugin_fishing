# -*- coding: utf-8 -*-
"""
S2 v11 · 二阶无限通关（1e306 次一阶）
====================================

用户定案
--------
- 目标不是「触发一次一阶」
- 目标是 **二阶无限** = 累计达成 **1e306 次一阶无限**
- 每次一阶应越来越快
- 允许拉长到 ~40 天
- 深度系统保留作成长维度，通关条件以二阶为准

数学模型
--------
一阶触发：coins_log 达到 INF_LOG(308) 时
  本段「溢出」可折算为一阶次数：
    gain_log10 = max(0, coins_log - INF_LOG)   # 若刚好 308，记 +1 → gain_log=0 用特殊处理
    实际：至少 +1，若 coins 远超则 gain = 10^(coins_log-308)
    用 log 累加：inf1_log = log10( 10^inf1_log + gain )

  一阶后：
    coins 重置到起点（安家费），保留所有升级
    永久加速：prod 乘区 += f(inf1_log)
      perm_log = INF1_PERM * inf1_log   # 一阶次数越多，产量/速度永久越快
    这样下一次冲 ∞ 越来越快

二阶：inf1_log >= 306 通关

日产出（log）：
  day_coin = log_ticks + coins_tick + perm_log
  day_depth = log_ticks + depth_tick + perm_log * DEPTH_PERM_SHARE

手动 3/日；每项单独买自动；每波每项最多自动 +1
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INF_LOG = 308.0
INF2_NEED = 306.0  # 二阶：1e306 次一阶
CORE_LOG = 306.0   # 深度目标（展示/并行）
BASE_INTERVAL = 8.0
BASE_MINING_SEC = 1800.0
BASE_Q = 1.0
BASE_DEPTH = 1.0
MANUAL_PER_DAY = 3
START_COINS = 80.0
MAX_DAYS = 45
WIN_LO, WIN_HI = 28, 42
PULSES = 4
# 一阶永久加成：perm_log = INF1_PERM * inf1_log
# 例：inf1=1e10 → inf1_log=10 → perm +5 数量级（若 PERM=0.5）
INF1_PERM = 0.55
DEPTH_PERM_SHARE = 0.35  # 永久加成对深度的分摊
# 一阶后 coins 重置到
POST_INF_COINS = 100.0

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
    auto_base: float
    per: float = 0.0
    qty_m: float = 1.0
    rate_m: float = 1.0
    depth_m: float = 1.0


def build_shop() -> List[Item]:
    return [
        Item("blast", "浅层爆破", "depth", 3.0, 15, 2.4, 220, "深度 ×3", 200),
        Item("strata", "岩层许可", "strata", 3.0, 20, 2.45, 200, "地层 ×3", 220),
        Item("cart", "矿车车厢", "qty", 3.0, 16, 2.4, 220, "产量 ×3", 200),
        Item("pick", "镐速齿轮", "rate", 2.0, 12, 2.25, 200, "速度 ×2", 180),
        Item("sorter", "分拣爪", "value", 2.0, 18, 2.35, 180, "售价 ×2", 210),
        Item("market", "矿市特许", "market", 2.0, 24, 2.4, 160, "市价 ×2", 230),
        Item("shift", "加班班次", "hours", 2.0, 22, 2.3, 120, "工时 ×2", 190),
        Item("chrono", "时序齿轮", "interval", 2.0, 24, 2.3, 120, "间隔 /2", 190),
        Item("rebate", "财税返还", "rebate", 2.0, 28, 2.35, 120, "结算 ×2", 240),
        Item("belt", "星尘传送带", "rate", 1.5, 32, 2.3, 140, "速度 ×1.5", 160),
        Item("brace", "巷道支架", "depth", 1.5, 30, 2.3, 140, "深度 ×1.5", 160),
        Item("lamp", "巷道工灯", "qty", 1.5, 30, 2.3, 140, "产量 ×1.5", 160),
        Item("polish", "虹核抛光", "refine", 2.0, 45, 2.55, 50, "精矿 ×2", 260),
        Item("drill", "猫钻头", "rare", 1.0, 26, 2.35, 35, "稀有↑", 150, per=1.0),
        Item("whisker", "猫须探针", "luck", 1.0, 28, 2.4, 30, "幸运↑", 150, per=1.0),
        Item(
            "canteen", "工地罐头铺", "hybrid", 1.25, 35, 2.35, 100, "全属性 ×1.25",
            250, qty_m=1.25, rate_m=1.25, depth_m=1.25,
        ),
    ]


SHOP: List[Item] = []
SHOP_MAP: Dict[str, Item] = {}


def clog(it: Item, lv: int) -> float:
    return math.log10(it.base) + lv * math.log10(it.growth)


def auto_cost(it: Item) -> float:
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


def can_aff(coins: float, c: float) -> bool:
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
    # 一阶次数 log10；二阶进度 = inf1_log / 306
    inf1_log: float = float("-inf")  # 0 次 → -inf
    inf1_events: int = 0  # 触发「冲破」次数（统计用，非次数本体）
    lv: Dict[str, int] = field(default_factory=dict)
    auto_bought: Dict[str, bool] = field(default_factory=dict)
    auto_on: Dict[str, bool] = field(default_factory=dict)
    manual_today: int = 0
    total_up: int = 0
    total_manual: int = 0
    total_auto: int = 0
    total_auto_unlocks: int = 0
    win: bool = False
    win_day: Optional[int] = None
    hist: List[dict] = field(default_factory=list)


def new_state() -> State:
    return State(
        lv={i.key: 0 for i in SHOP},
        auto_bought={i.key: False for i in SHOP},
        auto_on={i.key: True for i in SHOP},
        coins_log=math.log10(START_COINS),
    )


def perm_log(st: State) -> float:
    if not math.isfinite(st.inf1_log) or st.inf1_log < -12:
        return 0.0
    return INF1_PERM * max(0.0, st.inf1_log)


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

    pl = perm_log(st)
    log_ticks = (
        math.log10(BASE_MINING_SEC) + hours_l
        - math.log10(BASE_INTERVAL)
        + rate_l + interval_l
        + pl  # 永久加速 ticks
    )
    depth_tick_l = math.log10(BASE_DEPTH) + dep_l + strata_l + pl * DEPTH_PERM_SHARE
    probs = rarity_probs(drill, luck)
    e_price = 0.0
    for r, p in probs.items():
        u = PRICE[r] * (10 ** val_l) * (10 ** market_l)
        if r in ("SSR", "UR"):
            u *= 10 ** ref_l
        e_price += p * u
    e_price = max(e_price, 1e-15)
    coins_tick_l = math.log10(BASE_Q) + qty_l + math.log10(e_price) + rebate_l + pl
    day_depth_l = log_ticks + depth_tick_l
    day_coin_l = log_ticks + coins_tick_l
    return {
        "log_ticks": log_ticks,
        "day_depth_l": day_depth_l,
        "day_coin_l": day_coin_l,
        "perm": pl,
        "probs": probs,
    }


def apply_income(st: State, cg: float, dg: float) -> None:
    """加收入，并处理可能的一阶溢出（可批量）。"""
    st.coins_log = add_log(st.coins_log, cg)
    st.depth_log = add_log(st.depth_log, dg)
    if math.isfinite(st.depth_log):
        st.depth_log = min(st.depth_log, CORE_LOG)
    process_first_order(st)
    check_win(st)


def process_first_order(st: State) -> float:
    """
    若 coins 达/超 ∞，折算一阶次数并重置 coins。
    返回本次 gain_log（log10 次数）。
    """
    if not math.isfinite(st.coins_log) or st.coins_log < INF_LOG - 1e-12:
        return float("-inf")

    # 次数：至少 1；溢出部分 10^(coins-308)
    # total_gain = 1 + 10^(coins_log - 308) 约等于当 coins>>308 时 10^(coins-308)
    # 更干净：gain_log = log10(1 + 10^(coins_log - 308))
    over = st.coins_log - INF_LOG
    if over < 0:
        gain_log = 0.0  # +1
    else:
        # 1 + 10^over
        if over > 15:
            gain_log = over  # ≈ 10^over
        else:
            gain_log = math.log10(1.0 + 10 ** over)

    st.inf1_log = add_log(st.inf1_log, gain_log)
    st.inf1_events += 1
    # 重置矿币，保留升级与永久加成
    st.coins_log = math.log10(POST_INF_COINS)
    return gain_log


def check_win(st: State) -> None:
    if st.win:
        return
    if math.isfinite(st.inf1_log) and st.inf1_log >= INF2_NEED - 1e-9:
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
    # 二阶缺口大时偏生产（冲币）
    i1 = st.inf1_log if math.isfinite(st.inf1_log) else -5.0
    inf_gap = INF2_NEED - i1
    clog_ = st.coins_log if math.isfinite(st.coins_log) else -5.0
    coin_gap = INF_LOG - clog_

    if inf_gap > 2:
        # 全力冲一阶频率：qty/value/rate/hours/market/rebate
        if it.kind in ("qty", "value", "market", "rebate", "rate", "hours", "interval"):
            s *= 3.0 + min(3.0, inf_gap / 80.0)
        elif it.kind == "hybrid":
            s *= 2.2
        elif it.kind in ("depth", "strata"):
            s *= 1.2  # 深度次要
        elif it.kind == "refine":
            s *= 1.0 + min(1.5, coin_gap / 100.0)
    if it.kind in ("rare", "luck"):
        s *= 0.45 if st.total_up > 30 else 0.8
    return s


def score_unlock(st: State, it: Item) -> float:
    if st.auto_bought[it.key]:
        return -1e300
    c = max(auto_cost(it), 1e-12)
    base = delta_log(st, it) * 3.0 / c
    if it.kind in ("qty", "value", "rate", "hours", "interval", "market", "rebate"):
        base *= 1.6
    unlocked = sum(1 for v in st.auto_bought.values() if v)
    if unlocked == 0 and st.day >= 2:
        base *= 2.0
    return base


def best_manual(st: State) -> Optional[Tuple[str, str]]:
    best = None
    bs = -1e300
    for it in SHOP:
        if st.lv[it.key] < it.max_lv and can_aff(st.coins_log, clog(it, st.lv[it.key])):
            sc = score_level(st, it)
            if sc > bs:
                bs, best = sc, ("level", it.key)
        if not st.auto_bought[it.key] and can_aff(st.coins_log, auto_cost(it)):
            sc = score_unlock(st, it)
            if sc > bs:
                bs, best = sc, ("unlock", it.key)
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
    if not can_aff(st.coins_log, c):
        return False
    st.coins_log = sub_log(st.coins_log, c)
    st.lv[key] = lv + 1
    st.total_up += 1
    if source == "manual":
        st.manual_today += 1
        st.total_manual += 1
    else:
        st.total_auto += 1
    process_first_order(st)  # 极少情况：买完仍超？不会
    return True


def do_unlock(st: State, key: str) -> bool:
    if st.auto_bought[key] or st.manual_today >= MANUAL_PER_DAY:
        return False
    it = SHOP_MAP[key]
    c = auto_cost(it)
    if not can_aff(st.coins_log, c):
        return False
    st.coins_log = sub_log(st.coins_log, c)
    st.auto_bought[key] = True
    st.auto_on[key] = True
    st.manual_today += 1
    st.total_manual += 1
    st.total_auto_unlocks += 1
    return True


def auto_round(st: State) -> int:
    cands = []
    for it in SHOP:
        if not st.auto_bought.get(it.key) or not st.auto_on.get(it.key, True):
            continue
        if st.lv[it.key] >= it.max_lv:
            continue
        if not can_aff(st.coins_log, clog(it, st.lv[it.key])):
            continue
        cands.append((score_level(st, it), it.key))
    cands.sort(reverse=True)
    n = 0
    for _, key in cands:
        if do_level(st, key, "auto"):
            n += 1
    return n


def manual_spend(st: State) -> Tuple[int, int]:
    ups = unl = 0
    while st.manual_today < MANUAL_PER_DAY:
        act = best_manual(st)
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
        day_inf_gain = float("-inf")

        for _ in range(PULSES):
            d = derive(st)
            cg = d["day_coin_l"] + math.log10(1.0 / PULSES)
            dg = d["day_depth_l"] + math.log10(1.0 / PULSES)
            before = st.inf1_log
            apply_income(st, cg, dg)
            if math.isfinite(st.inf1_log):
                if not math.isfinite(before):
                    day_inf_gain = st.inf1_log
                else:
                    # approximate added
                    day_inf_gain = st.inf1_log  # track final
            auto_buys += auto_round(st)
            # 买升级可能不触发一阶；收入后已 process
            if st.win:
                break

        man_up, man_unl = manual_spend(st)
        auto_buys += auto_round(st)

        d = derive(st)
        inf1_disp = fmt(st.inf1_log) if math.isfinite(st.inf1_log) else "0"
        inf2_pct = 0.0
        if math.isfinite(st.inf1_log):
            inf2_pct = min(100.0, 100.0 * (st.inf1_log / INF2_NEED))

        row = {
            "day": day,
            "coins": fmt(st.coins_log),
            "depth": fmt(st.depth_log),
            "inf1": inf1_disp,
            "inf1_log": round(st.inf1_log, 3) if math.isfinite(st.inf1_log) else None,
            "inf2_pct": round(inf2_pct, 4),
            "inf1_events": st.inf1_events,
            "perm": round(perm_log(st), 2),
            "manual_up": man_up,
            "manual_unlock": man_unl,
            "auto": auto_buys,
            "unlocked": sum(1 for v in st.auto_bought.values() if v),
            "total_up": st.total_up,
            "day_coin": round(d["day_coin_l"], 2),
            "levels": {k: v for k, v in st.lv.items() if v},
        }
        st.hist.append(row)
        if verbose:
            print(
                f"D{day:02d} c={row['coins']:>10} inf1={inf1_disp:>10} "
                f"({inf2_pct:6.2f}%) ev={st.inf1_events:3d} perm={row['perm']:5.1f} "
                f"man={man_up}+U{man_unl}/3 auto={auto_buys:3d} "
                f"up={st.total_up:4d} dc={d['day_coin_l']:.1f}"
            )
        if st.win:
            if verbose:
                print(
                    f"*** WIN 二阶 day={day} inf1={inf1_disp} "
                    f"events={st.inf1_events} up={st.total_up} ***"
                )
            break
    return st


def summary(st: State) -> dict:
    return {
        "win": st.win,
        "win_day": st.win_day,
        "inf1": fmt(st.inf1_log) if math.isfinite(st.inf1_log) else "0",
        "inf1_log": st.inf1_log if math.isfinite(st.inf1_log) else None,
        "inf1_events": st.inf1_events,
        "inf2_need": INF2_NEED,
        "perm": perm_log(st),
        "total_up": st.total_up,
        "total_manual": st.total_manual,
        "total_auto": st.total_auto,
        "total_auto_unlocks": st.total_auto_unlocks,
        "coins": fmt(st.coins_log),
        "depth": fmt(st.depth_log),
        "levels": dict(st.lv),
        "last_day": st.hist[-1]["day"] if st.hist else 0,
        "INF1_PERM": INF1_PERM,
        "PULSES": PULSES,
        "BASE_MINING_SEC": BASE_MINING_SEC,
    }


def util(st: State) -> None:
    print("\n=== 切片 ===")
    for row in st.hist:
        if row["day"] % 5 == 0 or row["day"] <= 5 or row["day"] == st.hist[-1]["day"]:
            print(
                f"D{row['day']:02d}: inf1={row['inf1']:>10} ({row['inf2_pct']:6.2f}%) "
                f"ev={row['inf1_events']:3d} perm={row['perm']} "
                f"c={row['coins']:>10} dc={row['day_coin']}"
            )


def sweep():
    global INF1_PERM, PULSES, BASE_MINING_SEC
    best = None
    rows = []
    print("\n=== 扫参 ===")
    for perm in (0.40, 0.50, 0.55, 0.65, 0.75):
        for pulses in (3, 4, 5, 6):
            for ms in (1500, 1800, 2200):
                INF1_PERM = perm
                PULSES = pulses
                BASE_MINING_SEC = float(ms)
                st = run(False)
                s = summary(st)
                s.update({"perm_k": perm, "pulses": pulses, "ms": ms})
                rows.append(s)
                in_w = s["win"] and s["win_day"] and WIN_LO <= s["win_day"] <= WIN_HI
                if s["win"] or (perm == 0.55 and pulses == 4):
                    mark = " ★" if in_w else (" W" if s["win"] else "")
                    print(
                        f"P={perm} pul={pulses} ms={ms}: win={s['win']} day={s['win_day']} "
                        f"inf1={s['inf1']} ev={s['inf1_events']} up={s['total_up']}{mark}"
                    )
                if in_w:
                    if best is None or abs(s["win_day"] - 35) < abs(best["win_day"] - 35):
                        best = s
    if not best:
        wins = [r for r in rows if r["win"]]
        if wins:
            wins.sort(key=lambda r: abs((r["win_day"] or 99) - 35))
            best = wins[0]
    INF1_PERM, PULSES, BASE_MINING_SEC = 0.55, 4, 1800.0
    return best, rows


def main():
    global SHOP, SHOP_MAP, INF1_PERM, PULSES, BASE_MINING_SEC
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    print("通关: inf1_log >= 306 (二阶=1e306次一阶)")
    print("永久加成: perm = INF1_PERM * inf1_log")
    print("\n=== 主模拟 ===")
    st = run(True)
    s = summary(st)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    util(st)

    best, rows = sweep()
    if best:
        INF1_PERM = best["perm_k"]
        PULSES = best["pulses"]
        BASE_MINING_SEC = float(best["ms"])
        print(f"\n=== 最佳 PERM={INF1_PERM} P={PULSES} MS={BASE_MINING_SEC} ===")
        st2 = run(True)
        s2 = summary(st2)
        util(st2)
    else:
        st2, s2 = st, s

    out = {
        "rules": {
            "win": "inf1_log >= 306  (second-order = 1e306 first-order infinities)",
            "first_order": "when coins_log>=308: gain 1+10^(coins-308) first-orders, reset coins, keep upgrades",
            "faster_each_time": "perm_log = INF1_PERM * inf1_log multiplies production",
            "manual": 3,
            "auto": "per-item unlock + toggle; +1 level per item per pulse",
            "days": "target ~28-42",
        },
        "constants": {
            "INF_LOG": INF_LOG,
            "INF2_NEED": INF2_NEED,
            "INF1_PERM": INF1_PERM,
            "DEPTH_PERM_SHARE": DEPTH_PERM_SHARE,
            "BASE_MINING_SEC": BASE_MINING_SEC,
            "PULSES": PULSES,
            "POST_INF_COINS": POST_INF_COINS,
            "MAX_DAYS": MAX_DAYS,
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
        "summary": s2,
        "history": st2.hist,
    }
    path = r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v11_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    import shutil
    demo = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo"
    shutil.copyfile(
        r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v11_inf2.py",
        demo + r"\sim_v11_inf2.py",
    )
    with open(demo + r"\sim_v11_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    ok = s2["win"] and s2["win_day"] and WIN_LO <= s2["win_day"] <= WIN_HI
    print(f"\n写出 {path}")
    print("ACCEPT" if ok else "CHECK", json.dumps(s2, ensure_ascii=False))
    return s2


if __name__ == "__main__":
    main()
