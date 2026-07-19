"""
猫猫乐园 v7 — 展示 D(鱼价折扣) 对衰减陡度的影响
固定 m=18%（约18天建设），展示不同 D 值的完整曲线
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


V_cache = {rod: V_normal(rod) for rod in range(1, 20)}

PARK_DIFF = 6
RARITY_BASE = {"N": 8, "R": 22, "SR": 55, "SSR": 120, "UR": 220, "UTR": 400}
SCENE_MULT = 1 + PARK_DIFF * 0.3
FISH_MULT_AVG = 1.45


def E_fish_park_raw(rod):
    d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    total = 0.0
    for i in range(min(len(_RARITY_KEYS), len(probs))):
        total += probs[i] * RARITY_BASE[_RARITY_KEYS[i]] * SCENE_MULT * FISH_MULT_AVG
    if len(probs) > len(_RARITY_KEYS):
        total += (
            sum(probs[len(_RARITY_KEYS) :])
            * RARITY_BASE["UTR"]
            * SCENE_MULT
            * FISH_MULT_AVG
        )
    return total


ef10 = E_fish_park_raw(10)

print("=" * 80)
print("  D值对衰减陡度的影响（固定 m=18%，约18天建设）")
print("=" * 80)
print("  约束：ratio(10)=1.0 → 对每个D反解P")
print()

m = 0.18

print(
    f"  {'D':>5} {'P':>7} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6} {'r9-r11':>7} {'判定':>8}"
)
print("  " + "-" * 80)

for D_x100 in range(10, 105, 5):
    D = D_x100 / 100
    fish_part_10 = (1 - m) * D * ef10
    mP = V_cache[10] - fish_part_10
    if mP < 0:
        print(f"  {D:>5.2f}  P<0 (鱼价过高，材料无法补足)")
        continue
    P = mP / m

    ratios = {}
    for rod in range(7, 15):
        ratios[rod] = (m * P + (1 - m) * D * E_fish_park_raw(rod)) / V_cache[rod]

    r8, r9, r10, r11, r12, r13, r14 = (ratios[r] * 100 for r in range(8, 15))
    spread = r9 - r11
    ok = r9 > 100 and abs(r10 - 100) < 2 and r11 < 100
    flag = "✓满足" if ok else "不满足"
    print(
        f"  {D:>5.2f} {P:>7.0f} {r8:>5.0f}% {r9:>5.0f}% {r10:>5.0f}% {r11:>5.0f}% {r12:>5.0f}% {r13:>5.0f}% {r14:>5.0f}% {spread:>6.0f}pp {flag:>8}"
    )

print("""
  解读：
  - D=0.10: 鱼价1折，材料价≈1013，r@11=81%（陡，但鱼几乎是垃圾）
  - D=0.30: 鱼价3折，材料价≈771， r@11=81%
  - D=0.50: 鱼价5折，材料价≈529， r@11=82%
  - D=0.70: 鱼价7折(原设计)，材料价≈287，r@11=82%
  - D≥0.80: 鱼价太高，rod=9已经不能>100%

  关键发现：r@11 始终≈80-82%，对D不敏感！
  因为 ratio(rod)=[mP+(1-m)D×ef(rod)]/V(rod)，
  当 ratio(10)被锁定=1.0 时，r@11 由 ef(11)/V(11) 的固有形状决定，
  约束体系已经把它压到~81%，无法更陡（除非降低乐园鱼基础价表）
""")

# ═══ 验证：乐园鱼基础价表的影响 ═══
print(f"{'=' * 80}")
print("  实验：降低乐园鱼基础价表，能否让rod=11更陡？")
print(f"{'=' * 80}")

# 原表: N=8 R=22 SR=55 SSR=120 UR=220 UTR=400
# 试: 把高稀有度价格压低（UTR相对便宜），改变ef(rod)形状
print("\n  不同基础价表下 ef(rod)/V(rod) 的形状：")

tables = {
    "原表(8/22/55/120/220/400)": {
        "N": 8,
        "R": 22,
        "SR": 55,
        "SSR": 120,
        "UR": 220,
        "UTR": 400,
    },
    "扁平(15/25/40/70/110/160)": {
        "N": 15,
        "R": 25,
        "SR": 40,
        "SSR": 70,
        "UR": 110,
        "UTR": 160,
    },
    "高N低UTR(30/40/55/80/110/140)": {
        "N": 30,
        "R": 40,
        "SR": 55,
        "SSR": 80,
        "UR": 110,
        "UTR": 140,
    },
}

for tname, rbase in tables.items():
    print(f"\n  [{tname}]")

    def ef_custom(rod):
        d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
        probs = RARITY_DISTRIBUTION[d]
        total = 0.0
        for i in range(min(len(_RARITY_KEYS), len(probs))):
            total += probs[i] * rbase[_RARITY_KEYS[i]] * FISH_MULT_AVG
        if len(probs) > len(_RARITY_KEYS):
            total += sum(probs[len(_RARITY_KEYS) :]) * rbase["UTR"] * FISH_MULT_AVG
        return total

    print(f"    {'rod':>4} {'ef':>8} {'V':>8} {'ef/V':>7}")
    for rod in range(7, 14):
        ef = ef_custom(rod)
        v = V_cache[rod]
        print(f"    {rod:>4} {ef:>8.0f} {v:>8.0f} {ef / v * 100:>6.0f}%")
    # ef/V 是升是降？
    r7 = ef_custom(7) / V_cache[7]
    r13 = ef_custom(13) / V_cache[13]
    trend = "上升↑" if r13 > r7 else "下降↓"
    print(f"    ef/V: rod7={r7 * 100:.0f}% → rod13={r13 * 100:.0f}% {trend}")
