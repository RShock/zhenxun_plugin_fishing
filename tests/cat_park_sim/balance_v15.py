"""
猫猫乐园 v15 — 全部建筑buff精确计算
修正：
- 小木屋: 3/6/10%（原5/10/15）
- 鱼塘: 3/6/10%（原5/10/18）
- 爬架: 3/6/10%（原5/10/18）
- 咖啡馆: 3/6/10%（原10/20/35）
- 逗猫棒: 1/3/5%（原3/6/10）
- 过山车: 3/6/10%（原5/10/20）
- 猫城堡: 5/15/30%（原30/60/100）

逐个分析对每竿收益的影响：
1. 咖啡馆: 鱼价乘算
2. 逗猫棒: 双倍鱼获，乘算
3. 猫城堡: 30%概率rod+1来roll稀有度 → 改变稀有度分布
4. 鱼塘: 速度加成 → 每天竿数 ×1.10（乐园独有，主世界无此buff）
5. 过山车: 天气增幅 → 间接（先简化为平均增益）
6. 小木屋: 鱼饵节省 → 降低成本（影响净收益）
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
    """UR封顶的期望乘数"""
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

# ═══ 逐层计算乐园鱼每竿期望 ═══


# Layer 1: 基础（无buff）
def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


# Layer 2: 水晶猫城堡（30%概率rod+1）
CASTLE_PROB = 0.30  # Lv3


def ef_castle(rod):
    """猫城堡修正后的期望"""
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)


# Layer 3: 喵咖咖啡馆（鱼价+10%）
PRICE_MULT = 1.10

# Layer 4: 旋转逗猫棒（双倍鱼获5%）
DOUBLE_RATE = 0.05  # Lv3削弱后
DOUBLE_MULT = 1 + DOUBLE_RATE

# Layer 5: 猫猫过山车（天气增幅10%）
# 天气平均增益：6种天气各1/6
# 晴天0%, 雨天速度+10%, 流星稀有度+2%, 暴雨鱼饵减半, 迷途风UTR, 猫吃鱼
# 过山车增幅这些效果10%，平均下来对收益的影响约+3~5%
WEATHER_BOOST = 0.04  # 估算：平均4%收益提升

# Layer 6: 喵喵鱼塘（速度+10%）→ 影响每天竿数
SPEED_MULT = 1.10

# Layer 7: 小木屋（鱼饵节省10%）→ 降低成本
# 鱼饵成本约占收益的5~10%，节省10%→净收益+0.5~1%
BAIT_SAVE = 0.01  # 估算：净收益+1%

# 综合系数（每竿毛收益）
PER_CAST_MULT = PRICE_MULT * DOUBLE_MULT * (1 + WEATHER_BOOST)

# 综合系数（每天总收益 = 每竿 × 每天竿数 × 成本节省）
DAILY_MULT = PER_CAST_MULT * SPEED_MULT * (1 + BAIT_SAVE)

print("=" * 80)
print("  猫猫乐园 v15 — 全部buff精确计算")
print("=" * 80)

print("\n【修正后的建筑数值（全Lv3）】")
print("  小木屋: 鱼饵节省 10%  (原15%)")
print("  鱼塘:   速度+10%     (原18%)")
print("  爬架:   材料率+10%   (原18%)")
print("  咖啡馆: 鱼价+10%     (原35%)")
print("  逗猫棒: 双倍鱼获5%   (原10%)")
print("  过山车: 天气增幅10%  (原20%)")
print("  猫城堡: rod+1概率30% (原100%)")

print("\n【逐层系数分解】")
print("  猫城堡(30%概率rod+1): 见下表")
print(f"  咖啡馆(鱼价×1.10):   {PRICE_MULT}")
print(f"  逗猫棒(双倍×1.05):   {DOUBLE_MULT}")
print(f"  过山车(天气~+4%):    {1 + WEATHER_BOOST}")
print("  ────────────────────")
print(f"  每竿毛收益系数:      {PER_CAST_MULT:.3f}")
print(f"  鱼塘(速度×1.10):     {SPEED_MULT} ← 每天竿数额外加成")
print(f"  小木屋(成本-1%):     {1 + BAIT_SAVE}")
print("  ────────────────────")
print(f"  每天总收益系数:      {DAILY_MULT:.3f}")

# ═══ 猫城堡的影响 ═══
print("\n【猫城堡(30% rod+1)对ef的影响】")
print(f"  {'rod':>4} {'ef_raw':>8} {'ef_castle':>10} {'提升':>8}")
for rod in range(7, 16):
    r = ef_raw(rod)
    c = ef_castle(rod)
    print(f"  {rod:>4} {r:>8.1f} {c:>10.1f} {(c / r - 1) * 100:>+7.1f}%")


# ═══ 完工后综合ef vs V ═══
def ef_park_full(rod, D=1.0):
    """完工后全部buff的每竿毛收益（不含速度，用于对比每竿）"""
    return ef_castle(rod) * D * PER_CAST_MULT


def ef_park_daily(rod, D=1.0):
    """完工后每天总收益系数（含速度+成本）"""
    return ef_park_full(rod, D) * SPEED_MULT * (1 + BAIT_SAVE)


print("\n【完工后 ef vs V(rod)，D=1.0】")
print(
    f"  {'rod':>4} {'ef_raw':>8} {'ef_castle':>10} {'ef_每竿':>10} {'ef_每天':>10} {'V':>8} {'每竿/V':>7} {'每天/V':>7}"
)
print("  " + "-" * 75)
for rod in range(7, 16):
    r = ef_raw(rod)
    c = ef_castle(rod)
    fpc = ef_park_full(rod)
    fpd = ef_park_daily(rod)
    v = V_cache[rod]
    print(
        f"  {rod:>4} {r:>8.1f} {c:>10.1f} {fpc:>10.1f} {fpd:>10.1f} {v:>8.1f} {fpc / v * 100:>6.0f}% {fpd / v * 100:>6.0f}%"
    )

# ═══ 求解：ratio_daily(10)=1.0 ═══
print(f"\n{'=' * 80}")
print("  求解：每天总收益 ratio(10)=1.0")
print("  ratio = [m×P + (1-m)×D×ef_daily(rod)] / V(rod)")
print(f"{'=' * 80}")

ef_d10 = ef_park_daily(10, 1.0)
print(
    f"\n  ef_daily(10,D=1)={ef_d10:.1f}, V(10)={V_cache[10]:.1f}, 比值={ef_d10 / V_cache[10] * 100:.0f}%"
)

if ef_d10 > V_cache[10]:
    max_D = V_cache[10] / ef_d10
    print(f"  ⚠ 即使D=1鱼价已超标！需要D≤{max_D:.2f}")

print(
    f"\n  {'m':>5} {'D':>6} {'P':>8} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6}"
)
print("  " + "-" * 70)

solutions = []
for m_pct in range(5, 90, 5):
    m = m_pct / 100
    for D_x100 in range(5, 101, 1):
        D = D_x100 / 100
        fish10 = (1 - m) * D * ef_d10
        mP = V_cache[10] - fish10
        if mP < 0:
            continue
        P = mP / m if m > 0 else 0
        if P < 0:
            continue

        ratios = {}
        for rod in range(7, 15):
            income = m * P + (1 - m) * D * ef_park_daily(rod, 1.0)
            ratios[rod] = income / V_cache[rod]

        ok = ratios[9] > 1.0 and abs(ratios[10] - 1.0) < 0.03 and ratios[11] < 0.95
        if ok:
            solutions.append((m, D, P, ratios))

# 打印
if solutions:
    seen_m = set()
    for s in sorted(solutions, key=lambda x: (x[0], x[3][11])):
        m, D, P, ratios = s
        m_key = round(m, 2)
        if m_key in seen_m:
            continue
        seen_m.add(m_key)
        rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(8, 15))
        print(f"  {m * 100:>4.0f}% {D:>6.2f} {P:>8.0f} {rstr}")

# ═══ 推荐方案 ═══
print(f"\n{'=' * 80}")
print("  推荐方案")
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

for m, D in [(0.20, 0.50), (0.30, 0.45), (0.40, 0.40), (0.50, 0.35)]:
    mP = V_cache[10] - (1 - m) * D * ef_d10
    if mP < 0:
        continue
    P = mP / m
    mats_day = casts_24h * m

    print(f"\n  ── m={m * 100:.0f}%, D={D:.2f}, P={P:.0f} ──")
    print(f"  {'rod':>4} {'乐园每天':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * D * ef_park_daily(rod, 1.0)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.03 else ("平" if r > 0.97 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )
