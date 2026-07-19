"""
猫猫乐园数值平衡 v5 — 新约束
  rod=9:  乐园 > V(9)   赚钱
  rod=10: 乐园 = V(10)  持平
  rod=11: 乐园 < V(11)  亏钱
先诊断 ef(rod)/V(rod) 形状，判断可行性，再求解。
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
SCENE_MULT = 1 + PARK_DIFF * 0.3  # 2.8
FISH_MULT_AVG = 1.45


def E_fish_park_raw(rod):
    d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    total = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        r = _RARITY_KEYS[i]
        total += probs[i] * RARITY_BASE[r] * SCENE_MULT * FISH_MULT_AVG
    if len(probs) > len(_RARITY_KEYS):
        total += (
            sum(probs[len(_RARITY_KEYS) :])
            * RARITY_BASE["UTR"]
            * SCENE_MULT
            * FISH_MULT_AVG
        )
    return total


# ═══ 诊断 ═════════════════════════════════════════════════════════════
print("=" * 80)
print("  诊断：乐园鱼 ef(rod) 与主世界 V(rod) 的增长形状对比")
print("=" * 80)

print(
    f"\n{'rod':>4} {'ef(raw)':>10} {'V(rod)':>10} {'ef/V':>8} {'ef环比':>8} {'V环比':>8}"
)
print("-" * 55)
prev_ef = prev_v = 0
for rod in range(7, 16):
    ef = E_fish_park_raw(rod)
    v = V_cache[rod]
    ef_r = (ef / prev_ef - 1) * 100 if prev_ef else 0
    v_r = (v / prev_v - 1) * 100 if prev_v else 0
    print(
        f"{rod:>4} {ef:>10.1f} {v:>10.1f} {ef / v * 100:>7.0f}% {ef_r:>7.0f}% {v_r:>7.0f}%"
    )
    prev_ef, prev_v = ef, v

print("""
  关键观察：ef/V 是否随rod单调变化？
  - 若 ef/V 随rod上升 → 鱼部分占比越来越高 → 加材料后ratio上升 → 无法衰减
  - 若 ef/V 随rod下降 → 鱼部分被主世界甩开 → ratio自然下降 → 可行
""")

# ═══ 求解新约束 ═══════════════════════════════════════════════════════
# 乐园每竿收益(rod) = m×P + (1-m)×D×ef_raw(rod)
# ratio(rod) = 上面 / V(rod)
#
# 约束: ratio(10) = 1.0
#   m×P + (1-m)×D×ef10 = V(10)                      ... (*)
#
# 自由度：m, P, D 三个变量，一个方程
# 扫描 (m, D)，由(*)求P，然后验证 ratio(9)>1 且 ratio(11)<1

ef10 = E_fish_park_raw(10)
ef9 = E_fish_park_raw(9)
ef11 = E_fish_park_raw(11)

print(f"{'=' * 80}")
print("  求解：rod=10 持平，扫描 (m, D) 求 P，验证 rod=9赚/rod=11亏")
print(f"{'=' * 80}")


# 速度参数：hook=7, 传说饵, 打窝+框满
def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    base = 60
    hook_mult = 1 + hook * 0.1
    nest_bonus = min(nest_layers, 10) * 5
    frame_bonus = min(frame_layers, 10) * 5
    total_speed = bait_bonus + nest_bonus + frame_bonus
    return base / (hook_mult * (1 + total_speed / 100))


interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)
print(
    f"\n  速度：hook=7, 传说饵, 打窝+框满 → {interval7:.1f}分钟/竿 → {casts_24h}竿/天(24h)"
)

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

total_casts_20d = casts_24h * 20
m_min_build = TOTAL_NEEDED / total_casts_20d
print(
    f"  建造：{TOTAL_NEEDED}个 / {total_casts_20d}竿(20天) → 材料率≥{m_min_build * 100:.1f}%"
)

print("\n  扫描 (m, D)，约束 ratio(10)=1.0：")
print(
    f"  {'m':>6} {'D':>6} {'P':>8} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'判定':>8}"
)
print("  " + "-" * 75)

solutions = []
for m_pct in range(int(m_min_build * 100), 91, 2):
    m = m_pct / 100
    for D_x100 in range(5, 301, 5):
        D = D_x100 / 100
        # 由 ratio(10)=1 求 P
        # m×P + (1-m)×D×ef10 = V(10)
        fish_part_10 = (1 - m) * D * ef10
        mP = V_cache[10] - fish_part_10
        if mP < 0:
            continue
        P = mP / m if m > 0 else 0
        if P < 0 or P > 5000:
            continue

        # 计算关键ratio
        def ratio(rod):
            ef = E_fish_park_raw(rod)
            return (m * P + (1 - m) * D * ef) / V_cache[rod]

        r9 = ratio(9)
        r10 = ratio(10)
        r11 = ratio(11)

        # 判定
        ok = abs(r10 - 1.0) < 0.02 and r9 > 1.0 and r11 < 1.0
        flag = "✓✓✓" if ok else ""
        if ok:
            solutions.append((m, D, P, r9, r10, r11))
            r8 = ratio(8)
            r12 = ratio(12)
            r13 = ratio(13)
            print(
                f"  {m * 100:>5.0f}% {D:>6.2f} {P:>8.0f} {r8 * 100:>5.0f}% {r9 * 100:>5.0f}% {r10 * 100:>5.0f}% {r11 * 100:>5.0f}% {r12 * 100:>5.0f}% {r13 * 100:>5.0f}% {flag}"
            )

if not solutions:
    print("\n  无解！检查 rod=9/10/11 的 ef/V 是否允许这种单调性")
    # 打印极限情况
    print("\n  纯鱼(D折扣)下 ef×D/V 在各rod的形状（m=0,P=0）：")
    for D in [0.3, 0.5, 0.7, 1.0]:
        print(f"  D={D}: ", end="")
        for rod in range(8, 14):
            print(
                f"r{rod}={E_fish_park_raw(rod) * D / V_cache[rod] * 100:.0f}% ", end=""
            )
        print()
    print("\n  → 若 ef/V 单调上升，则加材料只会让所有rod同步上移，无法实现9>1>11")
else:
    # 选 r@11 最低（衰减最陡）
    best = min(solutions, key=lambda x: x[5])
    m, D, P = best[0], best[1], best[2]
    print(f"\n{'=' * 80}")
    print("  ★ 最优解（rod=11衰减最陡）")
    print(f"{'=' * 80}")
    print(f"  材料率={m * 100:.0f}%  鱼价折扣={D:.2f}  材料均价={P:.0f}")
    print(f"\n  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        ef = E_fish_park_raw(rod)
        income = m * P + (1 - m) * D * ef
        r = income / V_cache[rod]
        ev = "赚" if r > 1.02 else ("平" if r > 0.98 else "亏")
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )

    mats_per_day = casts_24h * m
    print(
        f"\n  建设：{casts_24h}竿×{m * 100:.0f}%={mats_per_day:.0f}材料/天 → {TOTAL_NEEDED / mats_per_day:.0f}天建完"
    )
