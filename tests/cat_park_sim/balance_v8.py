"""
猫猫乐园 v8 — 扁平价格表 + 完整方案求解
核心：乐园鱼稀有度价格表扁平化，让 ef/V 随rod下降，实现自然衰减
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
SCENE_MULT = 1 + PARK_DIFF * 0.3  # 2.8
FISH_MULT_AVG = 1.45


def make_ef_func(rbase):
    """用指定价格表生成乐园鱼期望函数"""

    def ef(rod):
        d = max(0, min(rod - PARK_DIFF, len(RARITY_DISTRIBUTION) - 1))
        probs = RARITY_DISTRIBUTION[d]
        total = 0.0
        for i in range(min(len(_RARITY_KEYS), len(probs))):
            total += probs[i] * rbase[_RARITY_KEYS[i]] * SCENE_MULT * FISH_MULT_AVG
        if len(probs) > len(_RARITY_KEYS):
            total += (
                sum(probs[len(_RARITY_KEYS) :])
                * rbase["UTR"]
                * SCENE_MULT
                * FISH_MULT_AVG
            )
        return total

    return ef


# 速度
def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    base = 60
    return base / (
        (1 + hook * 0.1)
        * (
            1
            + (bait_bonus + min(nest_layers, 10) * 5 + min(frame_layers, 10) * 5) / 100
        )
    )


interval7 = calc_interval(7, 120, 10, 10)
casts_24h = int(24 * 60 / interval7)

# 建造材料
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
total_mats = {}
for bld, levels in BUILDING_COSTS.items():
    for lv, cost in levels.items():
        for mat, qty in cost.items():
            total_mats[mat] = total_mats.get(mat, 0) + qty
TOTAL_NEEDED = sum(total_mats.values())

print("=" * 80)
print("  猫猫乐园 v8 — 扁平价格表完整方案")
print("=" * 80)
print(f"  速度：{interval7:.1f}分钟/竿 → {casts_24h}竿/天(24h)")
print(f"  建造：{TOTAL_NEEDED}个材料")

# ═══ 测试多个扁平价格表 ═══
candidate_tables = {
    "扁平A(15/25/40/70/110/160)": {
        "N": 15,
        "R": 25,
        "SR": 40,
        "SSR": 70,
        "UR": 110,
        "UTR": 160,
    },
    "扁平B(20/30/45/70/100/140)": {
        "N": 20,
        "R": 30,
        "SR": 45,
        "SSR": 70,
        "UR": 100,
        "UTR": 140,
    },
    "高N低UTR(30/40/55/80/110/140)": {
        "N": 30,
        "R": 40,
        "SR": 55,
        "SSR": 80,
        "UR": 110,
        "UTR": 140,
    },
    "极扁(25/35/45/60/75/95)": {
        "N": 25,
        "R": 35,
        "SR": 45,
        "SSR": 60,
        "UR": 75,
        "UTR": 95,
    },
}

for tname, rbase in candidate_tables.items():
    ef = make_ef_func(rbase)
    print(f"\n{'=' * 80}")
    print(f"  价格表：{tname}")
    print(f"{'=' * 80}")

    # 用此价格表，m=18%，扫描D，约束 ratio(10)=1.0
    m = 0.18
    ef10 = ef(10)

    print("\n  m=18%, 扫描D（ratio(10)=1.0 反解P）：")
    print(
        f"  {'D':>5} {'P':>7} {'r@8':>6} {'r@9':>6} {'r@10':>6} {'r@11':>6} {'r@12':>6} {'r@13':>6} {'r@14':>6}"
    )
    print("  " + "-" * 65)

    best_row = None
    for D_x100 in range(20, 101, 5):
        D = D_x100 / 100
        fish10 = (1 - m) * D * ef10
        mP = V_cache[10] - fish10
        if mP < 0:
            continue
        P = mP / m
        if P > 5000:
            continue

        ratios = {}
        for rod in range(7, 15):
            ratios[rod] = (m * P + (1 - m) * D * ef(rod)) / V_cache[rod]

        r8, r9, r10, r11, r12, r13, r14 = (ratios[r] * 100 for r in range(8, 15))
        ok = r9 > 100 and abs(r10 - 100) < 2 and r11 < 100
        mark = "★" if ok else ""
        print(
            f"  {D:>5.2f} {P:>7.0f} {r8:>5.0f}% {r9:>5.0f}% {r10:>5.0f}% {r11:>5.0f}% {r12:>5.0f}% {r13:>5.0f}% {r14:>5.0f}% {mark}"
        )
        if ok and (best_row is None or r11 < best_row[4]):
            best_row = (D, P, r8, r9, r10, r11, r12, r13, r14)

    if best_row:
        D, P = best_row[0], best_row[1]
        print(f"\n  ★ 最优：D={D:.2f}, P={P:.0f}")
        print("  完整衰减曲线：")
        for rod in range(7, 16):
            income = m * P + (1 - m) * D * ef(rod)
            r = income / V_cache[rod]
            ev = "赚" if r > 1.02 else ("平" if r > 0.98 else "亏")
            print(
                f"    rod={rod:>2}  收益{income:>7.1f}  V={V_cache[rod]:>7.1f}  {r * 100:>5.0f}%  {ev}"
            )
        mats_day = casts_24h * m
        print(f"  建设：{mats_day:.0f}材料/天 → {TOTAL_NEEDED / mats_day:.0f}天")

# ═══ 最推荐方案详细展开 ═══
print(f"\n{'=' * 80}")
print("  ★★ 最终推荐方案 ★★")
print(f"{'=' * 80}")

rbase = {"N": 20, "R": 30, "SR": 45, "SSR": 70, "UR": 100, "UTR": 140}  # 扁平B
ef = make_ef_func(rbase)
m, D = 0.18, 0.40
ef10 = ef(10)
fish10 = (1 - m) * D * ef10
P = (V_cache[10] - fish10) / m

print("\n  价格表：N=20 R=30 SR=45 SSR=70 UR=100 UTR=140")
print(f"  材料率：{m * 100:.0f}%")
print(f"  鱼价折扣：{D:.2f}（无折扣，直接用基础价×场景系数）")
print(f"  材料均价：{P:.0f} 金币/个")
print(f"  建设周期：{TOTAL_NEEDED / (casts_24h * m):.0f} 天")

print("\n  【衰减曲线】")
print(f"  {'rod':>4} {'乐园收益':>10} {'V(rod)':>10} {'比例':>8} {'评估':>6}")
print("  " + "-" * 45)
for rod in range(7, 16):
    income = m * P + (1 - m) * D * ef(rod)
    r = income / V_cache[rod]
    ev = "赚" if r > 1.02 else ("平" if r > 0.98 else "亏")
    print(f"  {rod:>4} {income:>10.1f} {V_cache[rod]:>10.1f} {r * 100:>7.0f}% {ev:>6}")

# 材料价格
print(f"\n  【材料价格分配（均价{P:.0f}）】")
weights = {
    "猫抓板木板": 20,
    "毛线团": 20,
    "小铃铛": 20,
    "特级小鱼干": 20,
    "水晶猫砂": 18,
    "彩虹逗猫棒": 12,
}
total_w = sum(weights.values())
common = P * 0.6
rare = P * 2.8
wavg = (common * 80 + rare * 30) / total_w
adj = P / wavg
common *= adj
rare *= adj
for mat, w in sorted(weights.items(), key=lambda x: -x[1]):
    p = common if w >= 18 else rare
    print(f"    {mat:<12} {p:>6.0f}金币/个")

# 单条鱼实际价格示例
print(f"\n  【单条鱼实际售价示例（D={D}，场景系数×{SCENE_MULT}）】")
for rarity in ["N", "R", "SR", "SSR", "UR", "UTR"]:
    price = rbase[rarity] * D * SCENE_MULT * FISH_MULT_AVG
    print(f"    {rarity:>4}: {price:>6.0f} 金币")
