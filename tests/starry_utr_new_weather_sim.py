"""
新模拟（截断修正版）：星空图概率表UTR永远截断为0
UTR唯一来源: 迷途风日递进概率 + 150保底
流星日: 概率表UTR=0%（截断），流星+2%加成作用于UR
"""
import random
import math
import json
import os

CONFIG_DIR = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\config"

with open(os.path.join(CONFIG_DIR, "locations.json"), encoding="utf-8") as f:
    locations = json.load(f)["locations"]

loc11 = next(l for l in locations if l["id"] == "11")
FISH_POOL = loc11["fish_pool"]
DIFFICULTY = loc11["difficulty"]  # 10

# 概率表
RARITY_DISTRIBUTION = [
    [0.6655, 0.3345, 0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.4964, 0.4246, 0.0790, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.3153, 0.5039, 0.1808, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0,0,0,0,0],
    [0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0,0,0,0,0],
    [0, 0.0291, 0.5209, 0.4000, 0.0500, 0,0,0,0,0,0,0,0,0,0,0],  # d=6: UR=5%
    [0, 0, 0.1937, 0.6863, 0.1200, 0,0,0,0,0,0,0,0,0,0,0],       # d=7
    [0, 0, 0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0,0,0,0,0],       # d=8
    [0, 0, 0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0,0,0], # d=9: 概率表UTR=11.37%
    [0, 0, 0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0,0,0],       # d=10: 概率表UTR=25.64%
]

_RARITY_ORDER = ["N", "R", "SR", "SSR", "UR", "UTR"]

def get_probs(d):
    return list(RARITY_DISTRIBUTION[min(d, len(RARITY_DISTRIBUTION)-1)])

def truncate_starry_utr(probs):
    """星空图截断: index>=5的概率全部置0，重分配给index=4(UR)"""
    new_probs = list(probs)
    truncated_mass = sum(new_probs[5:])
    new_probs = new_probs[:5] + [0.0] * (len(new_probs) - 5)
    if truncated_mass > 0:
        new_probs[4] += truncated_mass
    return new_probs

def select_rarity(probs):
    total = sum(probs)
    rand = random.random() * total
    cumulative = 0
    for i, prob in enumerate(probs):
        cumulative += prob
        if rand <= cumulative:
            return i
    return 0

def get_rarity_name(rarity_index, max_rarity_str):
    if 0 <= rarity_index < len(_RARITY_ORDER):
        name = _RARITY_ORDER[rarity_index]
    else:
        name = _RARITY_ORDER[0]
    max_idx = _RARITY_ORDER.index(max_rarity_str) if max_rarity_str in _RARITY_ORDER else len(_RARITY_ORDER) - 1
    r_idx = _RARITY_ORDER.index(name) if name in _RARITY_ORDER else 0
    if r_idx > max_idx:
        return _RARITY_ORDER[max_idx]
    return name

def get_lost_wind_utr_probability(rod_level, location_difficulty):
    location_level = location_difficulty + 1
    lead = max(0, rod_level - location_level)
    return 0.002 + lead * 0.001

def apply_meteor_effect(probs):
    """流星效果: 最高非零稀有度概率+2%, 次高-2%"""
    new_probs = list(probs)
    nonzero_indices = [i for i, p in enumerate(new_probs) if p > 0]
    if len(nonzero_indices) >= 2:
        highest = max(nonzero_indices)
        second = max(i for i in nonzero_indices if i != highest)
        new_probs[highest] += 0.02
        new_probs[second] -= 0.02
    return new_probs

UTR_PITY_THRESHOLD = 150
CPD = 129.6  # 每日钓鱼次数 (50%打窝)
SIM_RUNS = 10000
TARGET_UTR = 7

print("=" * 90)
print("新模拟（截断修正版）：星空图概率表UTR永远截断为0")
print("=" * 90)
print(f"\n场景: 图11 牛奶河 (difficulty={DIFFICULTY}, 5条鱼)")
print(f"速度: 50%打窝, {CPD:.1f}次/天")
print(f"天气: 50%迷途风 + 50%流星")
print(f"截断规则: 概率表index>=5全部置0, 概率质量重分配给UR(index=4)")
print(f"UTR唯一来源: 迷途风日递进概率 + 150保底")
print(f"模拟次数: {SIM_RUNS}")

