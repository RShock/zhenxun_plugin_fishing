"""
猫猫乐园 v10 — 修正版：UR封顶 + 鱼竿封顶10级
关键修正：
1. 普通情况下UTR不掉落，概率合并到UR（max_rarity=UR）
2. 鱼竿最高10级，没有rod>10的情况
3. 只需要计算 rod=7~10 的收益对比
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


# ═══ UR封顶的 M(d) ═══
def calc_M_UR_capped(d):
    """UR封顶的期望乘数：UTR概率合并到UR"""
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    # N, R, SR, SSR 直接用
    for i in range(4):  # index 0-3 = N,R,SR,SSR
        key = _RARITY_KEYS[i]
        m += probs[i] * RARITY_MULTIPLIER[key]
    # UR (index 4) + 所有扩展位 (index 5+) 合并
    ur_prob = sum(probs[4:])
    m += ur_prob * RARITY_MULTIPLIER["UR"]
    return m


def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0


LOC_AVG = {loc["id"]: loc_avg_base(loc) for loc in LOCATIONS}


# ═══ V(rod) — 主世界最优收益，UR封顶，鱼竿≤10 ═══
def V_normal(rod):
    """主世界rod级鱼竿在最优地图的期望收益/竿（UR封顶）"""
    best = 0
    best_loc = None
    for loc in LOCATIONS:
        if loc["difficulty"] > rod:
            continue
        d = rod - loc["difficulty"]
        exp = LOC_AVG[loc["id"]] * calc_M_UR_capped(d)
        if exp > best:
            best = exp
            best_loc = loc
    return best, best_loc


print("=" * 80)
print("  猫猫乐园 v10 — UR封顶 + 鱼竿封顶10级（修正版）")
print("=" * 80)

print("\n【UR封顶下的 M(d) 对比（含UTR vs 不含UTR）】")
print(f"  {'d':>3} {'M_UR封顶':>10} {'M_含UTR':>10} {'差异':>8}")
print("  " + "-" * 35)
for d in range(0, 16):
    m_cap = calc_M_UR_capped(d)
    # 含UTR的M
    probs = RARITY_DISTRIBUTION[d]
    m_full = sum(
        probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]] for i in range(min(6, len(probs)))
    )
    if len(probs) > 6:
        m_full += sum(probs[6:]) * RARITY_MULTIPLIER["UTR"]
    diff = (m_cap - m_full) / m_full * 100 if m_full > 0 else 0
    print(f"  {d:>3} {m_cap:>10.3f} {m_full:>10.3f} {diff:>+7.1f}%")

print("\n【主世界 V(rod) — UR封顶】")
print(f"  {'rod':>4} {'V(rod)':>10} {'地图':>8} {'d':>4}")
print("  " + "-" * 35)
V_cache = {}
for rod in range(1, 11):
    v, loc = V_normal(rod)
    V_cache[rod] = v
    d = rod - loc["difficulty"]
    print(f"  {rod:>4} {v:>10.1f} {loc['id']:>8} {d:>4}")

# ═══ 乐园参数 ═══
PARK_DIFF = 6


def ef_park(rod):
    """乐园鱼期望：用主世界diff=6地图均价 × M_UR封顶(rod-6)"""
    d = max(0, rod - PARK_DIFF)
    # diff=6地图均价
    diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
    park_avg = (
        sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)
        if diff6_locs
        else 52
    )
    return park_avg * calc_M_UR_capped(d)


print("\n【乐园鱼 ef_park(rod) vs V(rod) — UR封顶】")
print(f"  {'rod':>4} {'ef_park':>10} {'V(rod)':>10} {'ef/V':>8}")
print("  " + "-" * 40)
for rod in range(7, 11):
    ef = ef_park(rod)
    v = V_cache[rod]
    print(f"  {rod:>4} {ef:>10.1f} {v:>10.1f} {ef / v * 100:>7.0f}%")

# ═══ 核心求解 ═══
# ratio(rod) = [m×P + (1-m)×ef_park(rod)] / V(rod)
# 约束：ratio(10) = 1.0
#   m×P + (1-m)×ef_park(10) = V(10)
#   P = [V(10) - (1-m)×ef_park(10)] / m

print(f"\n{'=' * 80}")
print("  求解：ratio(10)=1.0，扫描材料率m")
print(f"{'=' * 80}")


# 速度
def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    base = 60
    return base / (
        (1 + hook * 0.1)
        * (
            1
            + (bait_bonus + min(nest_layers, 10) * 5 + min(frame_layers, 10) * 5) / 100
        )
    )


interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

# 建造材料
BUILDING_COSTS = {
    "猫猫小木屋": {
        1: {"猫抓板木板": 6, "毛线团": 4},
        2: {"猫抓板木板": 10, "毛线团": 6},
        3: {"猫抓板木板": 15, "毛线团": 10},
    },
    "喵喵鱼塘": {
        1: {"猫抓板木板": 4, "毛线团": 6},
        2: {"猫抓板木板": 8, "毛线团": 10},
        3: {"猫抓板木板": 14, "毛线团": 14},
    },
    "猫爬架广场": {
        1: {"猫抓板木板": 7, "毛线团": 3},
        2: {"猫抓板木板": 12, "毛线团": 5},
        3: {"猫抓板木板": 18, "毛线团": 8},
    },
    "喵咖咖啡馆": {
        1: {"小铃铛": 5, "特级小鱼干": 5},
        2: {"小铃铛": 8, "特级小鱼干": 8},
        3: {"小铃铛": 13, "特级小鱼干": 13},
    },
    "旋转逗猫棒": {
        1: {"小铃铛": 4, "特级小鱼干": 6},
        2: {"小铃铛": 7, "特级小鱼干": 10},
        3: {"小铃铛": 11, "特级小鱼干": 16},
    },
    "猫咪摩天轮": {
        1: {"小铃铛": 6, "特级小鱼干": 4},
        2: {"小铃铛": 10, "特级小鱼干": 7},
        3: {"小铃铛": 16, "特级小鱼干": 11},
    },
    "猫猫过山车": {
        1: {"水晶猫砂": 3, "彩虹逗猫棒": 2},
        2: {"水晶猫砂": 6, "彩虹逗猫棒": 4},
        3: {"水晶猫砂": 10, "彩虹逗猫棒": 7},
    },
    "水晶猫城堡": {
        1: {"水晶猫砂": 3, "彩虹逗猫棒": 2},
        2: {"水晶猫砂": 6, "彩虹逗猫棒": 4},
        3: {"水晶猫砂": 10, "彩虹逗猫棒": 7},
    },
    "传奇猫雕像": {
        1: {"水晶猫砂": 4, "彩虹逗猫棒": 3},
        2: {"水晶猫砂": 8, "彩虹逗猫棒": 6},
        3: {"水晶猫砂": 12, "彩虹逗猫棒": 8},
    },
}
total_mats = {}
for bld, levels in BUILDING_COSTS.items():
    for lv, cost in levels.items():
        for mat, qty in cost.items():
            total_mats[mat] = total_mats.get(mat, 0) + qty
TOTAL_NEEDED = sum(total_mats.values())

ef10 = ef_park(10)
print(f"  速度：{casts_24h}竿/天，建造需{TOTAL_NEEDED}个材料")
print(f"  ef_park(10)={ef10:.1f}, V(10)={V_cache[10]:.1f}")

if ef10 >= V_cache[10]:
    print("  ⚠ ef_park(10) ≥ V(10)！鱼价本身超标")
    # 这意味着材料收益需要是负的，不合理
    # 需要降低ef_park，方案：乐园鱼打折
    print("  → 需要给乐园鱼打折（D<1.0）")
    print("\n  扫描 D（鱼价折扣），ratio(10)=1.0 反解 P：\n")
else:
    print("  ef_park(10) < V(10)，材料可补足差额\n")

# 扫描 D 和 m
print(
    f"  {'m':>5} {'D':>5} {'P':>8} {'建天':>5} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6}"
)
print("  " + "-" * 55)

for m_pct in [8, 10, 12, 15, 18, 20, 25, 30]:
    m = m_pct / 100
    for D_x100 in [30, 50, 70, 80, 90, 100]:
        D = D_x100 / 100
        fish10 = (1 - m) * D * ef10
        mP = V_cache[10] - fish10
        if mP < 0:
            continue
        P = mP / m
        if P < 0:
            continue
        build_days = TOTAL_NEEDED / (casts_24h * m)

        ratios = {}
        for rod in range(7, 11):
            ratios[rod] = (m * P + (1 - m) * D * ef_park(rod)) / V_cache[rod]

        rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(7, 11))
        print(f"  {m * 100:>4.0f}% {D:>5.2f} {P:>8.0f} {build_days:>5.0f} {rstr}")
    print()

# ═══ 详细方案 ═══
print(f"{'=' * 80}")
print("  ★ 推荐方案（只看 rod 7~10）")
print(f"{'=' * 80}")

# 选几个代表性方案
for m, D in [
    (0.15, 0.70),
    (0.15, 1.00),
    (0.18, 0.70),
    (0.18, 1.00),
    (0.20, 0.80),
    (0.20, 1.00),
]:
    fish10 = (1 - m) * D * ef10
    mP = V_cache[10] - fish10
    if mP < 0:
        print(f"\n  m={m * 100:.0f}%, D={D}: 无解（鱼价超标）")
        continue
    P = mP / m
    build_days = TOTAL_NEEDED / (casts_24h * m)

    print(f"\n  ── m={m * 100:.0f}%, D={D:.2f}, P={P:.0f}, 建设{build_days:.0f}天 ──")
    print(f"  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 11):
        income = m * P + (1 - m) * D * ef_park(rod)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.05 else ("平" if r > 0.95 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )

# ═══ 关键洞察 ═══
print(f"\n{'=' * 80}")
print("  关键洞察")
print(f"{'=' * 80}")
print(f"""
  1. 鱼竿封顶10级，所以"rod=10持平"是最终态，没有"rod=11亏"的场景
     玩家鱼竿升到10就到顶了，乐园收益始终≈V(10)

  2. UR封顶后，ef_park(rod) 的增长形状：
     rod=7: ef={ef_park(7):.0f}
     rod=10: ef={ef_park(10):.0f}
     V(7)={V_cache[7]:.0f} → V(10)={V_cache[10]:.0f}

  3. 真正的"自然离开"机制：
     玩家鱼竿升到10级后，乐园收益=V(10)持平
     但玩家会获得更好的鱼饵/鱼钩/打窝，在主世界效率更高
     或者主世界开放新地图/新活动，自然转移

  4. 如果要让玩家"主动离开"，需要另一个机制：
     - 活动限时（20天后关闭）
     - 或完成后收益固定不再随rod增长（而主世界rod=10后可以去更高难度地图）
""")
