"""
猫猫乐园数值平衡 v3 — 基于主世界真实钓鱼间隔（60分钟基础间隔）
精确计算玩家在不同配置下的钓鱼速度，然后求解材料平衡
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

# ═══ 钓鱼间隔公式（来自 config.py calculate_fishing_interval）═══════════
# interval_min = 60 / [(1 + hook×0.1) × (1 + speed_bonus/100)] / extra_mult / weather_mult
#
# speed_bonus 包含：鱼饵 + 打窝(上限50%) + 展示框(上限50%) + 加速药水


def calc_interval(hook, bait_bonus, nest_layers, frame_layers, weather_spd=0):
    """返回真实钓鱼间隔（分钟）"""
    base = 60  # 分钟
    hook_mult = 1 + hook * 0.1
    nest_bonus = min(nest_layers, 10) * 5  # 打窝每层5%，上限10层=50%
    frame_bonus = min(frame_layers, 10) * 5  # 展示框每层5%，上限10层=50%
    total_speed = bait_bonus + nest_bonus + frame_bonus
    speed_mult = hook_mult * (1 + total_speed / 100)
    weather_mult = 1 + weather_spd / 100  # 雨天+10%
    return base / speed_mult / weather_mult


# ═══ 打印不同配置的真实钓鱼速度 ═══════════════════════════════════════
print("=" * 80)
print("  猫猫乐园数值平衡 v3 — 真实钓鱼速度")
print("=" * 80)

print("\n【1. 真实钓鱼间隔（基础=60分钟）】")
print(
    f"  {'hook':>4} {'鱼饵':>8} {'打窝':>4} {'框':>4} {'间隔(分)':>8} {'竿/天(12h)':>10} {'竿/天(8h)':>10}"
)
print("-" * 65)

configs = [
    # (hook, 鱼饵名, bait_bonus, 打窝层, 框层)
    (7, "传说(6级)", 120, 10, 10),
    (7, "魔法(5级)", 100, 10, 10),
    (7, "传说(6级)", 120, 0, 0),
    (7, "魔法(5级)", 100, 0, 0),
    (5, "魔法(5级)", 100, 10, 10),
    (5, "黄金(4级)", 80, 10, 10),
    (5, "魔法(5级)", 100, 0, 0),
    (3, "黄金(4级)", 80, 0, 0),
]

for hook, bait_name, bait_bonus, nest, frame in configs:
    interval = calc_interval(hook, bait_bonus, nest, frame)
    casts_12h = int(12 * 60 / interval)
    casts_8h = int(8 * 60 / interval)
    nest_str = f"{nest * 5}%" if nest > 0 else "无"
    frame_str = f"{frame * 5}%" if frame > 0 else "无"
    print(
        f"  hook{hook:<2} {bait_name:>8} {nest_str:>4} {frame_str:>4} {interval:>8.1f} {casts_12h:>10} {casts_8h:>10}"
    )

# ═══ 选取典型玩家画像 ═════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("  典型玩家画像（猫猫乐园入口：rod=7, hook=7）")
print(f"{'=' * 80}")

# 画像：hook=7，传说鱼饵，打窝满+框满
hook7, bait7, nest7, frame7 = 7, 120, 10, 10
interval7 = calc_interval(hook7, bait7, nest7, frame7)
casts_12h_7 = int(12 * 60 / interval7)
casts_8h_7 = int(8 * 60 / interval7)

print("\n  高配玩家：hook=7, 传说鱼饵, 打窝50%+框50%")
print(f"  间隔: {interval7:.1f}分钟")
print(f"  12h/天: {casts_12h_7}竿  |  8h/天: {casts_8h_7}竿")


# ═══ M(d) 和 V(rod) ═══════════════════════════════════════════════════
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


print("\n【主世界 V(rod) 期望收益/竿】")
V_cache = {}
for rod in range(6, 16):
    v = V_normal(rod)
    V_cache[rod] = v
    print(f"  rod={rod:>2}  V={v:>8.1f}")

# ═══ 乐园鱼期望 ═══════════════════════════════════════════════════════
PARK_DIFF = 6
RARITY_BASE = {"N": 8, "R": 22, "SR": 55, "SSR": 120, "UR": 220, "UTR": 400}
SCENE_MULT = 1 + PARK_DIFF * 0.3
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


# ═══ 建造材料总需求 ════════════════════════════════════════════════════
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

print(f"\n【建造总材料需求：{TOTAL_NEEDED} 个】")

# ═══ 核心求解 ═══════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("  核心求解 — 不同钓鱼时长×材料倍率的全扫描")
print(f"{'=' * 80}")
print("\n  变量：")
print("    D = 鱼价折扣")
print("    m = 材料掉率")
print("    P = 材料售价")
print("    K = 建造材料需求倍率（当前总需求×K）")
print("\n  约束：")
print("    A) (1-m) × E_fish(D, rod=7) = 0.5 × V(7)     [活动期半收益]")
print("    B) m × P + (1-m) × E_fish(D, rod=8) = 1.2 × V(8) [完成后+20%]")
print(f"    C) 总竿数 × m ≥ {TOTAL_NEEDED} × K              [建设可行]")

# 扫描：不同日均时长 × 不同材料倍率
for daily_hours in [4, 6, 8, 12]:
    casts_per_day = int(daily_hours * 60 / interval7)
    for build_days in [20, 30]:
        total_casts = casts_per_day * build_days

        print(
            f"\n  ── {daily_hours}h/天 × {build_days}天 = {casts_per_day}竿/天 × {total_casts}总竿 ──"
        )

        # 对每个材料倍率K，求所需的材料率和对应数值
        for K in [1, 2, 3, 5, 8, 10]:
            mats_needed = TOTAL_NEEDED * K
            max_mats_producible = total_casts  # 100%材料率
            if mats_needed > max_mats_producible:
                continue  # 即使100%也建不完

            # 材料率至少要 m_min = mats_needed / total_casts
            m_min = mats_needed / total_casts

            # 约束A: (1-m) × E_fish(D, 7) = 0.5 × V(7)
            # E_fish(D, 7) = E_fish(1.0, 7) × D
            ef_d1_7 = E_fish_park(7, 1.0)
            target_A = 0.5 * V_cache[7]
            # (1-m) × ef_d1_7 × D = target_A
            # D = target_A / ((1-m) × ef_d1_7)
            D = target_A / ((1 - m_min) * ef_d1_7)

            if D > 3 or D < 0.05 or (1 - m_min) <= 0:
                continue

            # 约束B求P
            ef8 = E_fish_park(8, D)
            target_B = 1.2 * V_cache[8]
            if m_min <= 0:
                continue
            P_mat = (target_B - (1 - m_min) * ef8) / m_min

            if P_mat < 0 or P_mat > 10000:
                continue

            # 验证
            active = (1 - m_min) * E_fish_park(7, D)
            done = m_min * P_mat + (1 - m_min) * E_fish_park(8, D)
            ratio_active = active / V_cache[7]
            ratio_done = done / V_cache[8]

            ok = (
                "✓"
                if (0.45 < ratio_active < 0.55 and 1.15 < ratio_done < 1.25)
                else "≈"
            )

            print(
                f"    K={K:>2} → 材料率{m_min * 100:>5.1f}%  折扣{D:.2f}  材料价{P_mat:>6.0f}  "
                f"活动{ratio_active * 100:>4.0f}%V 完工{ratio_done * 100:>4.0f}%V {ok}"
            )

# ═══ 最佳方案详细展开 ═══════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("  推荐方案详细展开（12h/天 × 20天，K=8）")
print(f"{'=' * 80}")

daily_hours, build_days, K = 12, 20, 8
casts_per_day = int(daily_hours * 60 / interval7)
total_casts = casts_per_day * build_days
mats_needed = TOTAL_NEEDED * K
m = mats_needed / total_casts

ef_d1_7 = E_fish_park(7, 1.0)
D = 0.5 * V_cache[7] / ((1 - m) * ef_d1_7)
ef8 = E_fish_park(8, D)
P_mat = (1.2 * V_cache[8] - (1 - m) * ef8) / m

print(f"\n  钓鱼配置：hook=7, 传说鱼饵, 打窝+框满, 间隔{interval7:.1f}分钟")
print(
    f"  {daily_hours}h/天 → {casts_per_day}竿/天 → {build_days}天 = {total_casts}总竿"
)
print(f"  材料需求倍率 K={K} → 总需{mats_needed}个 → 材料率={m * 100:.1f}%")
print(f"  鱼价折扣 D={D:.2f}")
print(f"  材料均价 P={P_mat:.0f}金币/个")
print("\n  【验证】")
active = (1 - m) * E_fish_park(7, D)
done = m * P_mat + (1 - m) * E_fish_park(8, D)
print(f"  活动期收益: {active:.1f} = {active / V_cache[7] * 100:.0f}% V(7) [目标50%]")
print(f"  完工后收益: {done:.1f} = {done / V_cache[8] * 100:.0f}% V(8) [目标120%]")

print("\n  【随鱼竿升级的衰减】")
print(f"  {'rod':>4} {'乐园收益':>10} {'主世界V':>10} {'乐园/V':>8}")
for rod in range(7, 16):
    ef = E_fish_park(rod, D)
    v = V_cache[rod]
    income = m * P_mat + (1 - m) * ef
    print(f"  {rod:>4} {income:>10.1f} {v:>10.1f} {income / v * 100:>7.0f}%")

# 材料价格分配
print(f"\n  【材料价格分配（均价{P_mat:.0f}）】")
weights = {
    "猫抓板木板": 20,
    "毛线团": 20,
    "小铃铛": 20,
    "特级小鱼干": 20,
    "水晶猫砂": 18,
    "彩虹逗猫棒": 12,
}
total_w = sum(weights.values())
# 常见4种×0.7P, 稀有2种×2.5P，校准到P
common = P_mat * 0.7
rare = P_mat * 2.5
wavg = (common * 80 + rare * 30) / total_w
adj = P_mat / wavg
common *= adj
rare *= adj
for mat, w in sorted(weights.items(), key=lambda x: -x[1]):
    p = common if w >= 18 else rare
    print(f"    {mat:<12} {p:>6.0f}金币/个")
