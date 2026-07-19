"""
猫猫乐园数值平衡计算器
目标：
  1. 活动期间收益 ≈ 0.5 × 同级别普通地图
  2. 完成后收益   ≈ 1.2 × 同级别普通地图（初始鱼竿等级）
  3. 随鱼竿升级，乐园收益/普通收益 逐渐下降 → 玩家自然离开
"""

import json

# ── 导入游戏常量 ──────────────────────────────────────────────────────────
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from constants import _RARITY_KEYS, RARITY_DISTRIBUTION, RARITY_MULTIPLIER

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# ── 加载鱼和关卡数据 ────────────────────────────────────────────────────
with open(CONFIG_DIR / "fish.json", encoding="utf-8") as f:
    FISH = {fi["id"]: fi["base_price"] for fi in json.load(f)["fish"]}

with open(CONFIG_DIR / "locations.json", encoding="utf-8") as f:
    LOCATIONS = json.load(f)["locations"]


# ── 1. 计算每个 d 的期望倍率 M(d) ───────────────────────────────────────
def calc_M(d: int) -> float:
    """钓鱼等级 d 时，稀有度倍率的期望值 E[multiplier]。"""
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        rarity = _RARITY_KEYS[i]
        m += probs[i] * RARITY_MULTIPLIER[rarity]
    # idx >= 6 的合并到 UTR
    if len(probs) > len(_RARITY_KEYS):
        utr_extra = sum(probs[len(_RARITY_KEYS) :])
        m += utr_extra * RARITY_MULTIPLIER["UTR"]
    return m


# ── 2. 每个关卡的平均 base_price ────────────────────────────────────────
def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0


LOC_AVG = {loc["id"]: loc_avg_base(loc) for loc in LOCATIONS}


# ── 3. 主世界每个鱼竿等级的最优期望收益 V(rod) ──────────────────────────
def V_normal(rod: int) -> float:
    """鱼竿等级 rod 时，玩家在最优关卡的每竿期望收益。"""
    best = 0
    for loc in LOCATIONS:
        n = loc["difficulty"]
        if n > rod:
            continue
        d = rod - n
        exp = LOC_AVG[loc["id"]] * calc_M(d)
        if exp > best:
            best = exp
    return best


# ── 4. 猫猫乐园鱼的期望价格 ─────────────────────────────────────────────
# 乐园难度=6，d = rod - 6
# 乐园鱼价 = base_r × discount × scene_mult × fish_mult
PARK_DIFFICULTY = 6
RARITY_BASE_PRICES = {"N": 8, "R": 22, "SR": 55, "SSR": 120, "UR": 220, "UTR": 400}
SCENE_MULT = 1 + PARK_DIFFICULTY * 0.3  # = 2.8
FISH_MULT_AVG = 1.45  # 1 + avg(0..9)×0.1 = 1.45


def E_fish_park(rod: int, discount: float = 0.7) -> float:
    """乐园中钓到一条鱼的期望售价（已含折扣、场景系数、鱼种系数）。"""
    d = max(0, rod - PARK_DIFFICULTY)
    d = min(d, len(RARITY_DISTRIBUTION) - 1)
    probs = RARITY_DISTRIBUTION[d]
    total = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        rarity = _RARITY_KEYS[i]
        base = RARITY_BASE_PRICES[rarity]
        price = base * discount * SCENE_MULT * FISH_MULT_AVG
        total += probs[i] * price
    if len(probs) > len(_RARITY_KEYS):
        utr_extra = sum(probs[len(_RARITY_KEYS) :])
        total += (
            utr_extra
            * RARITY_BASE_PRICES["UTR"]
            * discount
            * SCENE_MULT
            * FISH_MULT_AVG
        )
    return total


# ── 5. 打印基础数据表 ───────────────────────────────────────────────────
print("=" * 80)
print("  猫猫乐园数值平衡分析")
print("=" * 80)

print("\n【M(d) 稀有度倍率期望值】")
print(f"{'d':>3} {'M(d)':>10}")
for d in range(16):
    print(f"{d:>3} {calc_M(d):>10.3f}")

print("\n【各关卡平均 base_price】")
for loc in LOCATIONS:
    print(
        f"  关卡{loc['id']} (diff={loc['difficulty']}) {loc['name']:<10} avg_base={LOC_AVG[loc['id']]:.1f}"
    )

print("\n【主世界 V(rod) 最优每竿期望收益】")
V_cache = {}
for rod in range(1, 20):
    v = V_normal(rod)
    V_cache[rod] = v
    print(f"  rod={rod:>2}  V={v:>10.1f}")

# ── 6. 乐园分析 ─────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("  乐园鱼期望价格 vs 主世界（当前参数：discount=0.7）")
print("=" * 80)

print(
    f"\n{'rod':>4} {'d':>3} {'乐园鱼E':>10} {'主世界V':>10} {'鱼/V':>8} {'0.5V':>10} {'1.2V':>10}"
)
print("-" * 60)

for rod in range(7, 16):
    d = rod - PARK_DIFFICULTY
    ef = E_fish_park(rod, 0.7)
    v = V_cache[rod]
    print(
        f"{rod:>4} {d:>3} {ef:>10.1f} {v:>10.1f} {ef / v * 100:>7.1f}% {0.5 * v:>10.1f} {1.2 * v:>10.1f}"
    )

