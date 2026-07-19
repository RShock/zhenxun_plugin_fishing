"""
猫猫乐园 v14 — 建筑数值修正后重新计算
修正：喵咖咖啡馆 鱼价 3/6/10%（原10/20/35）
其他建筑保持不变，综合评估完工后真实收益
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
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


# ═══ 修正后的建筑buff（全Lv3完工后）═══
PRICE_BUFF = 1.10  # 喵咖咖啡馆：鱼价+10%（修正！原35%）
DOUBLE_FISH = 0.10  # 旋转逗猫棒：10%双倍鱼获
BUFF_COEFF = PRICE_BUFF * (1 + DOUBLE_FISH)  # 综合系数

print("=" * 80)
print("  猫猫乐园 v14 — 建筑数值修正（咖啡馆3/6/10%）")
print("=" * 80)

print(f"\n  修正后buff系数 = {PRICE_BUFF} × {1 + DOUBLE_FISH} = {BUFF_COEFF}")
print("  （之前是 1.35 × 1.10 = 1.485）")


def ef_park_buffed(rod, D=1.0):
    return ef_park_raw(rod) * D * BUFF_COEFF


print("\n【完工后 ef_park_buffed vs V(rod)，D=1.0】")
print(f"  {'rod':>4} {'ef_raw':>8} {'ef_buffed':>10} {'V(rod)':>10} {'buffed/V':>10}")
print("  " + "-" * 50)
for rod in range(7, 16):
    ef_r = ef_park_raw(rod)
    ef_b = ef_park_buffed(rod)
    v = V_cache[rod]
    print(f"  {rod:>4} {ef_r:>8.1f} {ef_b:>10.1f} {v:>10.1f} {ef_b / v * 100:>9.0f}%")

# ═══ 求解 ═══
print(f"\n{'=' * 80}")
print("  求解：ratio(10)=1.0，扫描(m, D, P)")
print("  约束：r@9>100%, r@10≈100%, r@11<95%, r@12<85%")
print(f"{'=' * 80}")

ef_b10 = ef_park_buffed(10, 1.0)
print(
    f"\n  ef_buffed(10,D=1)={ef_b10:.1f}, V(10)={V_cache[10]:.1f}, 比值={ef_b10 / V_cache[10] * 100:.0f}%"
)

print(
    f"\n  {'m':>5} {'D':>6} {'P':>8} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6}"
)
print("  " + "-" * 70)

solutions = []
for m_pct in range(5, 90, 5):
    m = m_pct / 100
    for D_x100 in range(10, 101, 5):
        D = D_x100 / 100
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

# 按m分组打印，每组只打印r@11最低的
if solutions:
    seen_m = set()
    for s in sorted(solutions, key=lambda x: (x[0], x[3][11])):
        m, D, P, ratios = s
        if m in seen_m:
            continue
        seen_m.add(m)
        rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(8, 15))
        print(f"  {m * 100:>4.0f}% {D:>6.2f} {P:>8.0f} {rstr} ★")

# ═══ 推荐方案 ═══
print(f"\n{'=' * 80}")
print("  推荐方案（P适中、建设周期合理）")
print(f"{'=' * 80}")


# 速度
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

# 建造材料（当前）
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

# 选3个代表方案
for m, D in [(0.30, 0.80), (0.40, 0.70), (0.50, 0.60), (0.60, 0.50)]:
    mP = V_cache[10] - (1 - m) * D * ef_b10
    if mP < 0:
        continue
    P = mP / m
    mats_day = casts_24h * m
    build_days = TOTAL_NEEDED / mats_day

    print(
        f"\n  ── m={m * 100:.0f}%, D={D:.2f}, P={P:.0f}, 材料{mats_day:.0f}个/天, 建设{build_days:.0f}天 ──"
    )
    print(f"  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * D * ef_park_buffed(rod, 1.0)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.03 else ("平" if r > 0.97 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )

# ═══ 建筑效果总览（修正后）═══
print(f"\n{'=' * 80}")
print("  9个建筑效果总览（修正后）")
print(f"{'=' * 80}")
print(f"  {'#':>2} {'建筑':<12} {'效果':<20} {'Lv1':>6} {'Lv2':>6} {'Lv3':>6}")
print("  " + "-" * 55)
buildings = [
    (1, "猫猫小木屋", "鱼饵节省概率", "5%", "10%", "15%"),
    (2, "喵喵鱼塘", "钓鱼速度加成", "+5%", "+10%", "+18%"),
    (3, "猫爬架广场", "材料掉率加成", "+5%", "+10%", "+18%"),
    (4, "喵咖咖啡馆", "鱼出售价格加成", "+3%", "+6%", "+10%"),  # ←修正
    (5, "旋转逗猫棒", "双倍鱼获概率", "3%", "6%", "10%"),
    (6, "猫咪摩天轮", "每日签到抽数", "1抽", "2抽", "3抽"),
    (7, "猫猫过山车", "天气效果增幅", "5%", "10%", "20%"),
    (8, "水晶猫城堡", "钓鱼等级+1概率", "30%", "60%", "100%"),
    (9, "传奇猫雕像", "门控+解锁+鱼竿+1", "解锁Lv2", "解锁Lv3", "鱼竿+1"),
]
for b in buildings:
    print(f"  {b[0]:>2} {b[1]:<12} {b[2]:<20} {b[3]:>6} {b[4]:>6} {b[5]:>6}")

print("""
  注：
  - 咖啡馆已从 10/20/35 修正为 3/6/10
  - 旋转逗猫棒(双倍鱼获)不变，但建议你也看看是否要降
  - 综合buff系数从1.485降到1.21
""")