# 验证截断后的概率表
print(f"\n{'='*90}")
print("截断后概率表验证")
print(f"{'='*90}")
print(f"{'d值':>4} | {'截断前UTR':>10} {'截断后UTR':>10} {'截断后UR':>10} | {'流星日UR(+2%)':>14} {'流星日次高(-2%)':>14}")
print("-" * 80)
for d in [6, 9, 10]:
    raw = get_probs(d)
    trunc = truncate_starry_utr(raw)
    meteor = apply_meteor_effect(trunc)
    utr_raw = raw[5]
    utr_trunc = trunc[5]
    ur_trunc = trunc[4]
    ur_meteor = meteor[4]
    # 找次高
    nonzero = [i for i, p in enumerate(meteor) if p > 0]
    second = max(i for i in nonzero if i != max(nonzero)) if len(nonzero) >= 2 else -1
    second_val = meteor[second] if second >= 0 else 0
    second_name = _RARITY_ORDER[second] if second >= 0 else "-"
    print(f"d={d:>2} | {utr_raw:>10.2%} {utr_trunc:>10.2%} {ur_trunc:>10.2%} | {ur_meteor:>14.2%} {second_name}:{second_val:>10.2%}")

# ===== Phase 1: 收集全5条UR (d=6, max_rarity=UR) =====
D_UR = 6
# Phase 1时max_rarity=UR, 所以UTR本来就封顶为UR, 不受截断影响
# 但概率表截断会改变UR的概率(把UTR概率加到UR上)
probs_ur_raw = get_probs(D_UR)
probs_ur_trunc = truncate_starry_utr(probs_ur_raw)

print(f"\n{'='*90}")
print(f"Phase 1: 收集全5条UR (d={D_UR}, 杆Lv.{DIFFICULTY+D_UR})")
print(f"  截断前: UR={probs_ur_raw[4]:.2%}, UTR={probs_ur_raw[5]:.2%}")
print(f"  截断后: UR={probs_ur_trunc[4]:.2%}, UTR={probs_ur_trunc[5]:.2%}")
print(f"  (Phase 1时max_rarity=UR, UTR被封顶为UR, 截断影响不大)")
print(f"{'='*90}")

ur_days = []
for _ in range(SIM_RUNS):
    collected = set()
    catches = 0
    while len(collected) < 5:
        catches += 1
        is_lost_wind_day = random.random() < 0.5
        if is_lost_wind_day:
            ri = select_rarity(probs_ur_trunc)
            rn = get_rarity_name(ri, "UR")
        else:
            probs_meteor = apply_meteor_effect(probs_ur_trunc)
            ri = select_rarity(probs_meteor)
            rn = get_rarity_name(ri, "UR")
        fish_id = random.choice(FISH_POOL)
        if rn == "UR":
            collected.add(fish_id)
    ur_days.append(catches / CPD)

ur_days.sort()
ur_median = ur_days[len(ur_days)//2]
ur_p10 = ur_days[int(len(ur_days)*0.1)]
ur_p90 = ur_days[int(len(ur_days)*0.9)]
print(f"  中位数: {ur_median:.2f}天, P10: {ur_p10:.2f}天, P90: {ur_p90:.2f}天")

# ===== Phase 2: 钓7条UTR (max_rarity=UTR, 但概率表UTR被截断) =====
# 迷途风日: 递进概率 + 150保底 (概率表UTR被截断为0)
# 流星日: 概率表UTR=0(截断), 流星+2%作用于UR, 无法获得UTR

def simulate_utr_collection(d, rod_level):
    """模拟钓7条UTR"""
    probs_raw = get_probs(d)
    probs_trunc = truncate_starry_utr(probs_raw)
    utr_prob_lw = get_lost_wind_utr_probability(rod_level, DIFFICULTY)

    print(f"\n  d={d}(杆Lv.{rod_level}):")
    print(f"    截断前: UR={probs_raw[4]:.2%}, UTR={probs_raw[5]:.2%}")
    print(f"    截断后: UR={probs_trunc[4]:.2%}, UTR={probs_trunc[5]:.2%}")
    print(f"    迷途风日(50%): 递进概率={utr_prob_lw:.2%} + 150保底")
    print(f"    流星日(50%): UTR=0%(截断), 流星+2%加成作用于UR, 无法获得UTR")

    utr_days = []
    for _ in range(SIM_RUNS):
        utr_count = 0
        utr_pity = 0
        catches = 0
        while utr_count < TARGET_UTR:
            catches += 1
            is_lost_wind_day = random.random() < 0.5

            if is_lost_wind_day:
                # 迷途风日: 保底 → 递进 → 概率表(UTR=0)
                if (utr_pity + 1) >= UTR_PITY_THRESHOLD:
                    utr_count += 1
                    utr_pity = 0
                    continue
                if random.random() < utr_prob_lw:
                    utr_count += 1
                    utr_pity = 0
                    continue
                # 概率表UTR被截断为0，不会产生UTR
                utr_pity += 1
            else:
                # 流星日: UTR=0%(截断), 无法获得UTR, pity不递增
                pass
        utr_days.append(catches / CPD)

    utr_days.sort()
    median = utr_days[len(utr_days)//2]
    p10 = utr_days[int(len(utr_days)*0.1)]
    p90 = utr_days[int(len(utr_days)*0.9)]
    mean = sum(utr_days)/len(utr_days)
    print(f"    中位数: {median:.2f}天, 均值: {mean:.2f}天, P10: {p10:.2f}天, P90: {p90:.2f}天")
    return median, p10, p90

print(f"\n{'='*90}")
print("Phase 2: 钓7条UTR（概率表UTR截断为0, 仅迷途风递进+保底）")
print(f"{'='*90}")

print("\n--- 2a: d=6 (杆Lv.16) ---")
d6_med, d6_p10, d6_p90 = simulate_utr_collection(6, DIFFICULTY+6)

print("\n--- 2b: d=9 (杆Lv.19) ---")
d9_med, d9_p10, d9_p90 = simulate_utr_collection(9, DIFFICULTY+9)

print("\n--- 2c: d=10 (杆Lv.20) ---")
d10_med, d10_p10, d10_p90 = simulate_utr_collection(10, DIFFICULTY+10)

# ===== 总结 =====
print(f"\n{'='*90}")
print("总结：全UR收集 + 7条UTR（概率表UTR截断版）")
print(f"{'='*90}")
print(f"""
场景: 图11 牛奶河 (difficulty=10, 5条鱼)
速度: 50%打窝, {CPD:.1f}次/天
天气: 50%迷途风 + 50%流星
截断: 概率表UTR(index>=5)永远为0, UTR仅来自迷途风递进+保底

Phase 1 — 收集全5条UR (d=6, 杆Lv.16):
  中位数: {ur_median:.2f}天, P90: {ur_p90:.2f}天

Phase 2 — 钓7条UTR:
┌──────────────────────────────────────────────────────────────────────────────┐
│ 鱼竿等级      │ 迷途风日UTR           │ 流星日UTR   │ 中位数   │ P90      │
├──────────────────────────────────────────────────────────────────────────────┤
│ d=6 (Lv.16)  │ 递进0.7%+150保底      │ 无(截断)    │ {d6_med:>7.2f}天 │ {d6_p90:>7.2f}天 │
│ d=9 (Lv.19)  │ 递进1.0%+150保底      │ 无(截断)    │ {d9_med:>7.2f}天 │ {d9_p90:>7.2f}天 │
│ d=10(Lv.20)  │ 递进1.1%+150保底      │ 无(截断)    │ {d10_med:>7.2f}天 │ {d10_p90:>7.2f}天 │
└──────────────────────────────────────────────────────────────────────────────┘

关键发现:
  1. 概率表UTR在星空图中被截断为0，无论d值多大
  2. UTR唯一来源: 迷途风日(50%)的递进概率 + 150保底
  3. 流星日(50%)完全无法获得UTR
  4. d=6全UR({ur_median:.2f}天) + 全UTR({d6_med:.2f}天) = {ur_median+d6_med:.2f}天(中位数)
  5. d值提升对UTR收集速度的提升有限(仅递进概率从0.7%→1.1%)
""")
