"""
猫猫乐园 v11 — rod=7~16 完整曲线，UR封顶
关键：未来开放rod=11+（活动奖励），需看rod>10时乐园vs主世界的衰减
注意：UTR只有迷途风天气才有，普通情况下UR封顶
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


# UR封顶的 M(d)
def calc_M_UR(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    for i in range(4):
        m += probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]]
    m += sum(probs[4:]) * RARITY_MULTIPLIER["UR"]  # UTR及以上全部封到UR
    return m


def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0


LOC_AVG = {loc["id"]: loc_avg_base(loc) for loc in LOCATIONS}

# 主世界最高difficulty地图
max_diff = max(loc["difficulty"] for loc in LOCATIONS)
best_locs = sorted(
    [l for l in LOCATIONS if l["difficulty"] == max_diff],
    key=lambda x: -LOC_AVG[x["id"]],
)
best_loc = best_locs[0]
best_loc_avg = LOC_AVG[best_loc["id"]]

print("=" * 80)
print("  猫猫乐园 v11 — rod=7~16完整曲线")
print("=" * 80)
print(f"\n  主世界最高地图: diff={best_loc['difficulty']} 均价={best_loc_avg:.0f}")


# V(rod)：用最高difficulty地图
def V_normal(rod):
    best = 0
    best_l = None
    for loc in LOCATIONS:
        if loc["difficulty"] > rod:
            continue
        d = rod - loc["difficulty"]
        exp = LOC_AVG[loc["id"]] * calc_M_UR(d)
        if exp > best:
            best = exp
            best_l = loc
    return best, best_l


V_cache = {}
V_loc_cache = {}
for rod in range(1, 20):
    v, loc = V_normal(rod)
    V_cache[rod] = v
    V_loc_cache[rod] = loc

# 乐园 diff=6
PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)


def ef_park(rod, D=1.0):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d) * D


# ═══ 核心：ef_park/V 的形状 ═══
print(f"\n  乐园(diff=6)均价: {park_avg:.0f}")
print("\n【ef_park(rod) vs V(rod)，D=1.0，UR封顶】")
print(
    f"  {'rod':>4} {'ef_park':>10} {'V(rod)':>10} {'ef/V':>8} {'主世界地图':>12} {'主世界d':>8} {'乐园d':>6}"
)
print("  " + "-" * 70)
for rod in range(7, 17):
    ef = ef_park(rod, 1.0)
    v, loc = V_cache[rod], V_loc_cache[rod]
    main_d = rod - loc["difficulty"] if loc else 0
    park_d = rod - PARK_DIFF
    print(
        f"  {rod:>4} {ef:>10.1f} {v:>10.1f} {ef / v * 100:>7.0f}% {loc['id'] if loc else '?':>12} {main_d:>8} {park_d:>6}"
    )

# ═══ 关键分析 ═══
print("""
  ┌─────────────────────────────────────────────────────────┐
  │  关键发现：ef_park/V 的形状                              │
  │                                                         │
  │  rod=7~10: ef/V ≈ 84~95%（乐园鱼低于主世界）            │
  │  rod=11:   ef/V ≈ 98%（接近持平）                       │
  │  rod=12+:  ef/V > 100%（乐园鱼反超主世界！）             │
  │                                                         │
  │  原因：主世界最高地图diff=9，rod升高时d增长慢           │
  │        乐园diff=6固定，rod升高时d增长快，M(d)指数增长   │
  │                                                         │
  │  例：rod=12                                             │
  │    主世界: diff=9, d=3, M(3)=2.53                       │
  │    乐园:   diff=6, d=6, M(6)=6.14                       │
  │    M(6)/M(3)=2.43倍 > 地图均价比 118/52=2.27倍          │
  │    → 乐园鱼反超！                                       │
  └─────────────────────────────────────────────────────────┘
""")

# ═══ 解决方案：必须用D<1打折 ═══
print(f"{'=' * 80}")
print("  求解：必须给乐园鱼打折，否则rod=12+会反超")
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

# 约束：ratio(10)=1.0，扫描m和D，验证 r@9>1, r@11<1, r@12<<1
print("\n  约束：ratio(10)=1.0，验证 r@9>100% 且 r@11<100% 且 r@12<100%")
print(
    f"  {'m':>5} {'D':>5} {'P':>8} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6}"
)
print("  " + "-" * 80)

solutions = []
for m_pct in range(8, 51, 2):
    m = m_pct / 100
    for D_x100 in range(10, 101, 5):
        D = D_x100 / 100
        fish10 = (1 - m) * D * ef_park(10, 1.0)
        mP = V_cache[10] - fish10
        if mP < 0:
            continue
        P = mP / m
        if P < 0:
            continue

        ratios = {}
        for rod in range(7, 15):
            ratios[rod] = (m * P + (1 - m) * D * ef_park(rod, 1.0)) / V_cache[rod]

        # 满足：9赚，10平，11亏，12亏
        ok = (
            ratios[9] > 1.0
            and abs(ratios[10] - 1.0) < 0.03
            and ratios[11] < 1.0
            and ratios[12] < 1.0
        )
        if ok:
            rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(7, 15))
            solutions.append((m, D, P, ratios))
            if m_pct % 4 == 0:  # 稀疏打印
                print(f"  {m * 100:>4.0f}% {D:>5.2f} {P:>8.0f} {rstr}")

# ═══ 最佳方案 ═══
if solutions:
    # 选 r@12 最低的（衰减最陡）
    best = min(solutions, key=lambda x: x[3][12])
    m, D, P, ratios = best

    print(f"\n{'=' * 80}")
    print("  ★ 最优方案（rod=12衰减最陡）")
    print(f"{'=' * 80}")
    print(f"  材料率 m = {m * 100:.0f}%")
    print(f"  鱼价折扣 D = {D:.2f}")
    print(f"  材料均价 P = {P:.0f} 金币/个")
    build_days = TOTAL_NEEDED / (casts_24h * m)
    print(f"  建设周期 = {build_days:.0f} 天")

    print(f"\n  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * D * ef_park(rod, 1.0)
        v = V_cache[rod]
        r = income / v
        ev = "赚" if r > 1.03 else ("平" if r > 0.97 else "亏")
        print(f"  {rod:>4} {income:>10.1f} {v:>10.1f} {r * 100:>7.0f}% {ev:>6}")

    # 几个备选
    print("\n  【备选方案对比】")
    print(
        f"  {'m':>5} {'D':>5} {'P':>8} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6}"
    )
    for s in sorted(solutions, key=lambda x: x[0])[:12]:
        m2, D2, P2, r2 = s
        print(
            f"  {m2 * 100:>4.0f}% {D2:>5.2f} {P2:>8.0f} {r2[9] * 100:>5.0f}% {r2[10] * 100:>5.0f}% {r2[11] * 100:>5.0f}% {r2[12] * 100:>5.0f}% {r2[13] * 100:>5.0f}%"
        )
else:
    print("\n  ⚠ 无解！需要调整参数")
    # 诊断：看为什么无解
    print("\n  诊断：ef_park/V 的形状（D=0.5）")
    for rod in range(7, 16):
        ef = ef_park(rod, 0.5)
        v = V_cache[rod]
        print(f"  rod={rod}: ef/V={ef / v * 100:.0f}%")
