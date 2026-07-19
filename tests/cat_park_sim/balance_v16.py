"""
猫猫乐园 v16 — D=0.8 固定，材料价格大幅削弱
目标：r@9>100%, r@10≈100%, r@11<95%, r@12<85%
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from constants import _RARITY_KEYS, RARITY_DISTRIBUTION, RARITY_MULTIPLIER

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
        if loc["difficulty"] > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M_UR(rod - loc["difficulty"])
        if exp > best:
            best = exp
    return best


V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)

# buff（全Lv3完工后）
CASTLE_PROB = 0.30
PRICE_MULT = 1.10
DOUBLE_MULT = 1.05
WEATHER_BOOST = 1.04
SPEED_MULT = 1.10
BAIT_SAVE = 1.01

PER_CAST_MULT = PRICE_MULT * DOUBLE_MULT * WEATHER_BOOST
DAILY_MULT = PER_CAST_MULT * SPEED_MULT * BAIT_SAVE


def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)


def ef_park_daily(rod, D=1.0):
    return ef_castle(rod) * D * DAILY_MULT


# ═══ D=0.8 固定 ═══
D_FIXED = 0.80

print("=" * 80)
print(f"  猫猫乐园 v16 — D={D_FIXED} 固定，材料价格大幅削弱")
print("=" * 80)

ef_d10 = ef_park_daily(10, D_FIXED)
print(f"\n  ef_daily(10, D={D_FIXED}) = {ef_d10:.1f}")
print(f"  V(10) = {V_cache[10]:.1f}")
print(f"  鱼收益占比 = {ef_d10 / V_cache[10] * 100:.0f}%")
print(
    f"  材料需补 = {V_cache[10] - ef_d10:.1f} ( {'正' if V_cache[10] > ef_d10 else '负'} )"
)

if ef_d10 > V_cache[10]:
    print(f"\n  ⚠ D={D_FIXED}时鱼收益已经超标！")
    print("  材料价格必须为负数才能平衡 → 不可能")
    print(f"  最大可接受D = {V_cache[10] / ef_park_daily(10, 1.0) * 1.0:.2f}")
else:
    print(f"\n  材料需要补 {V_cache[10] - ef_d10:.1f}/竿 来达到平衡")

# ═══ 扫描 ═══
print(f"\n{'=' * 80}")
print(f"  扫描材料率m，D={D_FIXED}固定，求P")
print(f"{'=' * 80}")


def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    return 60 / (
        (1 + hook * 0.1)
        * (
            1
            + (bait_bonus + min(nest_layers, 10) * 5 + min(frame_layers, 10) * 5) / 100
        )
    )


interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

print(f"\n  每24h竿数(全buff) = {casts_24h}竿")

print(
    f"\n  {'m':>5} {'P':>8} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6} {'材料/天':>7}"
)
print("  " + "-" * 75)

for m_pct in range(5, 90, 5):
    m = m_pct / 100
    # ratio(10)=1.0
    fish10 = (1 - m) * ef_d10  # 注意：m是材料率，(1-m)是鱼率
    mP = V_cache[10] - fish10
    if mP < 0:
        # 材料价值为负 → 这组m不可行
        # 但仍打印看看
        P = mP / m if m > 0 else 0
        ratios_str = "鱼收益已超标"
    else:
        P = mP / m
        ratios = {}
        for rod in range(7, 15):
            income = m * P + (1 - m) * ef_park_daily(rod, D_FIXED)
            ratios[rod] = income / V_cache[rod]
        mats_day = casts_24h * m
        rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(7, 15))
        print(f"  {m * 100:>4.0f}% {P:>8.0f} {rstr} {mats_day:>6.0f}")

# ═══ 推荐方案 ═══
print(f"\n{'=' * 80}")
print("  推荐方案（验证曲线）")
print(f"{'=' * 80}")

# 找一个材料率适中、P合理的
for m in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
    fish10 = (1 - m) * ef_d10
    mP = V_cache[10] - fish10
    if mP < 0:
        print(f"\n  m={m * 100:.0f}%: 鱼收益已超标，材料价值需为负 → 不可行")
        continue
    P = mP / m
    mats_day = casts_24h * m

    print(
        f"\n  ── m={m * 100:.0f}%, D={D_FIXED}, P={P:.0f}, 材料{mats_day:.0f}个/天 ──"
    )
    print(f"  {'rod':>4} {'乐园每天':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * ef_park_daily(rod, D_FIXED)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.03 else ("平" if r > 0.97 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )
