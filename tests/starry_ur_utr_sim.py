"""
图11(牛奶河)钓鱼模拟：
1. 鱼竿 d=6（rod_level=16, difficulty=10 → UR概率5%）
2. 50%玉米打窝速度，无天气
3. 目标A：收集全5条UR鱼
4. 目标B：钓到至少7条UTR鱼
"""
import random
import math
import json
import os

CONFIG_DIR = r"c:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing\config"

with open(os.path.join(CONFIG_DIR, "locations.json"), encoding="utf-8") as f:
    locations = json.load(f)["locations"]
with open(os.path.join(CONFIG_DIR, "fish.json"), encoding="utf-8") as f:
    fish_map = {e["id"]: e["base_price"] for e in json.load(f)["fish"]}

loc11 = next(l for l in locations if l["id"] == "11")
FISH_POOL = loc11["fish_pool"]  # 5条鱼
DIFFICULTY = loc11["difficulty"]  # 10

# ===== 概率表（从 constants.py 复制）=====
RARITY_DISTRIBUTION = [
    [0.6655, 0.3345, 0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.4964, 0.4246, 0.0790, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.3153, 0.5039, 0.1808, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0,0,0,0,0,0,0],
    [0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0,0,0,0,0],
    [0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0,0,0,0,0],
    [0, 0.0291, 0.5209, 0.4000, 0.0500, 0,0,0,0,0,0,0,0,0,0,0],  # d=6: UR=5%
    [0, 0, 0.1937, 0.6863, 0.1200, 0,0,0,0,0,0,0,0,0,0,0],       # d=7: UR=12%
    [0, 0, 0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0,0,0,0,0],       # d=8: UR=34.72%
    [0, 0, 0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0,0,0], # d=9: UR=44%, UTR=11.37%
    [0, 0, 0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0,0,0],       # d=10: UTR=25.64%
    [0, 0, 0, 0.1085, 0.4426, 0.3785, 0.0704, 0,0,0,0,0,0,0,0,0], # d=11
    [0, 0, 0, 0, 0.3153, 0.5039, 0.1808, 0,0,0,0,0,0,0,0,0],     # d=12
    [0, 0, 0, 0, 0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0,0,0],     # d=13
    [0, 0, 0, 0, 0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0], # d=14
    [0, 0, 0, 0, 0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0],    # d=15
    [0, 0, 0, 0, 0, 0.1085, 0.4426, 0.3785, 0.0704, 0,0,0,0,0,0,0], # d=16
    [0, 0, 0, 0, 0, 0, 0.3153, 0.5039, 0.1808, 0,0,0,0,0,0,0],   # d=17
    [0, 0, 0, 0, 0, 0, 0.1638, 0.4890, 0.3472, 0,0,0,0,0,0,0],   # d=18
    [0, 0, 0, 0, 0, 0, 0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0], # d=19
    [0, 0, 0, 0, 0, 0, 0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0], # d=20
]

# 稀有度名称映射（与engine.py一致）
# 注意：engine.py中 _RARITY_ORDER 只有6个元素，index>=6 会映射为 "N"
_RARITY_ORDER = ["N", "R", "SR", "SSR", "UR", "UTR"]

def get_rarity_name(rarity_index, max_rarity_str):
    """模拟engine.py的稀有度映射 + 封顶逻辑"""
    if 0 <= rarity_index < len(_RARITY_ORDER):
        name = _RARITY_ORDER[rarity_index]
    else:
        name = _RARITY_ORDER[0]  # index>=6 → "N" (engine行为)
    # 封顶
    max_idx = _RARITY_ORDER.index(max_rarity_str) if max_rarity_str in _RARITY_ORDER else len(_RARITY_ORDER) - 1
    r_idx = _RARITY_ORDER.index(name) if name in _RARITY_ORDER else 0
    if r_idx > max_idx:
        return _RARITY_ORDER[max_idx]
    return name

def get_probs(d):
    """获取d值对应的概率表"""
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    return RARITY_DISTRIBUTION[d]

def select_rarity(probs):
    """按概率抽选稀有度索引（与engine._select_rarity一致）"""
    total = sum(probs)
    rand = random.random() * total
    cumulative = 0
    for i, prob in enumerate(probs):
        cumulative += prob
        if rand <= cumulative:
            return i
    return 0

def get_rarity_dict(d):
    """获取6个稀有度的概率字典（用于展示）"""
    probs = get_probs(d)
    result = {}
    for i, key in enumerate(_RARITY_KEYS):
        if i < len(_RARITY_KEYS) - 1:
            result[key] = probs[i]
        else:
            result[key] = sum(probs[i:])
    return result

