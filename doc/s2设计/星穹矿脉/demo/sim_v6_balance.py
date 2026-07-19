# -*- coding: utf-8 -*-
"""
S2 星穹矿脉 · 平衡模型 v6（定稿候选）
====================================

数学
----
depth_log ≈ 2.48 + rate_log + depth_mult_log
通关需 rate_log + depth_mult_log ≳ 303.5

×2 → 0.3010/级，×1.5 → 0.1761/级，×1.25 → 0.0969/级

生产向单项安全顶 PROD_MAX 必须足够：
  2×rate(×1.5) + depth(×2) + depth(×1.5) + hybrid 部分
  在 max_lv≈360 时 pd_max ≈ 314 > 303.5

自动采购
--------
auto_buys = AUTO_PER * auto_lv          # 线性
manual    = max(1, 3 - auto_lv//3)
每天最多买 1 级 auto（防一天滚爆）
总升级次数 **无 90 硬顶**（90 仅是 30×3 手动下限参照）

∞ 后买力
--------
hit_inf1 后 coins 钉在 308，视为「可买任意标价」（预算无限）

目标
----
ROI 智能体 26–34 日通关；名额中前期打满。
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INF_LOG = 308.0
CORE_LOG = 306.0
BASE_INTERVAL = 8.0
MINING_SEC = 2400.0
BASE_MANUAL = 3
AUTO_PER = 5
AUTO_MAX = 24
AUTO_PER_DAY = 1
PROD_MAX = 360
START_COINS = 35.0
MAX_DAYS = 45
WIN_LO, WIN_HI = 26, 34
NEED_PD = 303.5

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
    M = PROD_MAX
    return [
        Item("pick", "镐速齿轮", "rate", 1.5, 10, 2.50, M, "速度 ×1.5"),
        Item("belt", "星尘传送带", "rate", 1.5, 26, 2.55, M, "速度 ×1.5"),
        Item("blast", "浅层爆破", "depth", 2.0, 14, 2.80, M, "深度 ×2"),
        Item("brace", "巷道支架", "depth", 1.5, 24, 2.60, M, "深度 ×1.5"),
        Item("cart", "矿车车厢", "qty", 2.0, 16, 2.85, M, "产量 ×2"),
        Item("lamp", "巷道工灯", "qty", 1.5, 22, 2.60, M, "产量 ×1.5"),
        Item("sorter", "分拣爪", "value", 2.0, 18, 2.90, M, "售价 ×2"),
        Item("polish", "虹核抛光", "refine", 2.0, 48, 3.05, 50, "精矿 ×2"),
        Item("drill", "猫钻头", "rare", 1.0, 30, 2.65, 35, "稀有↑", per=1.0),
        Item("whisker", "猫须探针", "luck", 1.0, 34, 2.70, 25, "幸运↑", per=1.0),
        Item(
            "canteen", "工地罐头铺", "hybrid", 1.25, 38, 2.70, 70, "全属性 ×1.25",
            qty_m=1.25, rate_m=1.25, depth_m=1.25,
        ),
        Item("auto", "自动采购协议", "auto", 1.0, 100, 3.8, AUTO_MAX, f"自动采购+{AUTO_PER}/日"),
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


def can_aff(st_coins: float, c: float, infinite_budget: bool) -> bool:
    if infinite_budget:
        return True
    return math.isfinite(c) and math.isfinite(st_coins) and st_coins + 1e-12 >= c


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
    t = min(1.0, drill / 35.0)
    lk = min(1.0, luck / 25.0)
    w = {
        "N": max(1e-9, 0.70 - 0.48 * t - 0.06 * lk),
        "R": max(1e-9, 0.20 - 0.05 * t),
        "SR": max(1e-9, 0.06 + 0.15 * t + 0.02 * lk),
        "SSR": max(1e-9, 0.025 + 0.22 * t + 0.04 * lk),
        "UR": max(1e-9, 0.015 + 0.16 * t + 0.05 * lk),
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
    total_ticks: float = 0.0
    hit_inf1: bool = False
    inf2: int = 0
    win: bool = False
    win_day: Optional[int] = None
    hist: List[dict] = field(default_factory=list)


def new_state() -> State:
    return State(lv={i.key: 0 for i in SHOP}, coins_log=math.log10(START_COINS))


def derive(st: State) -> dict:
    qty_l = rate_l = dep_l = val_l = ref_l = 0.0
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
        elif it.kind == "rare":
            drill += int(it.per * lv)
        elif it.kind == "luck":
            luck += int(it.per * lv)
        elif it.kind == "hybrid":
            qty_l += lv * math.log10(it.qty_m)
            rate_l += lv * math.log10(it.rate_m)
            dep_l += lv * math.log10(it.depth_m)
    interval = BASE_INTERVAL / max(10 ** rate_l, 1e-40)
    ticks = MINING_SEC / interval
    probs = rarity_probs(drill, luck)
    e_price = 0.0
    for r, p in probs.items():
        u = PRICE[r] * (10 ** val_l)
        if r in ("SSR", "UR"):
            u *= 10 ** ref_l
        e_price += p * u
    e_price = max(e_price, 1e-15)
    return {
        "qty_l": qty_l,
        "rate_l": rate_l,
        "dep_l": dep_l,
        "interval": interval,
        "ticks": ticks,
        "coins_tick_l": qty_l + math.log10(e_price),
        "depth_tick_l": dep_l,
        "prod_depth_l": rate_l + dep_l,
        "prod_coin_l": rate_l + qty_l + math.log10(e_price),
        "probs": probs,
    }


def max_pd_possible() -> float:
    # 粗算当前商店满级 pd
    st = new_state()
    for it in SHOP:
        if it.kind in ("rate", "depth", "hybrid"):
            st.lv[it.key] = it.max_lv
    return derive(st)["prod_depth_l"]


def produce(st: State) -> Tuple[float, float, float]:
    d = derive(st)
    t = d["ticks"]
    if t <= 0:
        return float("-inf"), float("-inf"), 0.0
    return math.log10(t) + d["coins_tick_l"], math.log10(t) + d["depth_tick_l"], t


def apply_income(st: State, cg: float, dg: float, ticks: float) -> None:
    st.coins_log = add_log(st.coins_log, cg)
    st.depth_log = add_log(st.depth_log, dg)
    if math.isfinite(st.depth_log):
        st.depth_log = min(st.depth_log, CORE_LOG)
    st.total_ticks += ticks
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
    if it.kind in ("qty", "rate", "depth", "value"):
        return math.log10(it.mult)
    if it.kind == "refine":
        phi = derive(st)["probs"]["SSR"] + derive(st)["probs"]["UR"]
        return math.log10(max(1.0001, 1.0 + phi * (it.mult - 1.0)))
    if it.kind == "hybrid":
        return math.log10(it.qty_m) + math.log10(it.rate_m) + 0.5 * math.log10(it.depth_m)
    if it.kind == "rare":
        return 0.028
    if it.kind == "luck":
        return 0.02
    if it.kind == "auto":
        return 0.22
    return 0.01


def score(st: State, it: Item) -> float:
    lv = st.lv[it.key]
    if lv >= it.max_lv:
        return -1e300
    if it.kind == "auto" and st.auto_today >= AUTO_PER_DAY:
        return -1e300

    c = max(clog(it, lv), 1e-12)
    # ∞ 预算时用「虚拟成本」压低超贵项乱买？仍用真实 cost 做 ROI
    s = delta_log(st, it) / c

    dlog = st.depth_log if math.isfinite(st.depth_log) else -5.0
    clog_ = st.coins_log if math.isfinite(st.coins_log) else -5.0
    depth_gap = CORE_LOG - dlog
    coin_gap = 0.0 if st.hit_inf1 else (INF_LOG - clog_)
    d = derive(st)
    pd, pc = d["prod_depth_l"], d["prod_coin_l"]
    cap = day_cap(st.lv["auto"])

    if pd < NEED_PD - 2:
        if it.kind == "depth":
            s *= 3.2 + min(2.5, depth_gap / 90.0)
        elif it.kind == "rate":
            s *= 2.6 + min(2.0, depth_gap / 110.0)
        elif it.kind == "hybrid":
            s *= 1.9
        elif it.kind in ("qty", "value"):
            s *= 0.9 + min(1.2, max(0.0, coin_gap) / 250.0)
        elif it.kind == "refine":
            s *= 0.4
    else:
        # 深度乘区够：冲币 / 补深度展示
        if depth_gap > 1 and it.kind in ("depth", "rate"):
            s *= 2.0
        if it.kind in ("qty", "value", "rate"):
            s *= 2.2 + min(2.0, max(0.0, coin_gap) / 120.0)
        if it.kind == "depth" and depth_gap < 1:
            s *= 0.2
        if it.kind == "refine":
            s *= 1.1

    if it.kind == "auto":
        refs = []
        for k in ("pick", "blast", "cart", "brace", "belt"):
            it2 = SHOP_MAP[k]
            if st.lv[k] < it2.max_lv:
                refs.append(clog(it2, st.lv[k]))
        cheap = min(refs) if refs else 1.0
        rich = st.hit_inf1 or (math.isfinite(st.coins_log) and st.coins_log > cheap + 0.7)
        if rich and pd < NEED_PD + 10 and st.lv["auto"] < AUTO_MAX:
            if cap <= 12:
                s *= 7.0
            elif cap <= 40:
                s *= 4.0
            elif cap <= 80:
                s *= 2.5
            else:
                s *= 1.2
        else:
            s *= 0.18
        if st.day <= 3:
            s *= 0.12
        if st.lv["auto"] >= AUTO_MAX:
            s = -1e300

    if it.kind in ("rare", "luck"):
        s *= 0.5 if st.total_up > 25 else 0.85

    return s


def best(st: State) -> Optional[Item]:
    b, bs = None, -1e300
    inf_b = st.hit_inf1
    for it in SHOP:
        if st.lv[it.key] >= it.max_lv:
            continue
        if it.kind == "auto" and st.auto_today >= AUTO_PER_DAY:
            continue
        if not can_aff(st.coins_log, clog(it, st.lv[it.key]), inf_b):
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
    # ∞ 预算不扣款
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
        apply_income(st, cg, dg, ticks)
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
            "pd": round(d["prod_depth_l"], 2),
            "pc": round(d["prod_coin_l"], 2),
            "levels": {k: v for k, v in st.lv.items() if v},
        }
        st.hist.append(row)
        if verbose:
            print(
                f"D{day:02d} c={row['coins']:>10} d={row['depth']:>10} "
                f"buy={bought:3d}/{row['cap']:<3d} up={st.total_up:4d} "
                f"auto={st.lv['auto']:2d} inf2={st.inf2} pd={d['prod_depth_l']:.1f}"
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
        "MINING_SEC": MINING_SEC,
        "PROD_MAX": PROD_MAX,
        "max_pd": round(max_pd_possible(), 2),
    }


def util(st: State) -> None:
    print("\n=== 利用率 ===")
    for row in st.hist:
        if row["day"] % 5 == 0 or row["day"] <= 5 or row["day"] == st.hist[-1]["day"]:
            u = row["bought"] / max(1, row["cap"])
            print(
                f"D{row['day']:02d}: {row['bought']:3d}/{row['cap']:<3d} ({u:4.0%}) "
                f"c={row['coins']:>10} d={row['depth']:>10} auto={row['auto']} pd={row['pd']}"
            )


def sweep():
    global AUTO_PER, MINING_SEC, PROD_MAX
    best = None
    rows = []
    print("\n=== 扫参 ===")
    for ap in (4, 5, 6, 7):
        for ms in (2200, 2400, 2600):
            for pm in (340, 360, 380):
                AUTO_PER = ap
                MINING_SEC = float(ms)
                PROD_MAX = pm
                st = run(False)
                s = summary(st)
                rows.append(s)
                in_w = s["win"] and s["win_day"] and WIN_LO <= s["win_day"] <= WIN_HI
                if s["win"] or (ap == 5 and ms == 2400):
                    mark = " ★" if in_w else (" W" if s["win"] else "")
                    print(
                        f"AP={ap} MS={ms} PM={pm}: win={s['win']} day={s['win_day']} "
                        f"up={s['total_up']} d={s['depth']}{mark}"
                    )
                if in_w:
                    if best is None or abs(s["win_day"] - 30) < abs(best["win_day"] - 30):
                        best = s
    wins = [r for r in rows if r["win"] and r["win_day"]]
    if not best and wins:
        wins.sort(key=lambda r: abs(r["win_day"] - 30))
        best = wins[0]
    elif wins:
        # 也考虑窗口外但更近 30
        wins.sort(key=lambda r: abs(r["win_day"] - 30))
        if best is None or abs(wins[0]["win_day"] - 30) < abs(best["win_day"] - 30):
            # 若 best 在窗口内则保留
            if not (best and WIN_LO <= best["win_day"] <= WIN_HI):
                best = wins[0]
    AUTO_PER, MINING_SEC, PROD_MAX = 5, 2400.0, 360
    return best, rows


def main():
    global SHOP, SHOP_MAP, AUTO_PER, MINING_SEC, PROD_MAX
    SHOP = build_shop()
    SHOP_MAP = {i.key: i for i in SHOP}
    print("max_pd@", PROD_MAX, "=", max_pd_possible())
    print("cap", {lv: day_cap(lv) for lv in range(0, 16)})
    print("=== 主模拟 ===")
    st = run(True)
    s = summary(st)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    util(st)

    best, rows = sweep()
    if best:
        AUTO_PER = best["AUTO_PER"]
        MINING_SEC = float(best["MINING_SEC"])
        PROD_MAX = best["PROD_MAX"]
        print(f"\n=== 最佳 AP={AUTO_PER} MS={MINING_SEC} PM={PROD_MAX} ===")
        st2 = run(True)
        s2 = summary(st2)
        util(st2)
    else:
        st2, s2 = st, s

    out = {
        "constants": {
            "INF_LOG": INF_LOG,
            "CORE_LOG": CORE_LOG,
            "BASE_INTERVAL": BASE_INTERVAL,
            "MINING_SEC": MINING_SEC,
            "BASE_MANUAL": BASE_MANUAL,
            "AUTO_PER": AUTO_PER,
            "AUTO_MAX": AUTO_MAX,
            "AUTO_PER_DAY": AUTO_PER_DAY,
            "PROD_MAX": PROD_MAX,
            "START_COINS": START_COINS,
            "NEED_PD": NEED_PD,
            "formulas": {
                "depth_log_day": "log10(MINING_SEC * rate_mult) + depth_mult_log",
                "depth_log_approx": "2.48 + rate_log + depth_mult_log",
                "cost_log": "log10(base)+lv*log10(growth)",
                "auto_buys": "AUTO_PER * auto_lv",
                "manual_cap": "max(1, 3 - auto_lv//3)",
                "day_cap": "manual + auto_buys",
                "auto_daily_limit": AUTO_PER_DAY,
                "win": "depth_log>=306 AND inf2>=1",
                "note_90": "90 = 30d*3 manual floor only; auto required by math for 1e306",
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
            {k: r[k] for k in ("win", "win_day", "total_up", "AUTO_PER", "MINING_SEC", "PROD_MAX", "depth", "coins")}
            for r in rows
            if r["win"]
        ],
    }
    path = r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v6_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    # 权威副本进设计目录
    auth = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo\sim_v6_balance.py"
    import shutil
    shutil.copyfile(
        r"c:\Users\Administrator\.trae-cn\work\6a584105b24b279bd2fd84a9\sim_v6_balance.py",
        auth,
    )
    res_auth = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\doc\s2设计\星穹矿脉\demo\sim_v6_result.json"
    with open(res_auth, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n写出 {path}\n权威 {auth}")
    ok = s2["win"] and s2["win_day"] and WIN_LO <= s2["win_day"] <= WIN_HI
    print("ACCEPT" if ok else "CHECK", json.dumps(s2, ensure_ascii=False))
    return s2


if __name__ == "__main__":
    main()