# ── 7. 求解：材料率和材料价 ─────────────────────────────────────────────
print("\n" + "=" * 80)
print("  求解材料率与材料价格")
print("=" * 80)

# 约束条件：
# A) 活动期间 (rod=7): (1-m) × E_fish(7) = 0.5 × V(7)
# B) 完成后   (rod=8): m × P_mat + (1-m) × E_fish(8) = 1.2 × V(8)
#
# 其中 m = 材料率，P_mat = 单个材料平均售价

rod_active = 7  # 活动期间鱼竿
rod_done = 8  # 完成后鱼竿（+1奖励）

ef7 = E_fish_park(rod_active, 0.7)
ef8 = E_fish_park(rod_done, 0.7)
v7 = V_cache[rod_active]
v8 = V_cache[rod_done]

print(f"\n  E_fish(rod=7) = {ef7:.1f}")
print(f"  E_fish(rod=8) = {ef8:.1f}")
print(f"  V(7) = {v7:.1f}")
print(f"  V(8) = {v8:.1f}")

# 约束A: (1-m) × ef7 = 0.5 × v7
# → m = 1 - 0.5 × v7 / ef7
m_required = 1 - 0.5 * v7 / ef7
print("\n  约束A: 活动期间收益 = 0.5 × V(7)")
print(f"  → (1-m) × {ef7:.1f} = {0.5 * v7:.1f}")
print(f"  → 材料率 m = {m_required * 100:.1f}%")

if 0 < m_required < 1:
    # 约束B: m × P_mat + (1-m) × ef8 = 1.2 × v8
    # → P_mat = (1.2 × v8 - (1-m) × ef8) / m
    p_mat = (1.2 * v8 - (1 - m_required) * ef8) / m_required
    print("\n  约束B: 完成后收益 = 1.2 × V(8)")
    print(
        f"  → {m_required * 100:.1f}% × P_mat + {100 - m_required * 100:.1f}% × {ef8:.1f} = {1.2 * v8:.1f}"
    )
    print(f"  → 材料平均售价 P_mat = {p_mat:.1f} 金币")

    # 验证
    print("\n  【验证】")
    active_income = (1 - m_required) * ef7
    done_income = m_required * p_mat + (1 - m_required) * ef8
    print(
        f"  活动期间每竿收益: {active_income:.1f}  (目标 {0.5 * v7:.1f})  ratio={active_income / v7:.2f}"
    )
    print(
        f"  完成后每竿收益:   {done_income:.1f}  (目标 {1.2 * v8:.1f})  ratio={done_income / v8:.2f}"
    )

    # ── 8. 衰减曲线 ─────────────────────────────────────────────────────
    print("\n  【随鱼竿升级的收益衰减】")
    print(f"  {'rod':>4} {'乐园收益':>10} {'主世界V':>10} {'乐园/V':>8} {'状态':>8}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        ef = E_fish_park(rod, 0.7)
        v = V_cache[rod]
        park_income = m_required * p_mat + (1 - m_required) * ef
        ratio = park_income / v
        status = (
            "超值"
            if ratio > 1.1
            else ("值得" if ratio > 0.9 else ("一般" if ratio > 0.7 else "该走了"))
        )
        print(
            f"  {rod:>4} {park_income:>10.1f} {v:>10.1f} {ratio * 100:>7.1f}% {status:>8}"
        )

    # ── 9. 材料价格分配 ─────────────────────────────────────────────────
    print("\n  【6种材料的价格分配】")
    print(f"  平均售价需 = {p_mat:.1f} 金币")
    # 权重: 木板20, 毛线20, 铃铛20, 鱼干20, 猫砂18, 逗猫12
    weights = {
        "猫抓板木板": 20,
        "毛线团": 20,
        "小铃铛": 20,
        "特级小鱼干": 20,
        "水晶猫砂": 18,
        "彩虹逗猫棒": 12,
    }
    total_w = sum(weights.values())
    # 前四种（常见）价格 = P_mat × 0.7，后两种（稀有）价格 = P_mat × 2.5
    common_price = p_mat * 0.7
    rare_price = p_mat * 2.5
    weighted_avg = (
        common_price * (20 + 20 + 20 + 20) + rare_price * (18 + 12)
    ) / total_w
    # 微调使 weighted_avg ≈ p_mat
    adjust = p_mat / weighted_avg
    common_price *= adjust
    rare_price *= adjust
    print(f"  常见材料(木板/毛线/铃铛/鱼干): {common_price:.0f} 金币/个")
    print(f"  稀有材料(猫砂/逗猫棒):         {rare_price:.0f} 金币/个")
    print(f"  加权平均: {weighted_avg * adjust:.0f} 金币/个")

else:
    print(f"\n  ⚠️ 材料率 {m_required * 100:.1f}% 不在合理范围，需要调整鱼价折扣")
    # 尝试不同折扣
    print("\n  【尝试不同折扣值】")
    print(f"  {'discount':>10} {'E_fish(7)':>10} {'m需要':>8} {'可行':>6}")
    for disc in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        ef = E_fish_park(7, disc)
        m = 1 - 0.5 * v7 / ef
        ok = "✓" if 0.1 < m < 0.8 else "✗"
        print(f"  {disc:>10.1f} {ef:>10.1f} {m * 100:>7.1f}% {ok:>6}")
