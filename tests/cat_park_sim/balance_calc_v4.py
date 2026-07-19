"""
猫猫乐园数值平衡 v4 — 24h/天 + 更陡衰减
约束：
  A) 活动期间 (rod=7):  收益 = 0.5 × V(7)
  B) rod=10:            收益 = 1.0 × V(10)   [允许回本]
  C) rod=11:            收益 ≪ V(11)         [大幅削弱]
核心：材料价固定 → rod升高后鱼收益碾压材料 → 自然衰减
关键是调出"rod=10是盈亏平衡点"的曲线
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


# ═══ 速度公式 ═════════════════════════════════════════════════════════
def calc_interval(hook, bait_bonus, nest_layers, frame_layers, weather_spd=0):
    base = 60  # 分钟
    hook_mult = 1 + hook * 0.1
    nest_bonus = min(nest_layers, 10) * 5
    frame_bonus = min(frame_layers, 10) * 5
    total_speed = bait_bonus + nest_bonus + frame_bonus
    speed_mult = hook_mult * (1 + total_speed / 100)
    weather_mult = 1 + weather_spd / 100
    return base / speed_mult / weather_mult


# ═══ M(d) 和 V(rod) ══════════════════════════════════════════════════
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
    for loc in LOCATIONS:
        if loc["difficulty"] > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M(rod - loc["difficulty"])
        if exp > best:
            best = exp
    return best


V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

# ═══ 乐园鱼期望 ═══════════════════════════════════════════════════════
PARK_DIFF = 6
RARITY_BASE = {"N": 8, "R": 22, "SR": 55, "SSR": 120, "UR": 220, "UTR": 400}
SCENE_MULT = 1 + PARK_DIFF * 0.3  # 2.8
FISH_MULT_AVG = 1.45


def E_fish_park(rod, discount):
    d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    total = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        r = _RARITY_KEYS[i]
        total += probs[i] * RARITY_BASE[r] * discount * SCENE_MULT * FISH_MULT_AVG
    if len(probs) > len(_RARITY_KEYS):
        total += (
            sum(probs[len(_RARITY_KEYS) :])
            * RARITY_BASE["UTR"]
            * discount
            * SCENE_MULT
            * FISH_MULT_AVG
        )
    return total


# ═══ 建造材料 ═════════════════════════════════════════════════════════
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

# ═══ 基础数据 ═════════════════════════════════════════════════════════
print("=" * 80)
print("  猫猫乐园数值平衡 v4 — 24h/天 + 陡衰减")
print("=" * 80)

# 24h真实速度
hook7, bait7, nest7, frame7 = 7, 120, 10, 10
interval7 = calc_interval(hook7, bait7, nest7, frame7)
casts_24h = int(24 * 60 / interval7)

print(
    f"\n【钓鱼速度】hook=7, 传说饵, 打窝+框满 → 间隔{interval7:.1f}分钟 → {casts_24h}竿/天(24h)"
)

print("\n【V(rod) 主世界期望收益】")
for rod in range(7, 16):
    print(f"  rod={rod:>2}  V={V_cache[rod]:.1f}")

print(f"\n【建造总材料：{TOTAL_NEEDED}个】")

# ═══ 新思路：解约束体系 ═══════════════════════════════════════════════
# 乐园每竿收益 = m × P + (1-m) × E_fish(D, rod)
#
# 三个目标点：
#   rod=7:  ratio = 0.5   （活动期半收益）
#   rod=10: ratio = 1.0   （盈亏平衡）
#   rod=11: ratio ≪ 1.0   （大幅削弱）
#
# 关键洞察：ratio(rod) = [m×P + (1-m)×E_fish(D,rod)] / V(rod)
# V(rod) 增长极快（指数级），E_fish 增长较慢
# 要让 rod=10 刚好=1.0，rod=11 远低于1.0
# 需要找到合适的 m, P, D

print(f"\n{'=' * 80}")
print("  求解：三约束体系")
print(f"{'=' * 80}")

# 约束1: rod=7 时 ratio=0.5
#   m×P + (1-m)×E_fish(D,7) = 0.5×V(7)                    ... (1)
# 约束2: rod=10 时 ratio=1.0
#   m×P + (1-m)×E_fish(D,10) = 1.0×V(10)                   ... (2)
# (2)-(1): (1-m)×[E_fish(D,10) - E_fish(D,7)] = V(10) - 0.5×V(7)
# 注意 E_fish(D,rod) = D × E_fish(1.0,rod)  （D线性缩放）
# 设 ef7_0 = E_fish(1.0,7), ef10_0 = E_fish(1.0,10)
# (2)-(1): (1-m)×D×(ef10_0 - ef7_0) = V(10) - 0.5×V(7)

ef7_0 = E_fish_park(7, 1.0)
ef10_0 = E_fish_park(10, 1.0)

print(f"\n  E_fish(1.0, rod=7)  = {ef7_0:.1f}")
print(f"  E_fish(1.0, rod=10) = {ef10_0:.1f}")
print(f"  V(7)  = {V_cache[7]:.1f}")
print(f"  V(10) = {V_cache[10]:.1f}")

# 差分方程: (1-m)×D = [V(10) - 0.5×V(7)] / (ef10_0 - ef7_0)
rhs = (V_cache[10] - 0.5 * V_cache[7]) / (ef10_0 - ef7_0)
print(f"\n  差分方程: (1-m)×D = {rhs:.3f}")

# 代入(1): m×P + rhs × ef7_0 = 0.5×V(7)
# → m×P = 0.5×V(7) - rhs×ef7_0
mP = 0.5 * V_cache[7] - rhs * ef7_0
print(f"  → m×P = {mP:.1f}")

# 现在扫描 (m, D) 组合，计算 P，然后验证 rod=11 衰减
# 约束: (1-m)×D = rhs → D = rhs/(1-m)
# m×P = mP → P = mP/m

# 还需满足建设约束: 24h×20天×casts × m ≥ TOTAL_NEEDED
total_casts_20d = casts_24h * 20
m_min_build = TOTAL_NEEDED / total_casts_20d
print(f"\n  建设约束: 24h×20天={total_casts_20d}竿 → 材料率≥{m_min_build * 100:.1f}%")

print(f"\n  扫描 m 从 {m_min_build:.2f} 到 0.8：")
print(
    f"  {'m(材料率)':>10} {'D(折扣)':>8} {'P(材料价)':>10} {'r@7':>6} {'r@8':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6}"
)
print("  " + "-" * 75)

best_solutions = []
for m_pct in range(int(m_min_build * 100), 81, 2):
    m = m_pct / 100
    D = rhs / (1 - m)
    if D > 3 or D < 0.05:
        continue
    if m <= 0:
        continue
    P = mP / m
    if P < 0 or P > 5000:
        continue

    # 验证各rod的ratio
    ratios = {}
    for rod in range(7, 16):
        ef = E_fish_park(rod, D)
        income = m * P + (1 - m) * ef
        ratios[rod] = income / V_cache[rod]

    r7 = ratios[7]
    r10 = ratios[10]
    r11 = ratios[11]

    # 检查约束
    ok7 = abs(r7 - 0.5) < 0.02
    ok10 = abs(r10 - 1.0) < 0.05

    if ok7 and ok10:
        flag = "✓✓"
    elif ok7:
        flag = "✓7"
    elif ok10:
        flag = "✓10"
    else:
        flag = "  "

    best_solutions.append((m, D, P, ratios, flag))
    print(
        f"  {m * 100:>9.0f}% {D:>8.2f} {P:>10.0f} {ratios[7] * 100:>5.0f}% {ratios[8] * 100:>5.0f}% {ratios[10] * 100:>5.0f}% {ratios[11] * 100:>5.0f}% {ratios[12] * 100:>5.0f}% {ratios[13] * 100:>5.0f}% {flag}"
    )

# ═══ 最佳方案 ═════════════════════════════════════════════════════════
if best_solutions:
    # 找 rod=11 衰减最明显的
    valid = [s for s in best_solutions if "✓✓" in s[4]]
    if not valid:
        valid = best_solutions

    # 选 r@11 最低的
    best = min(valid, key=lambda x: x[3][11])
    m, D, P, ratios, flag = best

    print(f"\n{'=' * 80}")
    print("  ★ 最优方案（rod=11衰减最陡）")
    print(f"{'=' * 80}")
    print(f"\n  材料率 m = {m * 100:.0f}%")
    print(f"  鱼价折扣 D = {D:.2f}")
    print(f"  材料均价 P = {P:.0f} 金币/个")
    print("\n  【完整衰减曲线】")
    print(f"  {'rod':>4} {'乐园收益':>10} {'主世界V':>10} {'比例':>8} {'评估':>8}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        ef = E_fish_park(rod, D)
        income = m * P + (1 - m) * ef
        v = V_cache[rod]
        r = income / v
        if r > 1.15:
            eval_ = "超值"
        elif r > 0.95:
            eval_ = "回本"
        elif r > 0.75:
            eval_ = "一般"
        else:
            eval_ = "该走了"
        print(f"  {rod:>4} {income:>10.1f} {v:>10.1f} {r * 100:>7.0f}% {eval_:>8}")

    # 建设节奏验证
    mats_per_day = casts_24h * m
    build_days = TOTAL_NEEDED / mats_per_day
    print("\n  【建设节奏】")
    print(f"  {casts_24h}竿/天 × {m * 100:.0f}% = {mats_per_day:.0f}材料/天")
    print(f"  需{TOTAL_NEEDED}个 → {build_days:.0f}天建完")

    # 材料价格分配
    print(f"\n  【材料价格分配（均价{P:.0f}）】")
    weights = {
        "猫抓板木板": 20,
        "毛线团": 20,
        "小铃铛": 20,
        "特级小鱼干": 20,
        "水晶猫砂": 18,
        "彩虹逗猫棒": 12,
    }
    total_w = sum(weights.values())
    common = P * 0.6
    rare = P * 2.8
    wavg = (common * 80 + rare * 30) / total_w
    adj = P / wavg
    common *= adj
    rare *= adj
    for mat, w in sorted(weights.items(), key=lambda x: -x[1]):
        p = common if w >= 18 else rare
        print(f"    {mat:<12} {p:>6.0f}金币/个")
else:
    print("\n  ⚠ 没有找到满足约束的方案")
