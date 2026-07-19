"""
猫猫乐园 v9 — 用户方案：鱼价=主世界，材料固定价
核心：乐园鱼直接用主世界价格体系，材料固定价格提供活动加成
随着rod升级，主世界V(rod)增长 > 乐园固定材料收益，自然衰减
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


def calc_M(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        m += probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]]
    if len(probs) > len(_RARITY_KEYS):
        m += sum(probs[len(_RARITY_KEYS) :]) * RARITY_MULTIPLIER["UTR"]
    return m


def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0


LOC_AVG = {loc["id"]: loc_avg_base(loc) for loc in LOCATIONS}


def V_normal(rod):
    best = 0
    best_loc = None
    for loc in LOCATIONS:
        if loc["difficulty"] > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M(rod - loc["difficulty"])
        if exp > best:
            best = exp
            best_loc = loc
    return best, best_loc


V_cache = {}
V_loc_cache = {}
for rod in range(1, 20):
    v, loc = V_normal(rod)
    V_cache[rod] = v
    V_loc_cache[rod] = loc

PARK_DIFF = 6
SCENE_MULT = 1 + PARK_DIFF * 0.3  # 2.8

# ═══ 检查locations的difficulty分布 ═══
print("=" * 80)
print("  猫猫乐园 v9 — 鱼价=主世界，材料固定价")
print("=" * 80)

print("\n【主世界地图列表】")
for loc in sorted(LOCATIONS, key=lambda x: x["difficulty"]):
    print(
        f"  diff={loc['difficulty']}  {loc['id']:<20} 鱼池均价={LOC_AVG[loc['id']]:.0f}  鱼数={len(loc['fish_pool'])}"
    )

max_diff = max(loc["difficulty"] for loc in LOCATIONS)
print(f"\n  最高difficulty={max_diff}")

# ═══ 乐园鱼期望：直接用主世界价格体系 ═══
# 用户思路：乐园鱼价格和主世界一样
# 乐园固定 diff=6，鱼池均价取主世界 diff=6 地图的均价（或自定义接近的值）
# ef_park(rod) = 乐园鱼池均价 × M(rod-6) × SCENE_MULT（场景加成是乐园特色）

# 找主世界diff=6的地图均价作参考
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
if diff6_locs:
    park_avg_price = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)
else:
    park_avg_price = sum(LOC_AVG.values()) / len(LOC_AVG)

print(f"\n  主世界diff=6地图均价: {park_avg_price:.0f}")
print(f"  乐园采用此均价 × M(rod-6) × SCENE_MULT({SCENE_MULT})")


def ef_park(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg_price * calc_M(d) * SCENE_MULT


# ═══ 验证 ef_park/V 的形状 ═══
print("\n【乐园鱼 ef_park(rod) vs 主世界 V(rod)】")
print(f"  {'rod':>4} {'ef_park':>10} {'V(rod)':>10} {'ef/V':>8} {'V用哪个图':>20}")
print("  " + "-" * 60)
for rod in range(7, 16):
    ef = ef_park(rod)
    v = V_cache[rod]
    loc_id = V_loc_cache[rod]["id"] if V_loc_cache[rod] else "?"
    print(f"  {rod:>4} {ef:>10.1f} {v:>10.1f} {ef / v * 100:>7.0f}% {loc_id:>20}")

# ═══ 求解 ═══
# ratio(rod) = [m×P + (1-m)×ef_park(rod)] / V(rod)
# 约束：ratio(10) = 1.0
#   m×P + (1-m)×ef_park(10) = V(10)
#   m×P = V(10) - (1-m)×ef_park(10)
#   P = [V(10) - (1-m)×ef_park(10)] / m
#
# 给定m（材料率），就能算P，然后看衰减


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

print(f"\n{'=' * 80}")
print("  求解：ratio(10)=1.0，扫描材料率m")
print(f"{'=' * 80}")
print(f"  速度：{casts_24h}竿/天，建造需{TOTAL_NEEDED}个")

ef10 = ef_park(10)
# 如果 ef_park(10) 已经 >= V(10)，说明鱼本身就已经超了，材料只会更高
print(
    f"  ef_park(10)={ef10:.1f}, V(10)={V_cache[10]:.1f}, ef/V={ef10 / V_cache[10] * 100:.0f}%"
)

if ef10 >= V_cache[10]:
    print("\n  ⚠ ef_park(10) ≥ V(10)！鱼价本身就超标了")
    print(f"  原因：SCENE_MULT={SCENE_MULT} 让乐园鱼价太高")
    print("  解决：去掉SCENE_MULT，或降低乐园鱼池均价")

    # 去掉SCENE_MULT重算
    print("\n  === 去掉SCENE_MULT（乐园鱼价=主世界原价）===")

    def ef_park_no_scene(rod):
        d = max(0, rod - PARK_DIFF)
        return park_avg_price * calc_M(d)

    ef10_ns = ef_park_no_scene(10)
    print(
        f"  ef_park(10)={ef10_ns:.1f}, V(10)={V_cache[10]:.1f}, ef/V={ef10_ns / V_cache[10] * 100:.0f}%"
    )
    ef_park = ef_park_no_scene  # 替换
    ef10 = ef10_ns

print("\n  扫描 m（材料率），ratio(10)=1.0 反解 P：")
print(
    f"  {'m':>5} {'建天':>5} {'P':>8} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6} {'r@15':>6}"
)
print("  " + "-" * 85)

for m_pct in range(5, 51, 1):
    m = m_pct / 100
    fish10 = (1 - m) * ef10
    mP = V_cache[10] - fish10
    if mP < 0:
        # 鱼本身已经超过V(10)
        continue
    P = mP / m
    if P < 0:
        continue
    build_days = TOTAL_NEEDED / (casts_24h * m)

    ratios = {}
    for rod in range(7, 16):
        ratios[rod] = (m * P + (1 - m) * ef_park(rod)) / V_cache[rod]

    rstr = " ".join(f"{ratios[r] * 100:>5.0f}%" for r in range(7, 16))
    ok9 = ratios[9] > 1.0
    ok10 = abs(ratios[10] - 1.0) < 0.02
    ok11 = ratios[11] < 1.0
    mark = "★" if (ok9 and ok10 and ok11) else ""
    # 只打印关键点
    if m_pct % 3 == 0 or mark:
        print(f"  {m * 100:>4.0f}% {build_days:>5.0f} {P:>8.0f} {rstr} {mark}")

# ═══ 最优方案 ═══
print(f"\n{'=' * 80}")
print("  ★ 推荐方案")
print(f"{'=' * 80}")

# 选 m=15%（约22天建设）
for m_target in [0.10, 0.12, 0.15, 0.18, 0.20, 0.25]:
    m = m_target
    fish10 = (1 - m) * ef10
    mP = V_cache[10] - fish10
    if mP < 0:
        print(f"\n  m={m * 100:.0f}%: 无解（鱼价已超标）")
        continue
    P = mP / m
    build_days = TOTAL_NEEDED / (casts_24h * m)

    print(f"\n  ── m={m * 100:.0f}%, P={P:.0f}, 建设{build_days:.0f}天 ──")
    print(f"  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * ef_park(rod)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.02 else ("平" if r > 0.98 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )
