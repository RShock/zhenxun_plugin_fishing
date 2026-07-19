"""
诊断 balance_v20 失效根因：V_cache 是否被 11-20 星空地图污染
验证方式：用「排除星空图的基准」重跑 v20 扫描，看是否恢复有解。
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

STARRY_IDS = {str(i) for i in range(11, 21)}


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
NORMAL_LOCS = [l for l in LOCATIONS if l["id"] not in STARRY_IDS]


def V_normal(rod, locs):
    best, best_loc = 0, None
    for loc in locs:
        if loc["difficulty"] > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M_UR(rod - loc["difficulty"])
        if exp > best:
            best, best_loc = exp, loc
    return best, best_loc


print("=" * 92)
print("  balance_v20 失效根因诊断")
print("=" * 92)

# V_cache 对比
print(f"\n  rod |  仅1-10图基准        |  含星空11-20(v20现状)    |  是否被污染")
print(f"      |  V_cache  来源       |  V_cache  来源           |")
print("  " + "-" * 80)
for rod in range(7, 16):
    v_norm, loc_norm = V_normal(rod, NORMAL_LOCS)
    v_all, loc_all = V_normal(rod, LOCATIONS)
    mark = " ⚠是" if abs(v_all - v_norm) > 0.5 else ""
    print(f"  {rod:>3} | {v_norm:>8.1f} {loc_norm['name']:<8} | {v_all:>8.1f} {loc_all['name']:<10}{mark}")

# 用排除星空的基准重跑 v20 扫描，看是否恢复有解
PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)
CASTLE_PROB = 0.30
DAILY_MULT = 1.10 * 1.10 * 1.04 * 1.10 * 1.01  # 新版（逗猫棒10%）


def ef_raw(rod):
    return park_avg * calc_M_UR(max(0, rod - PARK_DIFF))


def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)


def ef_park_daily(rod, D=1.0):
    return ef_castle(rod) * D * DAILY_MULT


def run_scan(use_starry):
    """复用 v20 约束扫描，use_starry=True 用含星空的 V_cache，False 用仅1-10"""
    locs = LOCATIONS if use_starry else NORMAL_LOCS
    Vc = {rod: V_normal(rod, locs)[0] for rod in range(1, 20)}
    ef_d10 = ef_park_daily(10, 1.0)

    def solve_m(D, P):
        num = Vc[10] - D * ef_d10
        den = P - D * ef_d10
        return None if abs(den) < 0.001 else num / den

    solutions = []
    for P_target in range(40, 351, 5):
        for D_x100 in range(80, 100):
            D = D_x100 / 100
            m = solve_m(D, P_target)
            if m is None or m < 0.01 or m > 0.95:
                continue
            ratios = {}
            for rod in range(7, 16):
                income = m * P_target + (1 - m) * D * ef_park_daily(rod, 1.0)
                ratios[rod] = income / Vc[rod]
            ok = (ratios[9] >= 1.00 and abs(ratios[10] - 1.0) < 0.02 and
                  ratios[11] <= 0.99 and ratios[7] <= 1.40 and ratios[8] <= 1.25)
            if ok:
                solutions.append((D, P_target, m, ratios))
    solutions.sort(key=lambda x: (-x[0], x[1]))
    return solutions, Vc


print(f"\n{'='*92}")
print("  修复验证：同一套 v20 约束，两种基准下的可行解数量")
print(f"{'='*92}")

sol_starry, Vc_starry = run_scan(use_starry=True)
sol_normal, Vc_normal = run_scan(use_starry=False)

print(f"\n  含星空基准 (v20 现状)  : {len(sol_starry)} 个可行解")
print(f"  仅1-10图基准 (修复后)  : {len(sol_normal)} 个可行解")

if sol_normal:
    print(f"\n  → 排除星空图后约束恢复可解，证明失效根因就是 V_cache 被星空污染。")
    print(f"\n  修复后前5个解（D降序）：")
    print(f"    {'D':>5} {'P':>5} {'m':>5} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6}")
    print("    " + "-" * 70)
    for D, P, m, ratios in sol_normal[:5]:
        rstr = " ".join(f"{ratios[r]*100:>5.0f}%" for r in range(7, 14))
        print(f"    {D:>5.2f} {P:>5} {m*100:>4.0f}% {rstr}")
else:
    print(f"\n  → 排除星空后仍无解，说明约束本身还需要进一步放宽。")

# 当前约束总结
print(f"\n{'='*92}")
print("  当前 v20 约束（联立 5 条）")
print(f"{'='*92}")
print("""
  r@rod = ( m·P + (1-m)·D·ef_park_daily(rod) ) / V_cache[rod]

  约束：
    r@9  ≥ 100%        （9图不亏）
    r@10 ≈ 100% (±2%)  （10图持平锚点）
    r@11 ≤ 99%         （11图亏，制造升级动力）
    r@7  ≤ 140%        （7图不爆表）
    r@8  ≤ 125%        （8图不爆表）

  变量：m(刷图占比)∈[1%,95%], D(乐园系数)∈[0.80,0.99], P(非乐园单次收益)∈[40,350]

  联立要求 V_cache 从 rod10→11 的增长率 > ef_park 的增长率，
  这样 r 才能从 ≈1 跌破 0.99。星空图把 V_cache[10]/[11] 顶高，
  改变了增长率结构，使 r@11 无法被压到 0.99 以下 → 无解。
""")