_RARITY_KEYS = ["N", "R", "SR", "SSR", "UR", "UTR"]

# ===== 速度参数（50%玉米打窝，无天气，星空图）=====
HOOK_MULT = 2.0       # 鱼钩Lv.10 → +100%
BAIT_NEST_MULT = 1 + (120 + 50) / 100  # 鱼饵120% + 打窝50% → 2.7
TOTAL_SPEED = HOOK_MULT * BAIT_NEST_MULT  # 5.4
BASE_INTERVAL = 60
CPD = 24 * 60 / (BASE_INTERVAL / TOTAL_SPEED)  # 129.6 次/天

# ===== 模拟参数 =====
SIM_RUNS = 10000  # 蒙特卡洛模拟次数
TARGET_UTR = 7

print("=" * 90)
print("图11(牛奶河) 钓鱼模拟")
print("=" * 90)
print(f"\n场景: {loc11['name']} (difficulty={DIFFICULTY})")
print(f"鱼池: {FISH_POOL} ({len(FISH_POOL)}条鱼)")
print(f"鱼价: {[fish_map[fn] for fn in FISH_POOL]}")
print(f"\n速度参数:")
print(f"  鱼钩: Lv.10 → +100% (×2.0)")
print(f"  鱼饵+打窝: +120%+50% = +170% (×2.7)")
print(f"  总速度: ×{TOTAL_SPEED}")
print(f"  每日钓鱼次数: {CPD:.1f}")
print(f"  模拟次数: {SIM_RUNS}")

# ===== 概率表分析 =====
print(f"\n{'=' * 90}")
print("各d值概率分析")
print(f"{'=' * 90}")
print(f"{'d值':>4} | {'N':>7} {'R':>7} {'SR':>7} {'SSR':>7} {'UR':>7} {'UTR(表)':>8} {'UTR(实际)':>9} | {'备注'}")
print("-" * 80)

for d in range(0, 13):
    probs = get_probs(d)
    # engine实际行为：index 5 → "UTR"，index 6+ → "N"
    n_prob = probs[0]
    r_prob = probs[1]
    sr_prob = probs[2]
    ssr_prob = probs[3]
    ur_prob = probs[4]
    utr_table = sum(probs[5:])  # 理论UTR（所有index 5+）
    utr_actual = probs[5]  # 实际UTR（仅index 5，因为6+映射为N）
    n_actual = probs[0] + sum(probs[6:])  # N包括原始N和index 6+

    rod_level = DIFFICULTY + d
    note = ""
    if d == 6:
        note = "← 用户指定 (5% UR)"
    elif ur_prob > 0 and utr_table == 0:
        note = "有UR无UTR"
    elif utr_table > 0:
        note = "有UTR"

    print(f"d={d:>2} | {n_actual:>7.2%} {r_prob:>7.2%} {sr_prob:>7.2%} {ssr_prob:>7.2%} {ur_prob:>7.2%} {utr_table:>8.2%} {utr_actual:>9.2%} | 杆Lv.{rod_level} {note}")

print(f"\n  注: 'UTR(表)'为理论值(sum(probs[5:])), 'UTR(实际)'为engine实际行为(仅index=5)")
print(f"  engine中 index>=6 的概率会被映射为 'N' (engine.py _RARITY_ORDER 仅6个元素)")

# ===== 目标A: 收集全5条UR鱼 (d=6, max_rarity=UR) =====
D_UR = 6
ROD_LEVEL_UR = DIFFICULTY + D_UR  # 16
probs_ur_phase = get_probs(D_UR)

print(f"\n{'=' * 90}")
print(f"目标A: 收集全5条UR鱼 (d={D_UR}, 杆Lv.{ROD_LEVEL_UR})")
print(f"{'=' * 90}")

# 展示概率
rarity_dict = {}
for i, key in enumerate(_RARITY_KEYS):
    if i < 5:
        rarity_dict[key] = probs_ur_phase[i]
    else:
        rarity_dict[key] = sum(probs_ur_phase[i:])
print(f"概率分布: {rarity_dict}")
print(f"  UR概率: {rarity_dict['UR']:.2%}")
print(f"  UTR概率: {rarity_dict['UTR']:.2%} (封顶为UR, max_rarity=UR)")

# 理论期望值
# 每次钓鱼: 5% UR, 随机选5条鱼之一
# 集齐5条UR的期望次数 = sum(1/(p*(n-k+1)/n)) for k=1..5 where p=UR率, n=5
expected_catches = 0
for k in range(1, 6):
    p_new_ur = rarity_dict['UR'] * (6 - k) / 5  # 还有(5-k+1)=6-k条未收集
    expected_catches += 1 / p_new_ur
