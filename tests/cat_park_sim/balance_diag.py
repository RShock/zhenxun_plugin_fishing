"""
猫猫乐园 v5 — 诊断增长率矛盾，找出 rod=7~10 之间到底卡在哪
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

def calc_M(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        m += probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]]
    if len(probs) > len(_RARITY_KEYS):
        m += sum(probs[len(_RARITY_KEYS):]) * RARITY_MULTIPLIER["UTR"]
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
        exp = LOC_AVG[loc["id"]] * calc_M(rod - loc["difficulty"])
        if exp > best:
            best = exp
    return best

V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
RARITY_BASE = {"N": 8, "R": 22, "SR": 55, "SSR": 120, "UR": 220, "UTR": 400}
SCENE_MULT = 1 + PARK_DIFF * 0.3
FISH_MULT_AVG = 1.45

def E_fish_park_raw(rod):
    """折扣=1.0时的乐园鱼期望"""
    d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    total = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        r = _RARITY_KEYS[i]
        total += probs[i] * RARITY_BASE[r] * SCENE_MULT * FISH_MULT_AVG
    if len(probs) > len(_RARITY_KEYS):
        total += sum(probs[len(_RARITY_KEYS):]) * RARITY_BASE["UTR"] * SCENE_MULT * FISH_MULT_AVG
    return total

print("=" * 80)
print("  诊断：乐园鱼 vs 主世界 增长率对比")
print("=" * 80)

print(f"\n{'rod':>4} {'乐园鱼(raw)':>12} {'乐园/V':>8} {'V(rod)':>10} {'乐园增长':>10} {'V增长':>10}")
print("-" * 60)
prev_ef = 0
prev_v = 0
for rod in range(7, 16):
    ef = E_fish_park_raw(rod)
    v = V_cache[rod]
    ef_grow = (ef/prev_ef - 1) * 100 if prev_ef > 0 else 0
    v_grow = (v/prev_v - 1) * 100 if prev_v > 0 else 0
    print(f"{rod:>4} {ef:>12.1f} {ef/v*100:>7.0f}% {v:>10.1f} {ef_grow:>9.0f}% {v_grow:>9.0f}%")
    prev_ef = ef
    prev_v = v

print(f"\n{'='*80}")
print(f"  矛盾根源分析")
print(f"{'='*80}")

print(f"""
  乐园鱼 raw 从 rod=7→10: {E_fish_park_raw(7):.0f} → {E_fish_park_raw(10):.0f}  增长 {(E_fish_park_raw(10)/E_fish_park_raw(7)-1)*100:.0f}%
  主世界 V  从 rod=7→10: {V_cache[7]:.0f} → {V_cache[10]:.0f}  增长 {(V_cache[10]/V_cache[7]-1)*100:.0f}%

  问题：乐园鱼增长({(E_fish_park_raw(10)/E_fish_park_raw(7)-1)*100:.0f}%) > 主世界增长({(V_cache[10]/V_cache[7]-1)*100:.0f}%)
  
  这意味着：如果 rod=7 时把乐园压到 50%V(7)，
  那么到 rod=10 时，乐园鱼部分自然涨到的比例 = 50% × {(E_fish_park_raw(10)/E_fish_park_raw(7)):.2f} / {(V_cache[10]/V_cache[7]):.2f} = {50 * (E_fish_park_raw(10)/E_fish_park_raw(7)) / (V_cache[10]/V_cache[7]):.0f}%V(10)
  
  鱼的部分就已经超过 100%V(10) 了！再加材料收益，rod=10根本不可能刚好=100%V。
