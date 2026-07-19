"""
猫猫乐园 v18 — 无过滤，全量打印
看清楚P=50/100时D到底能到多少
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from constants import RARITY_DISTRIBUTION, RARITY_MULTIPLIER, _RARITY_KEYS

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
with open(CONFIG_DIR / "fish.json", encoding="utf-8") as f:
    FISH = {fi["id"]: fi["base_price"] for fi in json.load(f)["fish"]}
with open(CONFIG_DIR / "locations.json", encoding="utf-8") as f:
    LOCATIONS = json.load(f)["locations"]

def calc_M_UR(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    for i in range(4):
        m += probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]]
    m += sum(probs[4:]) * RARITY_MULTIPLIER["UR"]
    return m

def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0

LOC_AVG = {loc["id"]: loc_avg_base(loc) for loc in LOCATIONS}

def V_normal(rod):
    best = 0
    for loc in LOCATIONS:
        if loc["difficulty"] > rod: continue
        exp = LOC_AVG[loc["id"]] * calc_M_UR(rod - loc["difficulty"])
        if exp > best: best = exp
    return best

V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)

# buff（全Lv3）
CASTLE_PROB = 0.30
PRICE_MULT = 1.10
DOUBLE_MULT = 1.05
WEATHER_BOOST = 1.04
SPEED_MULT = 1.10
BAIT_SAVE = 1.01
DAILY_MULT = PRICE_MULT * DOUBLE_MULT * WEATHER_BOOST * SPEED_MULT * BAIT_SAVE

def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)

def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)

def ef_park_daily(rod, D=1.0):
    return ef_castle(rod) * D * DAILY_MULT

ef_d10 = ef_park_daily(10, 1.0)

print(f"  DAILY_MULT = {DAILY_MULT:.3f}")
print(f"  ef_daily(10, D=1) = {ef_d10:.1f}")
print(f"  V(10) = {V_cache[10]:.1f}")
print(f"  即使D=1鱼收益是V的 {ef_d10/V_cache[10]*100:.0f}%")

# ═══ 核心逻辑 ═══
# 固定P, D，求ratio(10)=1.0所需的材料率m
# m×P + (1-m)×D×ef_d10 = V(10)
# m = [V(10) - D×ef_d10] / [P - D×ef_d10]

def solve_m(D, P):
    """给定D和P，求ratio(10)=1.0的材料率m"""
    num = V_cache[10] - D * ef_d10
    den = P - D * ef_d10
    if abs(den) < 0.001:
        return None
    m = num / den
    return m

def calc_ratios(m, D, P):
    ratios = {}
    for rod in range(7, 16):
        income = m*P + (1-m)*D*ef_park_daily(rod, 1.0)
        ratios[rod] = income / V_cache[rod]
    return ratios

print(f"\n{'='*90}")
print(f"  全量扫描（无过滤）")
print(f"{'='*90}")

for target_P in [50, 100, 150, 200]:
    print(f"\n{'─'*90}")
    print(f"  P = {target_P}")
    print(f"{'─'*90}")
    print(f"  {'D':>5} {'m':>6} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6} {'r@15':>6}")
    print("  " + "-" * 80)

    for D_x100 in range(50, 100, 2):
        D = D_x100 / 100
        m = solve_m(D, target_P)
        if m is None or m < 0 or m > 0.95:
            continue
        ratios = calc_ratios(m, D, target_P)
        rstr = " ".join(f"{ratios[r]*100:>5.0f}%" for r in range(7, 16))
        mark = ""
        if ratios[9] > 1.0 and abs(ratios[10]-1.0) < 0.03 and ratios[11] < 0.95:
            mark = " ★"
            if ratios[12] < 0.85:
                mark = " ★★"
        print(f"  {D:>5.2f} {m*100:>5.0f}% {rstr}{mark}")

# ═══ 重点方案 ═══
print(f"\n{'='*90}")
print(f"  重点方案详情")
print(f"{'='*90}")

# 选几个满足 r@9>100, r@10≈100, r@11<95% 的
def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    return 60 / ((1 + hook*0.1) * (1 + (bait_bonus + min(nest_layers,10)*5 + min(frame_layers,10)*5)/100))
interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

shown = 0
for target_P in [50, 100, 150]:
    for D_x100 in range(74, 96, 2):
        D = D_x100 / 100
        m = solve_m(D, target_P)
        if m is None or m < 0 or m > 0.95:
            continue
        ratios = calc_ratios(m, D, target_P)
        if not (ratios[9] > 1.0 and abs(ratios[10]-1.0) < 0.03 and ratios[11] < 0.95):
            continue

        mats_day = casts_24h * m
        print(f"\n  ── P={target_P}, D={D:.2f}, m={m*100:.0f}%, 材料{mats_day:.0f}个/天 ──")
        print(f"  {'rod':>4} {'乐园每天':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
        for rod in range(7, 16):
            income = m*target_P + (1-m)*D*ef_park_daily(rod, 1.0)
            r = income / V_cache[rod]
            ev = "赚" if r>1.03 else ("平" if r>0.97 else "亏")
            print(f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r*100:>7.0f}% {ev:>6}")
        shown += 1
        if shown >= 6:
            break
    if shown >= 6:
        break
