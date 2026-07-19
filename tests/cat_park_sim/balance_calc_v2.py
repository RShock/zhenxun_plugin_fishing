"""
猫猫乐园数值平衡计算 v2 — 基于真实手动钓鱼频率
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


# ── 基础工具 ──────────────────────────────────────────────────────────
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
        n = loc["difficulty"]
        if n > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M(rod - n)
        if exp > best:
            best = exp
    return best


# ── 乐园参数 ──────────────────────────────────────────────────────────
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


# ── 建造总材料需求 ────────────────────────────────────────────────────
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

total_mats_needed = {}
for bld, levels in BUILDING_COSTS.items():
    for lv, cost in levels.items():
        for mat, qty in cost.items():
            total_mats_needed[mat] = total_mats_needed.get(mat, 0) + qty

TOTAL_NEEDED = sum(total_mats_needed.values())

# ── 打印基础数据 ──────────────────────────────────────────────────────
print("=" * 70)
print("  猫猫乐园数值平衡 v2 — 基于真实钓鱼频率")
print("=" * 70)

print("\n【1. 建造总材料需求】")
for mat, qty in sorted(total_mats_needed.items(), key=lambda x: -x[1]):
    print(f"  {mat:<12} {qty:>4} 个")
print(f"  {'合计':<12} {TOTAL_NEEDED:>4} 个")

# ── 真实钓鱼频率参数 ──────────────────────────────────────────────────
ROD_INTERVAL_MIN = 20  # 真实钓鱼约20分钟/竿
DAILY_HOURS = 12  # 假设玩家每天钓12小时（肝帝）
DAILY_CASTS = int(DAILY_HOURS * 60 / ROD_INTERVAL_MIN)  # 36竿/天

print("\n【2. 钓鱼频率假设】")
print(f"  每竿间隔: ~{ROD_INTERVAL_MIN}分钟")
print(f"  每天钓鱼: {DAILY_HOURS}小时 → {DAILY_CASTS}竿/天")
print(f"  建设周期: 20天 → 总竿数 {DAILY_CASTS * 20}")

BUILD_DAYS = 20
TOTAL_CASTS = DAILY_CASTS * BUILD_DAYS
MAT_RATE_FOR_BUILD = TOTAL_NEEDED / TOTAL_CASTS

print("\n【3. 建设所需材料率】")
print(
    f"  需产出 {TOTAL_NEEDED} 个材料 / {TOTAL_CASTS} 竿 = {MAT_RATE_FOR_BUILD * 100:.1f}%/竿"
)

# 如果玩家更休闲呢？
for daily_hours in [4, 6, 8, 12]:
    casts = int(daily_hours * 60 / ROD_INTERVAL_MIN)
    total = casts * BUILD_DAYS
    rate = TOTAL_NEEDED / total
    print(f"  若每天钓{daily_hours}h → {casts}竿/天 → 需材料率 {rate * 100:.1f}%")

# ── 主世界 V(rod) ─────────────────────────────────────────────────────
print("\n【4. 主世界 V(rod)】")
V_cache = {}
for rod in range(6, 16):
    v = V_normal(rod)
    V_cache[rod] = v
    print(f"  rod={rod:>2}  V={v:.1f}")

# ── 5. 核心求解 ───────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("  核心求解")
print(f"{'=' * 70}")

# 变量：D(折扣), m(材料率), P(材料价)
# 取 m = 建设所需材料率
# 约束A: (1-m) × E_fish(D, 7) = 0.5 × V(7)  → 求D
# 约束B: m × P + (1-m) × E_fish(D, 8) = 1.2 × V(8)  → 求P

# 尝试不同的日均钓鱼时长
for daily_hours, daily_casts in [(4, 12), (6, 18), (8, 24), (12, 36)]:
    total_casts = daily_casts * BUILD_DAYS
    m = TOTAL_NEEDED / total_casts  # 建设所需材料率
    if m >= 1:
        print(f"\n  每天{daily_hours}h: 材料率>{100}%，不可能完成建设")
        continue

    # 约束A求D
    target_active = 0.5 * V_cache[7]
    # (1-m) × E_fish(D, 7) = target_active
    # E_fish(D, 7) = E_fish(1.0, 7) × D  (线性)
    ef_d1 = E_fish_park(7, 1.0)
    D_needed = target_active / ((1 - m) * ef_d1)

    if D_needed > 1.5 or D_needed < 0.1:
        print(
            f"\n  每天{daily_hours}h: 材料率{m * 100:.0f}% → 需折扣{D_needed:.2f}（不合理）"
        )
        continue

    # 约束B求P
    ef8 = E_fish_park(8, D_needed)
    target_done = 1.2 * V_cache[8]
    P_mat = (target_done - (1 - m) * ef8) / m

    # 验证
    active_income = (1 - m) * E_fish_park(7, D_needed)
    done_income = m * P_mat + (1 - m) * E_fish_park(8, D_needed)

    print(f"\n  【方案：每天{daily_hours}h钓鱼，{daily_casts}竿/天】")
    print(
        f"  材料率:     {m * 100:.1f}%（{daily_casts}竿×{BUILD_DAYS}天产{int(total_casts * m)}个，需求{TOTAL_NEEDED}个）"
    )
    print(f"  鱼价折扣:   {D_needed:.2f}（原0.7）")
    print(f"  材料均价:   {P_mat:.0f} 金币/个")
    print("  ─ 验证 ─")
    print(
        f"  活动期间:   {active_income:.1f} / V(7)={V_cache[7]:.1f} → {active_income / V_cache[7] * 100:.0f}%"
    )
    print(
        f"  完成后:     {done_income:.1f} / V(8)={V_cache[8]:.1f} → {done_income / V_cache[8] * 100:.0f}%"
    )

    # 衰减曲线
    print("  ─ 衰减曲线 ─")
    print(f"  {'rod':>4} {'乐园收益':>10} {'主世界V':>10} {'比例':>8}")
    for rod in range(7, 16):
        ef = E_fish_park(rod, D_needed)
        v = V_cache[rod]
        income = m * P_mat + (1 - m) * ef
        print(f"  {rod:>4} {income:>10.1f} {v:>10.1f} {income / v * 100:>7.0f}%")
