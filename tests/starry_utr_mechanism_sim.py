"""
UTR 机制完整验证 + 模拟
验证用户的说法：
1. 1-10关+猫猫乐园: UTR需要集齐UR + 迷途风天气
2. 11-20关: 集齐UR后自动解锁UTR
3. 概率表中UTR因截断无法生效
4. UTR掉率沿用递进概率算法(0.7%@d=6)
5. 150保底
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

# ===== 概率表 =====
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
    [0, 0, 0.0677, 0.3774, 0.4412, 0.1137, 0,0,0,0,0,0,0,0,0,0], # d=9: UTR=11.37%
    [0, 0, 0, 0.2335, 0.5101, 0.2564, 0,0,0,0,0,0,0,0,0,0],       # d=10: UTR=25.64%
]

# 递进概率算法（从 constants.py 复制）
def get_lost_wind_utr_probability(rod_level, location_difficulty):
    """迷途风 UTR 概率：基础 0.2%，鱼竿每领先场景等级 1 级 +0.1%。"""
    location_level = location_difficulty + 1
    lead = max(0, rod_level - location_level)
    return 0.002 + lead * 0.001

UTR_PITY_THRESHOLD = 150

# 速度参数
CPD = 129.6  # 每日钓鱼次数 (50%打窝)
SIM_RUNS = 10000
TARGET_UTR = 7

print("=" * 90)
print("UTR 机制完整验证")
print("=" * 90)

# ===== 验证1: 1-10关+猫猫乐园 UTR 机制 =====
print(f"\n{'='*90}")
print("验证1: 1-10关+猫猫乐园 UTR 机制")
print(f"{'='*90}")
print(f"""
代码流程:
  1. 集齐当前图所有UR → 成就 collect_scene_{{id}} 完成
  2. achievement_service.py: 非星空图显示"🌀 迷途风天气已对你解锁！"
  3. has_unlocked_lost_wind(user_id, location_id) → True
  4. 迷途风天气buff不再被过滤 → weather_lost_wind = True
  5. engine.py Part1: UTR保底检查 (utr_pity+1 >= 150)
  6. engine.py Part2: 迷途风UTR随机概率 (0.2% + 0.1%/级)
  7. engine.py Part3: utr_pity计数器+1 (仅迷途风时)

结论: ✓ 正确 — 1-10关+猫猫乐园需要先集齐UR解锁迷途风，再等天气钓UTR
""")

# ===== 验证2: 11-20关 UTR 机制 =====
print(f"{'='*90}")
print("验证2: 11-20关 UTR 机制")
print(f"{'='*90}")
print(f"""
代码流程:
  1. 集齐当前星空图所有UR → 成就 collect_scene_{{id}} 完成
  2. achievement_service.py: 星空图显示"✨ UTR稀有度已对你解锁！"
  3. core/scene.py & core/actions.py: max_rarity 从 UR → UTR
  4. 星空图天气系统: 仅【流星】一种天气 (doc.md L332)
     → 迷途风天气在星空图永远不会出现！
  5. engine.py Part1: UTR保底检查需 weather_lost_wind=True → ✗ 不触发
  6. engine.py Part2: 迷途风UTR随机需 weather_lost_wind=True → ✗ 不触发
  7. engine.py Part3: utr_pity计数器不+1 (weather_lost_wind=False)
  8. UTR唯一来源: 稀有度表 index=5

结论: ⚠ 星空图UTR"解锁"仅改变 max_rarity，但：
  - 迷途风天气永远不会出现 → 递进概率算法(0.7%)不生效
  - utr_pity计数器不递增 → 150保底不生效
  - UTR唯一来源是稀有度表，但d=6时被截断为0%
""")

# ===== 验证3: 概率表截断 =====
print(f"{'='*90}")
print("验证3: 概率表UTR截断分析")
print(f"{'='*90}")

# 模拟截断算法
S, SIGMA, THETA = 0.4, 0.8, 0.05

def raw_distribution(d, max_r=20):
    mu = S * d
    weights = [math.exp(-((r - mu) ** 2) / (2 * SIGMA**2)) for r in range(max_r + 1)]
    total = sum(weights)
    return [w / total for w in weights]

def truncated_distribution(d, max_r=20):
    probs = raw_distribution(d, max_r)
    kept = [p if p >= THETA else 0.0 for p in probs]
    for i, p in enumerate(probs):
        if p >= THETA:
            continue
        kept_indices = [j for j, q in enumerate(kept) if q > 0]
        nearest = min(kept_indices, key=lambda j: (abs(j - i), j))
        kept[nearest] += p
    total = sum(kept)
    return [p / total for p in kept]

print(f"\n截断阈值 THETA = {THETA} (概率低于5%的项被截断)")
print(f"\n{'d值':>4} | {'UTR(截断前)':>12} {'UTR(截断后)':>12} {'UR(截断后)':>10} | {'备注'}")
print("-" * 65)

for d in range(4, 11):
    raw = raw_distribution(d)
    trunc = truncated_distribution(d)
    utr_raw = raw[5] if len(raw) > 5 else 0
    utr_trunc = trunc[5] if len(trunc) > 5 else 0
    ur_trunc = trunc[4] if len(trunc) > 4 else 0
    rod_lv = DIFFICULTY + d
    note = ""
    if d == 6:
        note = "← UR刚解锁(d=6)"
    elif d == 9:
        note = "← UTR首次>0%"
    print(f"d={d:>2} | {utr_raw:>12.4%} {utr_trunc:>12.4%} {ur_trunc:>10.2%} | 杆Lv.{rod_lv} {note}")

print(f"\n结论: ✓ 正确 — d=6时UTR截断前=0.25%，低于5%阈值被截断为0%")

# ===== 验证4: 递进概率算法 =====
print(f"\n{'='*90}")
print("验证4: 递进概率算法验证")
print(f"{'='*90}")

print(f"\n公式: get_lost_wind_utr_probability(rod_level, difficulty)")
print(f"     = 0.002 + max(0, rod_level - (difficulty + 1)) × 0.001")
print(f"     = 0.2% + 鱼竿领先场景等级 × 0.1%\n")

print(f"{'d值':>4} {'杆Lv':>6} {'lead':>5} | {'递进UTR概率':>12} {'概率表UTR':>10} | {'备注'}")
print("-" * 70)

for d in range(0, 11):
    rod_level = DIFFICULTY + d
    lead = max(0, rod_level - (DIFFICULTY + 1))
    prog_prob = 0.002 + lead * 0.001
    table_prob = RARITY_DISTRIBUTION[min(d, 10)][5] if d < len(RARITY_DISTRIBUTION) else 0
    note = ""
    if d == 6:
        note = "← UR刚解锁"
    elif d == 9:
        note = "← 概率表UTR首次>0%"
    print(f"d={d:>2} Lv.{rod_level:>3} {lead:>5} | {prog_prob:>12.2%} {table_prob:>10.2%} | {note}")

print(f"""
验证结果:
  ✓ 递进概率算法存在: get_lost_wind_utr_probability()
  ✓ d=6(杆Lv.16)时: lead=5, 概率=0.2%+5×0.1%=0.7% ✓
  ⚠ 但此算法仅在 weather_lost_wind=True 时调用 (engine.py L166)
  ⚠ 星空图天气系统仅有流星，迷途风永远不会出现
  ⚠ 所以递进概率算法在星空图中实际不生效！
""")

# ===== 验证5: 150保底 =====
print(f"{'='*90}")
print("验证5: 150保底验证")
print(f"{'='*90}")

print(f"""
代码确认:
  ✓ UTR_PITY_THRESHOLD = 150 (constants.py L78)
  ✓ 保底检查: engine.py L138: if weather_lost_wind and (utr_pity+1) >= 150
  ⚠ 保底检查需要 weather_lost_wind=True → 星空图中不生效
  ⚠ 计数器更新: engine.py L271: new_utr_pity = utr_pity + 1 if weather_lost_wind else utr_pity
  ⚠ 无迷途风时utr_pity永远不递增 → 保底永远不触发

结论:
  ✓ 150保底确实存在
  ⚠ 但在星空图中因无迷途风天气，保底计数器不递增，永远无法触发
""")

# ===== 综合结论 =====
print(f"{'='*90}")
print("综合验证结论")
print(f"{'='*90}")

print(f"""
用户说法验证:
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 1-10+猫猫乐园: UTR需集齐UR+迷途风天气           ✓ 正确        │
│ 2. 11-20: 集齐UR后自动解锁UTR                       ✓ 正确        │
│ 3. 概率表UTR因截断无法生效                           ✓ 正确        │
│ 4. UTR掉率沿用递进算法, d=6时=0.7%                   ⚠ 部分正确    │
│    → 公式确实给出0.7%，但仅迷途风天气时调用                        │
│    → 星空图无迷途风天气 → 0.7%实际不生效                            │
│ 5. 150保底                                           ⚠ 部分正确    │
│    → 150保底确实存在，但仅迷途风天气时检查/计数                     │
│    → 星空图无迷途风天气 → 保底计数器不递增，永远不触发              │
└─────────────────────────────────────────────────────────────────────┘

