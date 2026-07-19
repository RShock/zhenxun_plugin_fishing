"""
猫猫乐园 v17 — 材料价格50~100，猫爬架重新设计
变更：
1. P目标降到50~100
2. 猫爬架广场: 材料率 +20%/25%/30%（原5/10/18%）
   → 材料率和鱼率是竞争关系，爬架越高→鱼越少
3. 扫描更高的D（0.85~0.95）

关键：爬架的材料率加成是直接加到材料率上的
比如基础材料率20%，爬架Lv3 +30% → 实际材料率 = 20% + 30% = 50%
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
        if loc["difficulty"] > rod: continue
        exp = LOC_AVG[loc["id"]] * calc_M_UR(rod - loc["difficulty"])
        if exp > best: best = exp
    return best

V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)

# buff
CASTLE_PROB = 0.30
PRICE_MULT = 1.10
DOUBLE_MULT = 1.05
WEATHER_BOOST = 1.04
SPEED_MULT = 1.10
BAIT_SAVE = 1.01
PER_CAST_MULT = PRICE_MULT * DOUBLE_MULT * WEATHER_BOOST
DAILY_MULT = PER_CAST_MULT * SPEED_MULT * BAIT_SAVE

def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)

def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)

def ef_park_daily(rod, D=1.0):
    return ef_castle(rod) * D * DAILY_MULT

# ═══ 猫爬架广场：材料率加成 ═══
# 基础材料率 m_base（无爬架时的材料率）
# 爬架Lv3 +30% → 实际材料率 = m_base + 0.30
# 但要注意：实际材料率不能超过100%

print("=" * 90)
print("  猫猫乐园 v17 — P=50/100, 爬架+20/25/30%, 扫描D=0.85~0.95")
print("=" * 90)

def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    return 60 / ((1 + hook*0.1) * (1 + (bait_bonus + min(nest_layers,10)*5 + min(frame_layers,10)*5)/100))
interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

# 扫描：基础材料率 m_base, 爬架加成, P, D
# 实际材料率 = m_base + 爬架
# ratio(10) = [实际m × P + (1-实际m) × D × ef_daily(10)] / V(10) = 1.0

ef_d10_raw = ef_park_daily(10, 1.0)  # D=1时的每天鱼收益

print(f"\n  ef_daily(10, D=1) = {ef_d10_raw:.1f}")
print(f"  V(10) = {V_cache[10]:.1f}")
print(f"  每24h = {casts_24h}竿")
print()

# ═══ 扫描矩阵 ═══
for target_P in [50, 100]:
    print(f"\n{'='*90}")
    print(f"  目标材料价格 P = {target_P} 金币")
    print(f"{'='*90}")

    for rack_add in [0.20, 0.25, 0.30]:  # 爬架Lv3加成
        print(f"\n  ┌─ 爬架Lv3 = +{rack_add*100:.0f}% 材料率 ─┐")

        for D_x100 in range(80, 100, 1):
            D = D_x100 / 100

            # 扫描基础材料率
            best_m_base = None
            best_score = 999

            for m_base_x10 in range(0, 700, 1):  # 0% ~ 70%
                m_base = m_base_x10 / 10
                m_actual = min(m_base + rack_add, 0.95)  # 实际材料率
                if m_actual >= 0.95: continue

                # ratio(10) = 1.0
                income10 = m_actual * target_P + (1 - m_actual) * D * ef_d10_raw
                ratio10 = income10 / V_cache[10]

                if abs(ratio10 - 1.0) > 0.02:
                    continue

                # 验证曲线
                ratios = {}
                for rod in range(7, 15):
                    income = m_actual*target_P + (1-m_actual)*D*ef_park_daily(rod, 1.0)
                    ratios[rod] = income / V_cache[rod]

                # 目标：r@9>100%, r@10≈100%, r@11<95%, r@12<85%
                if ratios[9] < 1.0 or ratios[11] > 0.95 or ratios[12] > 0.85:
                    continue

                # 评分：r@11越低越好
                score = ratios[11]
                if score < best_score:
                    best_score = score
                    best_m_base = m_base

            if best_m_base is not None:
                m_actual = best_m_base + rack_add
                ratios = {}
                for rod in range(7, 16):
                    income = m_actual*target_P + (1-m_actual)*D*ef_park_daily(rod, 1.0)
                    ratios[rod] = income / V_cache[rod]

                mats_day = casts_24h * m_actual
                rstr = " ".join(f"r{r}={ratios[r]*100:>4.0f}%" for r in [9,10,11,12,13])
                print(f"  │ D={D:.2f} m_base={best_m_base*100:>4.0f}% m_实际={m_actual*100:>4.0f}% P={target_P:>3} │ {rstr} │ {mats_day:>4.0f}个/天 │")

# ═══ 最佳方案详情 ═══
print(f"\n{'='*90}")
print(f"  最佳方案详情")
print(f"{'='*90}")

# 手动选几个好方案
best_configs = [
    # (P, rack, D, m_base)
    (50, 0.25, 0.88, None),   # P=50, 爬架25%
    (100, 0.20, 0.90, None),  # P=100, 爬架20%
    (100, 0.30, 0.92, None),  # P=100, 爬架30%
]

for target_P, rack_add, D_target, _ in best_configs:
    # 搜索匹配的m_base
    for m_base_x10 in range(0, 700, 1):
        m_base = m_base_x10 / 10
        m_actual = min(m_base + rack_add, 0.95)
        income10 = m_actual * target_P + (1 - m_actual) * D_target * ef_d10_raw
        ratio10 = income10 / V_cache[10]
        if abs(ratio10 - 1.0) > 0.02:
            continue
        ratios = {}
        for rod in range(7, 15):
            income = m_actual*target_P + (1-m_actual)*D_target*ef_park_daily(rod, 1.0)
            ratios[rod] = income / V_cache[rod]
        if ratios[9] < 1.0 or ratios[11] > 0.95 or ratios[12] > 0.85:
            continue

        # 找到了
        mats_day = casts_24h * m_actual
        print(f"\n  ── P={target_P}, 爬架+{rack_add*100:.0f}%, D={D_target:.2f}, m_base={m_base*100:.0f}%, m_实际={m_actual*100:.0f}% ──")
        print(f"  材料/天: {mats_day:.0f}个")
        print(f"  {'rod':>4} {'乐园每天':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
        print("  " + "-" * 45)
        for rod in range(7, 16):
            income = m_actual*target_P + (1-m_actual)*D_target*ef_park_daily(rod, 1.0)
            r = income / V_cache[rod]
            ev = "赚" if r>1.03 else ("平" if r>0.97 else "亏")
            print(f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r*100:>7.0f}% {ev:>6}")
        break
