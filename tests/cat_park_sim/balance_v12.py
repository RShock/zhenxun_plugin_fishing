"""
猫猫乐园 v12 — 用户的思路：D=1.0（鱼价=主世界），拉高材料率
理论：材料率越高，乐园收益中"固定材料"占比越大，
      rod升高时主世界V增长，固定材料被稀释 → 自然衰减
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


# UR封顶的 M(d)
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
        if loc["difficulty"] > rod:
            continue
        exp = LOC_AVG[loc["id"]] * calc_M_UR(rod - loc["difficulty"])
        if exp > best:
            best = exp
    return best


V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)


def ef_park(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


ef10 = ef_park(10)

print("=" * 80)
print("  猫猫乐园 v12 — D=1.0，拉高材料率")
print("=" * 80)
print("  鱼价折扣 D = 1.0（鱼价=主世界原价，不打折）")
print("  约束：ratio(10)=1.0 → P = [V(10) - (1-m)×ef(10)] / m")
print(f"\n  V(10)={V_cache[10]:.1f}, ef(10)={ef10:.1f}")

print(
    f"\n  {'m':>6} {'P':>8} {'r@7':>7} {'r@8':>7} {'r@9':>7} {'r@10':>7} {'r@11':>7} {'r@12':>7} {'r@13':>7} {'r@14':>7} {'r@15':>7}"
)
print("  " + "-" * 85)

for m_pct in range(10, 91, 5):
    m = m_pct / 100
    # ratio(10)=1.0
    mP = V_cache[10] - (1 - m) * ef10
    if mP < 0:
        print(f"  {m * 100:>5.0f}%  无解（鱼价超标）")
        continue
    P = mP / m

    ratios = {}
    for rod in range(7, 16):
        income = m * P + (1 - m) * ef_park(rod)
        ratios[rod] = income / V_cache[rod]

    rstr = " ".join(f"{ratios[r] * 100:>6.0f}%" for r in range(7, 16))
    # 标记
    ok = ratios[9] > 1.0 and abs(ratios[10] - 1.0) < 0.02 and ratios[11] < 0.95
    mark = " ★" if ok else ""
    print(f"  {m * 100:>5.0f}% {P:>8.0f} {rstr}{mark}")

print("""
  ┌─────────────────────────────────────────────────────────────┐
  │  结论验证                                                    │
  │                                                             │
  │  材料率越高，衰减越陡 — 这正是用户的思路！                   │
  │                                                             │
  │  原因：m高时，乐园收益 ≈ m×P（固定），不随rod增长           │
  │        而V(rod)随rod增长 → ratio必然单调下降                │
  │                                                             │
  │  例：m=70%                                                  │
  │    乐园收益 ≈ 0.7×P + 0.3×ef(rod)                           │
  │    P不变，ef(rod)变化不大 → 乐园收益几乎恒定                 │
  │    但V(rod)从90→700+ → ratio从200%+降到20%                  │
  └─────────────────────────────────────────────────────────────┘
""")

# ═══ 最佳方案详细展示 ═══
print(f"{'=' * 80}")
print("  几个代表性方案详细展示")
print(f"{'=' * 80}")

for m_target in [0.40, 0.50, 0.60, 0.70, 0.80]:
    m = m_target
    mP = V_cache[10] - (1 - m) * ef10
    P = mP / m

    # 建设速度
    def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
        return 60 / (
            (1 + hook * 0.1)
            * (
                1
                + (bait_bonus + min(nest_layers, 10) * 5 + min(frame_layers, 10) * 5)
                / 100
            )
        )

    interval7 = calc_interval(7, 120, 10, 10)
    casts_24h = int(24 * 60 / interval7)
    mats_day = casts_24h * m

    print(f"\n  ── m={m * 100:.0f}%, D=1.0, P={P:.0f}, 材料{mats_day:.0f}个/天 ──")
    print(f"  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
    print("  " + "-" * 45)
    for rod in range(7, 16):
        income = m * P + (1 - m) * ef_park(rod)
        r = income / V_cache[rod]
        ev = "赚" if r > 1.05 else ("平" if r > 0.95 else ("小亏" if r > 0.8 else "亏"))
        print(
            f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}"
        )
