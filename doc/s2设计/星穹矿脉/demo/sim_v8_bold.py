# -*- coding: utf-8 -*-
"""
S2 星穹矿脉 · v8 大胆指数（定稿向）
==================================

原则
----
- 指数必须大胆：核心维 ×3 / ×2，不靠 360 级小碎步
- **公式常数全部维度化**：工时、间隔、地层、市价、结算返还
- 单项 max 必须让满配 day_depth_log ≳ 310（否则永久卡关）
- 自动采购扩容日额度；每天协议限 1 级
- UI 只显示 ×N

满配 day_depth 预算（验收）
--------------------------
day_depth = log10(mining_sec/interval) + log10(depth/tick)
         = log10(BASE_MS/BASE_IV) + hours + rate + chrono + depth + strata + hybrid
目标 ≥ 310
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INF_LOG = 308.0
CORE_LOG = 306.0
BASE_INTERVAL = 8.0
BASE_MINING_SEC = 1800.0
BASE_Q = 1.0
BASE_DEPTH = 1.0
BASE_MANUAL = 3
AUTO_PER = 6
AUTO_MAX = 20
AUTO_PER_DAY = 1
START_COINS = 50.0
MAX_DAYS = 40
WIN_LO, WIN_HI = 26, 34

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
    # max 按满配 day_depth≳310 反推；growth 仍 > mult
    return [
        # 核心大胆维
        Item("blast", "浅层爆破", "depth", 3.0, 12, 2.45, 200, "深度 ×3"),
        Item("strata", "岩层许可", "strata", 3.0, 18, 2.50, 180, "地层 ×3"),
        Item("cart", "矿车车厢", "qty", 3.0, 14, 2.45, 200, "产量 ×3"),
        Item("pick", "镐速齿轮", "rate", 2.0, 10, 2.30, 180, "速度 ×2"),
        Item("sorter", "分拣爪", "value", 2.0, 16, 2.40, 160, "售价 ×2"),
        Item("market", "矿市特许", "market", 2.0, 22, 2.45, 140, "市价 ×2"),
        # 原常数维度
        Item("shift", "加班班次", "hours", 2.0, 20, 2.35, 100, "工时 ×2"),
        Item("chrono", "时序齿轮", "interval", 2.0, 22, 2.35, 100, "间隔 /2"),
        Item("rebate", "财税返还", "rebate", 2.0, 26, 2.40, 100, "结算 ×2"),
        # 辅助
        Item("belt", "星尘传送带", "rate", 1.5, 30, 2.35, 120, "速度 ×1.5"),
        Item("brace", "巷道支架", "depth", 1.5, 28, 2.35, 120, "深度 ×1.5"),
        Item("lamp", "巷道工灯", "qty", 1.5, 28, 2.35, 120, "产量 ×1.5"),
        Item("polish", "虹核抛光", "refine", 2.0, 40, 2.60, 40, "精矿 ×2"),
        Item("drill", "猫钻头", "rare", 1.0, 24, 2.35, 30, "稀有↑", per=1.0),
        Item("whisker", "猫须探针", "luck", 1.0, 26, 2.40, 25, "幸运↑", per=1.0),
        Item(
            "canteen", "工地罐头铺", "hybrid", 1.25, 32, 2.40, 80, "全属性 ×1.25",
            qty_m=1.25, rate_m=1.25, depth_m=1.25,
        ),
        Item("auto", "自动采购协议", "auto", 1.0, 70, 3.0, AUTO_MAX, f"自动+{AUTO_PER}/日"),
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


def manual_cap(auto_lv: int) -> int:
    return max(1, BASE_MANUAL - auto_lv // 3)


def auto_buys(auto_lv: int) -> int:
    return AUTO_PER * max(0, auto_lv)


def day_cap(auto_lv: int) -> int:
    return manual_cap(auto_lv) + auto_buys(auto_lv)


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
    spent: int = 0
    auto_today: int = 0
    total_up: int = 0
    hit_inf1: bool = False
    inf2: int = 0
    win: bool = False
    win_day: Optional[int] = None
    hist: List[dict] = field(default_factory=list)


def new_state() -> State:
    return State(lv={i.key: 0 for i in SHOP}, coins_log=math.log10(START_COINS))


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
        "rate_l": rate_l,
        "dep_l": dep_l,
        "qty_l": qty_l,
    }


def max_day_depth() -> float:
    st = new_state()
    for it in SHOP:
        if it.kind != "auto":
            st.lv[it.key] = it.max_lv
    return derive(st)["day_depth_l"]


def produce(st: State) -> Tuple[float, float, float]:
    d = derive(st)
    return d["day_coin_l"], d["day_depth_l"], d["ticks"]


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
        return 0.28
    return 0.01


def score(st: State, it: Item) -> float:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return -1e300
    if it.kind == "auto" and st.auto_today >= AUTO_PER_DAY:
        return -1e300
    c = max(clog(it, lv), 1e-12)
    s = delta_log(st, it) / c

    dlog = st.depth_log if math.isfinite(st.depth_log) else -5.0
    clog_ = st.coins_log if math.isfinite(st.coins_log) else -5.0
    depth_gap = CORE_LOG - dlog
    coin_gap = 0.0 if st.hit_inf1 else INF_LOG - clog_
    d = derive(st)
    dd = d["day_depth_l"]
    cap = day_cap(st.lv["auto"])

    # 深度不够：砸深度链 + 速度/工时/间隔
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

    if it.kind == "auto":
        refs = []
        for k in ("pick", "blast", "cart", "shift", "chrono", "strata"):
            it2 = SHOP_MAP.get(k)
            if it2 and st.lv[k] < it2.max_lv:
                refs.append(clog(it2, st.lv[k]))
        cheap = min(refs) if refs else 1.0
        rich = st.hit_inf1 or (math.isfinite(st.coins_log) and st.coins_log > cheap + 0.5)
        if rich and depth_gap > 3 and st.lv["auto"] < AUTO_MAX:
            if cap <= 12:
                s *= 9.0
            elif cap <= 40:
                s *= 5.0
            elif cap <= 100:
                s *= 2.8
            else:
                s *= 1.3
        else:
            s *= 0.18
        if st.day <= 2:
            s *= 0.12

    if it.kind in ("rare", "luck"):
        s *= 0.5 if st.total_up > 25 else 0.85
    return s


def best(st: State) -> Optional[Item]:
    b, bs = None, -1e300
    for it in SHOP:
        if st.lv[it.key] >= it.max_lv:
            continue
        if it.kind == "auto" and st.auto_today >= AUTO_PER_DAY:
            continue
        if not can_aff(st.coins_log, clog(it, st.lv[it.key]), st.hit_inf1):
            continue
        sc = score(st, it)
        if sc > bs:
            bs, b = sc, it
    return b


def buy_one(st: State, it: Item) -> bool:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return False
    if it.kind == "auto" and st.auto_today >= AUTO_PER_DAY:
        return False
    if st.spent >= day_cap(st.lv["auto"]):
        return False
    c = clog(it, lv)
    if not can_aff(st.coins_log, c, st.hit_inf1):
        return False
    if not st.hit_inf1:
        st.coins_log = sub_log(st.coins_log, c)
    st.lv[it.key] = lv + 1
    st.spent += 1
    st.total_up += 1
    if it.kind == "auto":
        st.auto_today += 1
    return True


def spend_all(st: State) -> int:
    n = 0
    for _ in range(30000):
        if st.spent >= day_cap(st.lv["auto"]):
            break
        it = best(st)
        if it is None:
            break
        if not buy_one(st, it):
            break
        n += 1
    return n


def run(verbose: bool = False) -> State:
    global SHOP, SHOP_MAP
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    st = new_state()
    for day in range(1, MAX_DAYS + 1):
        st.day = day
        st.spent = 0
        st.auto_today = 0
        cg, dg, ticks = produce(st)
        apply_income(st, cg, dg)
        bought = spend_all(st)
        d = derive(st)
        row = {
            "day": day,
            "coins": fmt(st.coins_log),
            "depth": fmt(st.depth_log),
            "cL": round(st.coins_log, 2) if math.isfinite(st.coins_log) else None,
            "dL": round(st.depth_log, 2) if math.isfinite(st.depth_log) else None,
            "bought": bought,
            "cap": day_cap(st.lv["auto"]),
            "auto": st.lv["auto"],
            "total_up": st.total_up,
            "inf2": st.inf2,
            "day_depth": round(d["day_depth_l"], 2),
            "day_coin": round(d["day_coin_l"], 2),
            "levels": {k: v for k, v in st.lv.items() if v},
        }
        st.hist.append(row)
        if verbose:
            print(
                f"D{day:02d} c={row['coins']:>10} d={row['depth']:>10} "
                f"buy={bought:3d}/{row['cap']:<3d} up={st.total_up:4d} "
                f"auto={st.lv['auto']:2d} inf2={st.inf2} dd={d['day_depth_l']:.1f}"
            )
        if st.win:
            if verbose:
                print(f"*** WIN day={day} total_up={st.total_up} ***")
            break
    return st


def summary(st: State) -> dict:
    return {
        "win": st.win,
        "win_day": st.win_day,
        "total_up": st.total_up,
        "inf2": st.inf2,
        "hit_inf1": st.hit_inf1,
        "coins": fmt(st.coins_log),
        "depth": fmt(st.depth_log),
        "depth_log": st.depth_log if math.isfinite(st.depth_log) else None,
        "levels": dict(st.lv),
        "last_day": st.hist[-1]["day"] if st.hist else 0,
        "AUTO_PER": AUTO_PER,
        "BASE_MINING_SEC": BASE_MINING_SEC,
        "max_day_depth": round(max_day_depth(), 2),
        "dims": len(SHOP),
    }


def util(st: State) -> None:
    print("\n=== 利用率 ===")
    for row in st.hist:
        if row["day"] % 5 == 0 or row["day"] <= 5 or row["day"] == st.hist[-1]["day"]:
            u = row["bought"] / max(1, row["cap"])
            print(
                f"D{row['day']:02d}: {row['bought']:3d}/{row['cap']:<3d} ({u:4.0%}) "
                f"c={row['coins']:>10} d={row['depth']:>10} auto={row['auto']} dd={row['day_depth']}"
            )


def sweep():
    global AUTO_PER, BASE_MINING_SEC
    best = None
    rows = []
    print("\n=== 扫参 ===")
    for ap in (5, 6, 7, 8):
        for ms in (1500, 1800, 2200):
            AUTO_PER = ap
            BASE_MINING_SEC = float(ms)
            st = run(False)
            s = summary(st)
            rows.append(s)
            in_w = s["win"] and s["win_day"] and WIN_LO <= s["win_day"] <= WIN_HI
            mark = " ★" if in_w else (" W" if s["win"] else "")
            print(
                f"AP={ap} MS={ms}: win={s['win']} day={s['win_day']} "
                f"up={s['total_up']} d={s['depth']}{mark}"
            )
            if s["win"]:
                if best is None or abs((s["win_day"] or 99) - 30) < abs((best["win_day"] or 99) - 30):
                    best = s
    windowed = [r for r in rows if r["win"] and r["win_day"] and WIN_LO <= r["win_day"] <= WIN_HI]
    if windowed:
        windowed.sort(key=lambda r: abs(r["win_day"] - 30))
        best = windowed[0]
    AUTO_PER = 6
    BASE_MINING_SEC = 1800.0
    return best, rows


def main():
    global SHOP, SHOP_MAP, AUTO_PER, BASE_MINING_SEC
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    mdd = max_day_depth()
    print(f"满配 day_depth_log = {mdd:.2f} (需 ≥310)")
    print("维度", len(SHOP), [i.bump for i in SHOP])
    print("cap", {lv: day_cap(lv) for lv in range(0, 12)})
    if mdd < 310:
        print("WARNING: 满配仍不够通关，请加 max 或倍率")

    print("\n=== 主模拟 ===")
    st = run(True)
    s = summary(st)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    util(st)

    best, rows = sweep()
    if best:
        AUTO_PER = best["AUTO_PER"]
        BASE_MINING_SEC = float(best["BASE_MINING_SEC"])
        print(f"\n=== 最佳 AP={AUTO_PER} MS={BASE_MINING_SEC} ===")
        st2 = run(True)
        s2 = summary(st2)
        util(st2)
    else:
        st2, s2 = st, s

    out = {
        "principle": "大胆指数；公式常数全部升级维度化",
        "constants": {
            "INF_LOG": INF_LOG,
            "CORE_LOG": CORE_LOG,
            "BASE_INTERVAL": BASE_INTERVAL,
            "BASE_MINING_SEC": BASE_MINING_SEC,
            "BASE_Q": BASE_Q,
            "BASE_DEPTH": BASE_DEPTH,
            "BASE_MANUAL": BASE_MANUAL,
            "AUTO_PER": AUTO_PER,
            "AUTO_MAX": AUTO_MAX,
            "AUTO_PER_DAY": AUTO_PER_DAY,
            "START_COINS": START_COINS,
            "max_day_depth": max_day_depth(),
            "formulas": {
                "interval": "BASE_INTERVAL / rate / chrono",
                "mining_sec": "BASE_MINING_SEC * hours",
                "depth_tick": "BASE_DEPTH * depth * strata",
                "coins_tick": "qty * E[price]*market * rebate",
                "day_gain": "log10(ticks)+tick_log",
                "day_cap": "max(1,3-auto//3)+AUTO_PER*auto",
                "win": "depth_log>=306 AND inf2>=1",
            },
        },
        "shop": [
            {
                "key": i.key,
                "label": i.label,
                "kind": i.kind,
                "mult": i.mult,
                "base": i.base,
                "growth": i.growth,
                "max_lv": i.max_lv,
                "bump": i.bump,
                "per": i.per,
                "qty_m": i.qty_m,
                "rate_m": i.rate_m,
                "depth_m": i.depth_m,
            }
            for i in build_shop()
        ],
        "summary": s2,
        "history": st2.hist,
        "sweep_wins": [
            {
                "win_day": r["win_day"],
                "total_up": r["total_up"],
                "AUTO_PER": r["AUTO_PER"],
                "BASE_MINING_SEC": r["BASE_MINING_SEC"],
            }
            for r in rows
            if r["win"]
        ],
    }
    path = r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v8_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    import shutil
    demo = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo"
    shutil.copyfile(
        r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v8_bold.py",
        demo + r"\sim_v8_bold.py",
    )
    with open(demo + r"\sim_v8_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    ok = s2["win"] and s2["win_day"] and WIN_LO <= s2["win_day"] <= WIN_HI
    print(f"\n写出 {path}")
    print("ACCEPT" if ok else "CHECK", json.dumps(s2, ensure_ascii=False))
    return s2


if __name__ == "__main__":
    main()