""")  # noqa

print(f"{'='*80}")
print(f"  可行方案：放宽 rod=7 的约束")
print(f"{'='*80}")

# 既然 rod=7=50% 和 rod=10=100% 矛盾，
# 那么找出：如果要求 rod=10=100%V，rod=7 最低能到多少？
# 
# rod=10: m×P + (1-m)×D×ef10 = V(10)
# rod=7:  m×P + (1-m)×D×ef7  = ?×V(7)
# 
# 两式相减: (1-m)×D×(ef10-ef7) = V(10) - ?×V(7)
# 给定 ?=ratio7，解 (1-m)×D:
#   (1-m)×D = [V(10) - ratio7×V(7)] / (ef10-ef7)
# 然后需要 m×P ≥ 0 且 D 合理

ef7 = E_fish_park_raw(7)
ef10 = E_fish_park_raw(10)

print(f"\n  若固定 rod=10 = 100%V(10)，扫描 rod=7 的可达比例：")
print(f"  {'r@7目标':>8} {'(1-m)D':>8} {'m×P':>8} {'可行性':>8}")
for r7_target_pct in range(50, 101, 5):
    r7 = r7_target_pct / 100
    one_minus_m_D = (V_cache[10] - r7 * V_cache[7]) / (ef10 - ef7)
    # m×P = V(10) - (1-m)×D×ef10 = V(10) - one_minus_m_D × ef10
    mP = V_cache[10] - one_minus_m_D * ef10
    feasible = "✓" if (one_minus_m_D > 0 and mP >= 0) else "✗"
    print(f"  {r7_target_pct:>7.0f}% {one_minus_m_D:>8.3f} {mP:>8.1f} {feasible:>8}")

print(f"\n  结论：rod=10=100%V 时，rod=7 最低只能到 ≈85%V")
print(f"  （因为乐园鱼增长比主世界快，压不下去）")

# ═══ 换一个思路：固定 rod=7=50%，看 rod=10 最低能到多少 ═══
print(f"\n{'='*80}")
print(f"  反向：固定 rod=7 = 50%V(7)，看 rod=10 最低能到多少")
print(f"{'='*80}")

# rod=7: m×P + (1-m)×D×ef7 = 0.5×V(7)
# 要让 rod=10 最低，需要让 D 尽量小（鱼价尽量低）
# 极限 D→0: m×P = 0.5×V(7)，rod=10: m×P = 0.5×V(7) → ratio = 0.5×V(7)/V(10)
r10_min = 0.5 * V_cache[7] / V_cache[10]
print(f"\n  极限情况（D→0，纯材料收益）：")
print(f"  rod=10 最低 = 0.5×V(7)/V(10) = {r10_min*100:.0f}%V(10)")
print(f"  但这要求材料率=100%（不钓鱼），不现实")

# 实际可行：m<100%，扫描
print(f"\n  扫描不同材料率下，rod=7=50%V 时各rod的ratio：")
print(f"  {'m':>6} {'D':>6} {'P':>8} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6}")
print("  " + "-" * 60)

results = []
for m_pct in range(20, 96, 5):
    m = m_pct / 100
    # rod=7: m×P + (1-m)×D×ef7 = 0.5×V(7)
    # 两个未知数(P,D)一个方程，需要另一个约束
    # 令 P=0（材料不值钱，纯靠压制鱼价）看D
    D_if_P0 = (0.5 * V_cache[7]) / ((1-m) * ef7)
    if D_if_P0 > 3 or D_if_P0 < 0.05:
        continue

    # P=0时各rod的ratio
    ratios = {}
    for rod in range(7, 14):
        ef = E_fish_park_raw(rod) * D_if_P0
        income = (1-m) * ef  # P=0
        ratios[rod] = income / V_cache[rod]

    results.append((m, D_if_P0, 0, ratios))
    rstr = " ".join(f"{ratios[r]*100:>5.0f}%" for r in range(7, 13))
    print(f"  {m*100:>5.0f}% {D_if_P0:>6.2f} {'P=0':>8} {rstr}")

print(f"\n  观察：即使 P=0（材料一文不值），rod=10 仍然 > 50%V")
print(f"  原因：乐园鱼 raw 本身就是 V 的 ~77%，打5折后还有38%")

# ═══ 真正的解法：降低乐园鱼的基础价 ═══
print(f"\n{'='*80}")
print(f"  解法：调整乐园鱼基础价格表")
print(f"{'='*80}")

print(f"""
  当前乐园鱼基础价: N=8 R=22 SR=55 SSR=120 UR=220 UTR=400
  这些价格 × SCENE_MULT(2.8) × FISH_MULT(1.45) 后，
  乐园鱼raw在 rod=7 时 = {ef7:.0f}，已是 V(7)={V_cache[7]:.0f} 的 {ef7/V_cache[7]*100:.0f}%

  要实现 rod=7=50%V，需要把乐园鱼基础价大幅降低。
  但降太低会导致完成后鱼收益不够，无法靠材料补到 120%V。

  真正的矛盾：乐园鱼和主世界鱼用同一张概率表，增长率一致。
  差别在于：乐园有固定的难度6，主世界玩家会去更高难度关卡。
  
  rod=7 时：乐园d=1，主世界最优也是d=1（去diff=6关卡）→ 增长率几乎一样
  rod=10时：乐园d=4，主世界最优也是d=4（去diff=6关卡）→ 增长率还是一样
  
  核心问题：主世界关卡7(diff=6)和乐园(diff=6)是同难度，
  所以乐园鱼/V(rod)几乎不随rod变化！
""")

# 验证
print(f"  乐园鱼/V(rod) 随rod的变化（基础价相同的情况下）：")
for rod in range(7, 16):
    ef = E_fish_park_raw(rod)
    v = V_cache[rod]
    print(f"  rod={rod}: 乐园鱼/V = {ef/v*100:.0f}%")
