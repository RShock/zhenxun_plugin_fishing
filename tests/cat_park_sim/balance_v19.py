"""
猫猫乐园 v19 — 鱼价更高(D↑)，材料价更低(P↓)，r@11≤99%即可
约束放宽：
- r@9 ≥ 100%（9级赚一点）
- r@10 ≈ 100%
- r@11 ≤ 99%（只要更低就行，不要求大幅亏）
- r@7~8 不要太高（控制在120%以内更好）
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

# buff（全Lv3）
CASTLE_PROB = 0.30
PRICE_MULT = 1.10
DOUBLE_MULT = 1.05
WEATHER_BOOST = 1.04
SPEED_MULT = 1.10
BAIT_SAVE = 1.01
DAILY_MULT = PRICE_MULT * DOUBLE_MULT * WEATHER_BOOST * SPEED_MULT * BAIT_SAVE

def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)

def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)

def ef_park_daily(rod, D=1.0):
    return ef_castle(rod) * D * DAILY_MULT

ef_d10 = ef_park_daily(10, 1.0)

def solve_m(D, P):
    """ratio(10)=1.0求m"""
    num = V_cache[10] - D * ef_d10
    den = P - D * ef_d10
    if abs(den) < 0.001:
        return None
    m = num / den
    return m

def calc_ratios(m, D, P):
    ratios = {}
    for rod in range(7, 16):
        income = m*P + (1-m)*D*ef_park_daily(rod, 1.0)
        ratios[rod] = income / V_cache[rod]
    return ratios

# ═══ 扫描 ═══
print("=" * 95)
print("  猫猫乐园 v19 — D尽量高, P尽量低, r@11≤99%即可")
print("=" * 95)

def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    return 60 / ((1 + hook*0.1) * (1 + (bait_bonus + min(nest_layers,10)*5 + min(frame_layers,10)*5)/100))
interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

# 目标：D尽量高，P尽量低
# 约束：r@9≥100, r@10=100, r@11≤99, r@7≤125, r@8≤115
best_solutions = []

for P_target in range(50, 301, 10):
    for D_x100 in range(80, 100, 1):
        D = D_x100 / 100
        m = solve_m(D, P_target)
        if m is None or m < 0.01 or m > 0.95:
            continue
        ratios = calc_ratios(m, D, P_target)
        
        # 放宽约束
        ok = (ratios[9] >= 1.00 and          # 9级赚
              abs(ratios[10] - 1.0) < 0.02 and # 10级平
              ratios[11] <= 0.99 and           # 11级亏（≤99%即可）
              ratios[7] <= 1.30 and            # 7级别太高
              ratios[8] <= 1.20)               # 8级别太高
        if ok:
            best_solutions.append((D, P_target, m, ratios))

# 按D降序、P升序排序
best_solutions.sort(key=lambda x: (-x[0], x[1]))

print(f"\n  共找到 {len(best_solutions)} 个可行解")
print(f"\n  {'D':>5} {'P':>5} {'m':>5} {'r@7':>6} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6} {'r@15':>6}")
print("  " + "-" * 85)

# 去重：相同D取P最小的
seen_DP = set()
count = 0
for D, P, m, ratios in best_solutions:
    key = (round(D, 2), P)
    if key in seen_DP:
        continue
    seen_DP.add(key)
    rstr = " ".join(f"{ratios[r]*100:>5.0f}%" for r in range(7, 16))
    mats_day = casts_24h * m
    print(f"  {D:>5.2f} {P:>5} {m*100:>4.0f}% {rstr}  ({mats_day:>3.0f}个/天)")
    count += 1
    if count >= 30:
        break

# ═══ 精选方案 ═══
print(f"\n{'='*95}")
print(f"  精选方案详情（D尽量高，P尽量低）")
print(f"{'='*95}")

# 选3个代表性方案
picks = []
for P_target in [100, 150, 200]:
    candidates = [s for s in best_solutions if s[1] == P_target]
    if candidates:
        # D最高的
        best = max(candidates, key=lambda x: x[0])
        picks.append(best)

for D, P, m, ratios in picks:
    mats_day = casts_24h * m
    print(f"\n  ── D={D:.2f}, P={P}, m={m*100:.0f}%, 材料{mats_day:.0f}个/天 ──")
    print(f"  {'rod':>4} {'乐园每天':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m*P + (1-m)*D*ef_park_daily(rod, 1.0)
        r = income / V_cache[rod]
        ev = "赚" if r>1.02 else ("平" if r>0.98 else "亏")
        print(f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r*100:>7.0f}% {ev:>6}")