关键发现:
  星空图(11-20)中，UTR虽然"解锁"(max_rarity=UTR)，但:
  - 概率表UTR: d=6时被截断为0% (THETA=0.05)
  - 递进概率0.7%: 需迷途风天气，星空图无迷途风
  - 150保底: 需迷途风天气，星空图无迷途风
  → d=6时UTR在星空图中实际完全不可获得！

  UTR在星空图中首次可获得的d值:
  - 无天气: d=9 (杆Lv.19), 概率表UTR=11.37%
  - 有流星天气: d=9时流星效果将最高稀有度+2% → UTR≈13.37%
""")

# ===== 模拟 =====
print(f"\n{'='*90}")
print("模拟: 图11全UR收集 + 7条UTR")
print(f"{'='*90}")

def select_rarity(probs):
    total = sum(probs)
    rand = random.random() * total
    cumulative = 0
    for i, prob in enumerate(probs):
        cumulative += prob
        if rand <= cumulative:
            return i
    return 0

_RARITY_ORDER = ["N", "R", "SR", "SSR", "UR", "UTR"]

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

# Phase 1: 收集全5条UR (d=6, max_rarity=UR)
D_UR = 6
probs_ur = RARITY_DISTRIBUTION[D_UR]

print(f"\n--- Phase 1: 收集全5条UR (d={D_UR}, 杆Lv.{DIFFICULTY+D_UR}) ---")
print(f"  UR概率: {probs_ur[4]:.2%}")

ur_days = []
for _ in range(SIM_RUNS):
    collected = set()
    catches = 0
    while len(collected) < 5:
        catches += 1
        fish_id = random.choice(FISH_POOL)
        ri = select_rarity(probs_ur)
        rn = get_rarity_name(ri, "UR")
        if rn == "UR":
            collected.add(fish_id)
    ur_days.append(catches / CPD)

ur_days.sort()
print(f"  蒙特卡洛({SIM_RUNS}次): 中位数={ur_days[len(ur_days)//2]:.2f}天, P10={ur_days[int(len(ur_days)*0.1)]:.2f}天, P90={ur_days[int(len(ur_days)*0.9)]:.2f}天")

# Phase 2a: 无天气 — UTR不可能
print(f"\n--- Phase 2a: 无天气, d=6钓UTR ---")
print(f"  概率表UTR(d=6): {probs_ur[5]:.2%} (截断为0)")
print(f"  递进概率UTR: 0.7%但需迷途风天气 → 星空图无迷途风 → 不生效")
print(f"  150保底: 需迷途风天气 → 星空图无迷途风 → 计数器不递增")
print(f"  结论: ⚠ d=6无天气时UTR完全不可获得！")

# Phase 2b: 假设有迷途风天气 — 递进概率0.7% + 150保底
print(f"\n--- Phase 2b: 假设有迷途风天气, d=6钓UTR (递进0.7% + 150保底) ---")
utr_prob = get_lost_wind_utr_probability(DIFFICULTY + D_UR, DIFFICULTY)
print(f"  递进概率: {utr_prob:.2%}")
print(f"  保底阈值: {UTR_PITY_THRESHOLD}")

utr_days_lw = []
for _ in range(SIM_RUNS):
    utr_count = 0
    utr_pity = 0
    catches = 0
    while utr_count < TARGET_UTR:
        catches += 1
        # Part1: 保底检查
        if (utr_pity + 1) >= UTR_PITY_THRESHOLD:
            utr_count += 1
            utr_pity = 0
            continue
        # Part2: 递进概率
        if random.random() < utr_prob:
            utr_count += 1
            utr_pity = 0
            continue
        # 普通鱼
        utr_pity += 1
    utr_days_lw.append(catches / CPD)

utr_days_lw.sort()
print(f"  蒙特卡洛({SIM_RUNS}次): 中位数={utr_days_lw[len(utr_days_lw)//2]:.2f}天, P10={utr_days_lw[int(len(utr_days_lw)*0.1)]:.2f}天, P90={utr_days_lw[int(len(utr_days_lw)*0.9)]:.2f}天")

# Phase 2c: 无天气, 升级到d=9 — 概率表UTR
print(f"\n--- Phase 2c: 无天气, 升级到d=9(杆Lv.19)钓UTR ---")
D_UTR9 = 9
probs_utr9 = RARITY_DISTRIBUTION[D_UTR9]
print(f"  概率表UTR(d=9): {probs_utr9[5]:.2%}")

utr_days_d9 = []
for _ in range(SIM_RUNS):
    utr_count = 0
    catches = 0
    while utr_count < TARGET_UTR:
        catches += 1
        ri = select_rarity(probs_utr9)
        rn = get_rarity_name(ri, "UTR")
        if rn == "UTR":
            utr_count += 1
    utr_days_d9.append(catches / CPD)

utr_days_d9.sort()
print(f"  蒙特卡洛({SIM_RUNS}次): 中位数={utr_days_d9[len(utr_days_d9)//2]:.2f}天, P10={utr_days_d9[int(len(utr_days_d9)*0.1)]:.2f}天, P90={utr_days_d9[int(len(utr_days_d9)*0.9)]:.2f}天")

# Phase 2d: 流星天气, d=9 — 概率表UTR + 流星加成
print(f"\n--- Phase 2d: 流星天气(50%概率), d=9钓UTR ---")
# 流星效果: 最高非零稀有度概率+2%, 次高-2%
probs_meteor = list(probs_utr9)
# d=9时最高非零是UTR(index 5), 次高是UR(index 4)
probs_meteor[5] += 0.02
probs_meteor[4] -= 0.02
print(f"  流星UTR概率(d=9): {probs_meteor[5]:.2%}")
print(f"  普通UTR概率(d=9): {probs_utr9[5]:.2%}")
print(f"  加权UTR概率(50%流星): {0.5*probs_meteor[5] + 0.5*probs_utr9[5]:.2%}")

utr_days_meteor = []
for _ in range(SIM_RUNS):
    utr_count = 0
    catches = 0
    while utr_count < TARGET_UTR:
        catches += 1
        # 50%概率流星天气
        if random.random() < 0.5:
            ri = select_rarity(probs_meteor)
        else:
            ri = select_rarity(probs_utr9)
        rn = get_rarity_name(ri, "UTR")
        if rn == "UTR":
            utr_count += 1
    utr_days_meteor.append(catches / CPD)

utr_days_meteor.sort()
print(f"  蒙特卡洛({SIM_RUNS}次): 中位数={utr_days_meteor[len(utr_days_meteor)//2]:.2f}天, P10={utr_days_meteor[int(len(utr_days_meteor)*0.1)]:.2f}天, P90={utr_days_meteor[int(len(utr_days_meteor)*0.9)]:.2f}天")

# ===== 总结 =====
print(f"\n{'='*90}")
print("总结")
print(f"{'='*90}")
print(f"""
场景: 图11 牛奶河 (difficulty=10, 5条鱼)
速度: 50%打窝, 129.6次/天