expected_days = expected_catches / CPD
print(f"\n理论期望值:")
print(f"  期望钓鱼次数: {expected_catches:.1f}")
print(f"  期望天数: {expected_days:.2f}天")

# 蒙特卡洛模拟
print(f"\n蒙特卡洛模拟 ({SIM_RUNS}次):")
ur_days_list = []
for run in range(SIM_RUNS):
    collected_ur = set()
    catches = 0
    while len(collected_ur) < 5:
        catches += 1
        # 先选鱼
        fish_id = random.choice(FISH_POOL)
        # 再选稀有度
        rarity_index = select_rarity(probs_ur_phase)
        rarity_name = get_rarity_name(rarity_index, "UR")  # max_rarity=UR
        if rarity_name == "UR":
            collected_ur.add(fish_id)
    days = catches / CPD
    ur_days_list.append(days)

ur_days_list.sort()
median_days = ur_days_list[len(ur_days_list) // 2]
p10 = ur_days_list[int(len(ur_days_list) * 0.10)]
p25 = ur_days_list[int(len(ur_days_list) * 0.25)]
p75 = ur_days_list[int(len(ur_days_list) * 0.75)]
p90 = ur_days_list[int(len(ur_days_list) * 0.90)]
mean_days = sum(ur_days_list) / len(ur_days_list)

print(f"  均值: {mean_days:.2f}天")
print(f"  中位数: {median_days:.2f}天")
print(f"  P10(运气好): {p10:.2f}天")
print(f"  P25: {p25:.2f}天")
print(f"  P75: {p75:.2f}天")
print(f"  P90(运气差): {p90:.2f}天")
print(f"  最短: {min(ur_days_list):.2f}天")
print(f"  最长: {max(ur_days_list):.2f}天")

# ===== 目标B: 钓到7条UTR =====
print(f"\n{'=' * 90}")
print(f"目标B: 钓到至少{TARGET_UTR}条UTR")
print(f"{'=' * 90}")

# 在星空图(11-20)中，UTR的来源:
# 1. 木框保底: ✗ 星空图不触发
# 2. 木框随机0.7%: ✗ 星空图不触发
# 3. 迷途风UTR随机0.2%: ✗ 需要迷途风天气
# 4. 迷途风UTR保底150次: ✗ 需要迷途风天气
# 5. 稀有度表UTR: ✓ 仅当 max_rarity=UTR (需集齐全UR解锁成就) 且 d>=9

# 解锁UTR需要先集齐全UR(目标A完成)
# 解锁后 max_rarity = UTR

print(f"\nUTR来源分析(星空图, 无天气):")
print(f"  1. 展示木框保底: ✗ 星空图不触发")
print(f"  2. 展示木框随机0.7%: ✗ 星空图不触发")
print(f"  3. 迷途风UTR随机: ✗ 需要迷途风天气")
print(f"  4. 迷途风UTR保底: ✗ 需要迷途风天气")
print(f"  5. 稀有度表UTR: ✓ 需max_rarity=UTR(集齐全UR后解锁) + d>=9")

# d=6时的UTR概率
utr_prob_d6 = get_probs(D_UR)[5]  # index 5 = UTR
print(f"\n  d={D_UR}(杆Lv.{ROD_LEVEL_UR})时 UTR概率: {utr_prob_d6:.2%}")
if utr_prob_d6 == 0:
    print(f"  ⚠ d={D_UR}时 UTR概率为0%！此杆等级无法钓到UTR！")
    print(f"  要钓到UTR需要 d>=9 (杆Lv.{DIFFICULTY+9})")

# 展示各d值的UTR可行性
print(f"\n各d值UTR可行性分析:")
print(f"{'d值':>4} {'杆Lv':>6} | {'UR概率':>8} {'UTR概率':>9} | {'7条UTR期望天数':>15} | {'备注'}")
print("-" * 70)
for d in range(6, 13):
    probs = get_probs(d)
    ur_p = probs[4]
    utr_p = probs[5]  # 实际UTR概率(index=5)
    rod_lv = DIFFICULTY + d
    if utr_p > 0:
        exp_catches = TARGET_UTR / utr_p
        exp_days = exp_catches / CPD
        note = ""
        if d == 6:
            note = "← 用户指定杆"
        elif d == 9:
            note = "← 最低可钓UTR"
        print(f"d={d:>2} Lv.{rod_lv:>3} | {ur_p:>8.2%} {utr_p:>9.2%} | {exp_days:>15.2f}天 | {note}")
    else:
        note = "无法钓UTR" if d <= 8 else ""
        if d == 6:
            note = "← 用户指定杆, 无法钓UTR"
        print(f"d={d:>2} Lv.{rod_lv:>3} | {ur_p:>8.2%} {utr_p:>9.2%} | {'∞':>15} | {note}")

# ===== 综合模拟: d=6收集全UR → 升级杆到d=10钓7条UTR =====
print(f"\n{'=' * 90}")
print("综合模拟方案: d=6收集全UR → 升级杆后钓7条UTR")
print(f"{'=' * 90}")

# 用户完成全UR收集后，UTR解锁
# 但d=6时UTR=0%，需要升级鱼竿
# 假设用户升级到 d=10 (杆Lv.20) 钓UTR
D_UTR = 10
ROD_LEVEL_UTR = DIFFICULTY + D_UTR  # 20
probs_utr_phase = get_probs(D_UTR)
utr_prob = probs_utr_phase[5]
print(f"\n方案1: d=6收集全UR → 升级到d={D_UTR}(杆Lv.{ROD_LEVEL_UTR}) → 钓7条UTR")
print(f"  UTR概率: {utr_prob:.2%}")

# 蒙特卡洛: d=10钓7条UTR
utr_days_list = []
for run in range(SIM_RUNS):
    utr_count = 0
    catches = 0
    while utr_count < TARGET_UTR:
        catches += 1
        rarity_index = select_rarity(probs_utr_phase)
        rarity_name = get_rarity_name(rarity_index, "UTR")  # max_rarity=UTR
        if rarity_name == "UTR":
            utr_count += 1
    days = catches / CPD
    utr_days_list.append(days)

utr_days_list.sort()
print(f"  蒙特卡洛({SIM_RUNS}次):")
print(f"    均值: {sum(utr_days_list)/len(utr_days_list):.2f}天")
print(f"    中位数: {utr_days_list[len(utr_days_list)//2]:.2f}天")
print(f"    P10: {utr_days_list[int(len(utr_days_list)*0.10)]:.2f}天")
print(f"    P90: {utr_days_list[int(len(utr_days_list)*0.90)]:.2f}天")

# 方案2: d=9
D_UTR2 = 9
probs_utr2 = get_probs(D_UTR2)
utr_prob2 = probs_utr2[5]
print(f"\n方案2: d=6收集全UR → 升级到d={D_UTR2}(杆Lv.{DIFFICULTY+D_UTR2}) → 钓7条UTR")
print(f"  UTR概率: {utr_prob2:.2%}")

utr_days_list2 = []
for run in range(SIM_RUNS):
    utr_count = 0
    catches = 0
    while utr_count < TARGET_UTR:
        catches += 1
        rarity_index = select_rarity(probs_utr2)
        rarity_name = get_rarity_name(rarity_index, "UTR")
        if rarity_name == "UTR":
            utr_count += 1
    days = catches / CPD
    utr_days_list2.append(days)

utr_days_list2.sort()
print(f"  蒙特卡洛({SIM_RUNS}次):")
print(f"    均值: {sum(utr_days_list2)/len(utr_days_list2):.2f}天")
print(f"    中位数: {utr_days_list2[len(utr_days_list2)//2]:.2f}天")
print(f"    P10: {utr_days_list2[int(len(utr_days_list2)*0.10)]:.2f}天")
print(f"    P90: {utr_days_list2[int(len(utr_days_list2)*0.90)]:.2f}天")

# ===== 总结 =====
print(f"\n{'=' * 90}")
print("总结")
print(f"{'=' * 90}")
print(f"""
场景: 图11 牛奶河 (difficulty=10, 5条鱼)
速度: 50%打窝, 129.6次/天

目标A — 收集全5条UR鱼:
  鱼竿: d=6 (杆Lv.16), UR概率=5.00%
  理论期望: {expected_catches:.1f}次 ≈ {expected_days:.2f}天
  蒙特卡洛中位数: {median_days:.2f}天
  90%玩家在 {p90:.2f}天 内完成

目标B — 钓到7条UTR:
  ⚠ d=6(杆Lv.16)时 UTR概率=0.00%，无法钓到UTR！
  星空图UTR仅来自稀有度表(index=5)，需要 d>=9
  
  升级方案:
  ├─ d=9  (杆Lv.19): UTR=11.37%, 7条期望≈{TARGET_UTR/0.1137/CPD:.2f}天, 中位数={utr_days_list2[len(utr_days_list2)//2]:.2f}天
  └─ d=10 (杆Lv.20): UTR=25.64%, 7条期望≈{TARGET_UTR/0.2564/CPD:.2f}天, 中位数={utr_days_list[len(utr_days_list)//2]:.2f}天

  注: UTR解锁需先集齐全UR(目标A), 解锁后max_rarity从UR变为UTR
""")
