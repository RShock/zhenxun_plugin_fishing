"""
猫猫乐园 v13 — 纳入全部建筑buff的真实收益计算
关键修正：
1. 鱼竿+1是全局效果，不影响乐园/主世界比例 → 忽略
2. 喵咖咖啡馆(鱼价+35%)、旋转逗猫棒(双倍鱼获10%)直接提升乐园鱼收益
3. 喵喵鱼塘(速度+18%)影响竿数，但主世界也能打窝，所以只看每竿期望
4. 先试素材价值=0，看buff后乐园鱼收益是否已经超标

计算"全建筑Lv3完工后"的乐园每竿期望，对比主世界V(rod)
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


def ef_park_raw(rod):
    """无buff的乐园鱼期望"""
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


# ═══ 建筑buff（全Lv3）═══
PRICE_BUFF = 1.35  # 喵咖咖啡馆：鱼价+35%
DOUBLE_FISH = 0.10  # 旋转逗猫棒：10%概率双倍鱼获
# 鱼竿+1是全局，忽略
# 猫爬架广场只影响材料率，不影响鱼
# 喵喵鱼塘影响速度(竿数)，不影响每竿期望

print("=" * 80)
print("  猫猫乐园 v13 — 纳入建筑buff的真实收益")
print("=" * 80)

print(f"\n  乐园鱼池均价(diff=6): {park_avg:.0f}")
print("  建筑buff（全Lv3完工后）:")
print(f"    喵咖咖啡馆: 鱼价 × {PRICE_BUFF}")
print(f"    旋转逗猫棒: {DOUBLE_FISH * 100}% 概率额外一条鱼")
print("    鱼竿+1: 全局效果，忽略")
print("    材料价值: 先设为0")


# 带buff的乐园鱼每竿期望
def ef_park_buffed(rod, D=1.0):
    """完工后带全部buff的乐园鱼期望"""
    base = ef_park_raw(rod) * D
    # 鱼价加成
    base *= PRICE_BUFF
    # 双倍鱼获：10%概率多一条鱼（多出的鱼也有价格加成）
    base *= 1 + DOUBLE_FISH
    return base


print("\n【完工后乐园鱼 vs 主世界V(rod)，D=1.0】")
print(f"  {'rod':>4} {'ef_raw':>8} {'ef_buffed':>10} {'V(rod)':>10} {'buffed/V':>10}")
print("  " + "-" * 50)
for rod in range(7, 16):
    ef_r = ef_park_raw(rod)
    ef_b = ef_park_buffed(rod)
    v = V_cache[rod]
    print(f"  {rod:>4} {ef_r:>8.1f} {ef_b:>10.1f} {v:>10.1f} {ef_b / v * 100:>9.0f}%")

print(f"""
  ┌──────────────────────────────────────────────────────────┐
  │  关键发现                                                 │
  │                                                          │
  │  buff后 ef_park/V 显著提升：                              │
  │  - rod=7:  raw 95% → buffed {ef_park_buffed(7) / V_cache[7] * 100:.0f}%             │
  │  - rod=10: raw 93% → buffed {ef_park_buffed(10) / V_cache[10] * 100:.0f}%            │
  │  - rod=11: raw 98% → buffed {ef_park_buffed(11) / V_cache[11] * 100:.0f}%            │
  │  - rod=12: raw 100% → buffed {ef_park_buffed(12) / V_cache[12] * 100:.0f}%           │
  │                                                          │
  │  buff系数 = 1.35 × 1.10 = 1.485                          │
  │  所以 buffed/V ≈ raw/V × 1.485                           │
  │                                                          │
  │  这意味着完工后乐园鱼收益已经远超主世界！                  │
  │  材料价值必须设为负数才能平衡 —— 不可能                  │
  │                                                          │
  │  唯一出路：给乐园鱼打折（D < 1.0）                       │
  └──────────────────────────────────────────────────────────┘
""")

# ═══ 求解：完工后ratio(10)=1.0 ═══
# ratio(rod) = [m×P + (1-m)×D×ef_buffed(rod)] / V(rod)
# 先试 P=0（材料无价值），求D

print(f"{'=' * 80}")
print("  求解1: P=0（材料无价值），ratio(10)=1.0 反解D")
print(f"{'=' * 80}")

# (1-m)×D×ef_buffed(10) = V(10)
# D = V(10) / [(1-m)×ef_buffed(10)]
# 但P=0意味着材料完全没用，建设无意义

ef_b10 = ef_park_buffed(10, 1.0)  # D=1时的buffed值
print(f"\n  ef_buffed(10, D=1.0) = {ef_b10:.1f}")
print(f"  V(10) = {V_cache[10]:.1f}")

for m_pct in [0, 10, 20, 30, 40, 50, 60, 70, 80]:
    m = m_pct / 100
    D = V_cache[10] / ((1 - m) * ef_b10) if (1 - m) > 0 else 0
    print(f"  m={m * 100:>3.0f}%: D={D:.3f}", end="")
    if D <= 0 or D > 2:
        print("  (不合理)")
    else:
        # 验证曲线
        ratios = {}
        for rod in range(7, 16):
            income = m * 0 + (1 - m) * D * ef_park_buffed(rod, 1.0)  # P=0
            ratios[rod] = income / V_cache[rod]
        rstr = " ".join(
            f"r{rod}={ratios[rod] * 100:.0f}%" for rod in [9, 10, 11, 12, 13]
        )
        print(f"  {rstr}")

# ═══ 求解2: 有材料价值，ratio(10)=1.0 ═══
print(f"\n{'=' * 80}")
print("  求解2: 扫描(m, D, P)，ratio(10)=1.0，验证 rod=11大幅亏")
print(f"{'=' * 80}")
print(
    f"\n  {'m':>5} {'D':>6} {'P':>8} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6}"
)
print("  " + "-" * 70)

solutions = []
for m_pct in range(5, 90, 5):
    m = m_pct / 100
    for D_x100 in range(5, 101, 5):
        D = D_x100 / 100
        # ratio(10)=1.0
        fish10 = (1 - m) * D * ef_b10
        mP = V_cache[10] - fish10
        if mP < 0:
            continue
        P = mP / m if m > 0 else 0
        if P < 0:
            continue

        ratios = {}
        for rod in range(7, 15):
            income = m * P + (1 - m) * D * ef_park_buffed(rod, 1.0)
            ratios[rod] = income / V_cache[rod]

        ok = (
            ratios[9] > 1.0
            and abs(ratios[10] - 1.0) < 0.03
            and ratios[11] < 0.95
            and ratios[12] < 0.85
        )
        if ok:
            rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(8, 15))
            solutions.append((m, D, P, ratios))
            print(f"  {m * 100:>4.0f}% {D:>6.2f} {P:>8.0f} {rstr} ★")

if solutions:
    # 选 r@11 最低
    best = min(solutions, key=lambda x: x[3][11])
    m, D, P, ratios = best
    print(f"\n  ★ 最优: m={m * 100:.0f}%, D={D:.2f}, P={P:.0f}")
    print(f"\n  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * D * ef_park_buffed(rod, 1.0)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.03 else ("平" if r > 0.97 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )
else:
    print("\n  ⚠ 无解")
    # 打印最接近的
    print("\n  最接近的方案（放宽约束）：")
    for m_pct in [20, 30, 40, 50]:
        m = m_pct / 100
        for D_x100 in [20, 30, 40, 50]:
            D = D_x100 / 100
            fish10 = (1 - m) * D * ef_b10
            mP = V_cache[10] - fish10
            if mP < 0:
                continue
            P = mP / m
            ratios = {}
            for rod in range(7, 15):
                income = m * P + (1 - m) * D * ef_park_buffed(rod, 1.0)
                ratios[rod] = income / V_cache[rod]
            rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(8, 15))
            print(f"  m={m * 100:.0f}% D={D:.2f} P={P:.0f}: {rstr}")