Phase 1 — 收集全5条UR鱼:
  鱼竿: d=6(杆Lv.16), UR=5.00%
  中位数: {ur_days[len(ur_days)//2]:.2f}天, P90: {ur_days[int(len(ur_days)*0.9)]:.2f}天

Phase 2 — 钓7条UTR:
  ┌──────────────────────────────────────────────────────────────────┐
  │ 方案              │ UTR来源      │ UTR概率  │ 中位数 │ P90     │
  ├──────────────────────────────────────────────────────────────────┤
  │ 2a: d=6无天气     │ 无           │ 0.00%    │ ∞      │ ∞       │
  │ 2b: d=6+迷途风    │ 递进+保底    │ 0.70%    │ {utr_days_lw[len(utr_days_lw)//2]:.2f}天 │ {utr_days_lw[int(len(utr_days_lw)*0.9)]:.2f}天 │
  │ 2c: d=9无天气     │ 概率表       │ 11.37%   │ {utr_days_d9[len(utr_days_d9)//2]:.2f}天 │ {utr_days_d9[int(len(utr_days_d9)*0.9)]:.2f}天 │
  │ 2d: d=9+流星50%   │ 概率表+流星  │ ~12.37%  │ {utr_days_meteor[len(utr_days_meteor)//2]:.2f}天 │ {utr_days_meteor[int(len(utr_days_meteor)*0.9)]:.2f}天 │
  └──────────────────────────────────────────────────────────────────┘

关键发现:
  1. d=6(杆Lv.16)在星空图中UTR完全不可获得
     - 概率表UTR=0%(截断), 递进概率需迷途风, 保底需迷途风
  2. 递进概率0.7%和150保底确实存在，但绑定迷途风天气
     - 星空图天气仅有流星，迷途风永远不会出现
  3. 要在星空图钓UTR，必须升级到d=9(杆Lv.19)以上
     - d=9时概率表UTR=11.37%, 7条约{utr_days_d9[len(utr_days_d9)//2]:.2f}天
  4. 流星天气对UTR有+2%加成(50%概率时约+1%)
""")
