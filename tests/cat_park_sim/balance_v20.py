"""
猫猫乐园平衡分析 — 满级(全Lv3)单一场景
模型：所有建筑 Lv3 满级（游戏实际配置），对比"纯乐园日收益"vs"纯普通图日收益"。
- 普通图基准 V(rod)：仅 1-10 图（排除 S1 乐园自身、11-20 星空图门控）
- 乐园收益 ef_park_daily(rod)：基于 S1 鱼池 + 满级 DAILY_MULT
- r@rod = ef_park_daily(rod) / V(rod)
  - r≥1 → 该等级玩家留乐园不亏
  - r<1 → 该等级玩家去普通图更优
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
    ALL_LOCS = json.load(f)["locations"]

# 普通图基准：仅 1-10 图（排除 S1 乐园自身、11-20 星空图）
NORMAL_LOCS = [l for l in ALL_LOCS if l["id"] in {str(i) for i in range(1, 11)}]
PARK = next(l for l in ALL_LOCS if l["id"] == "S1")


def calc_M_UR(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = sum(probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]] for i in range(4))
    m += sum(probs[4:]) * RARITY_MULTIPLIER["UR"]
    return m


def loc_avg_base(loc):
    prices = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(prices) / len(prices) if prices else 0


def V_normal(rod):
    """普通图最优日单次期望 + 来源地点"""
    best, best_loc = 0, None
    for loc in NORMAL_LOCS:
        if loc["difficulty"] > rod:
            continue
        exp = loc_avg_base(loc) * calc_M_UR(rod - loc["difficulty"])
        if exp > best:
            best, best_loc = exp, loc
    return best, best_loc


# 乐园参数
PARK_DIFF = PARK["difficulty"]  # 6
park_avg = loc_avg_base(PARK)
CASTLE_PROB = 0.30  # 水晶猫城堡 30% 概率 rod+1

# 满级 DAILY_MULT（5 因子，全部 Lv3）
# 鱼价1.10 × 双倍1.10 × 天气1.04 × 鱼塘速度1.10 × 饵节省1.01
# 旋转逗猫棒 Lv3 双倍率 10%（与 cat_park.py 及同级百分比建筑 3%/6%/10% 对齐）
DAILY_MULT = 1.10 * 1.10 * 1.04 * 1.10 * 1.01  # = 1.399


def ef_raw(rod):
    return park_avg * calc_M_UR(max(0, rod - PARK_DIFF))


def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)


def ef_park_daily(rod):
    return ef_castle(rod) * DAILY_MULT


# 24h 抛竿次数：同速口径（100鱼饵 + 100 Buff；Buff=满打窝50+满展示框50）
def calc_interval(hook, bait_bonus, nest_layers, frame_layers):
    return 60 / ((1 + hook * 0.1) * (1 + (bait_bonus + min(nest_layers, 10) * 5 + min(frame_layers, 10) * 5) / 100))


interval7 = calc_interval(7, 100, 10, 10)
casts_24h = int(24 * 60 / interval7)
MATERIAL_RATE_LV3 = 0.45  # 猫爬架广场 Lv3

# ═══ 输出 ═══
print("=" * 88)
print("  猫猫乐园平衡分析 — 满级(全Lv3)单一场景")
print("=" * 88)
print(f"\n  满级 DAILY_MULT = {DAILY_MULT:.4f}")
print(f"    (鱼价1.10 × 双倍1.10 × 天气1.04 × 鱼塘速度1.10 × 饵节省1.01)")
print(f"  乐园 fish_pool 均价 park_avg = {park_avg:.2f}")
print(f"  水晶猫城堡 rod+1 概率 = {CASTLE_PROB:.0%}")
print(f"  7级鱼钩满buff下 24h 抛竿 = {casts_24h} 次")

print(f"\n  {'rod':>4} {'乐园日收益':>10} {'普通图V(rod)':>12} {'来源':>10} "
      f"{'r=乐园/普通':>12} {'评估':>8}")
print("  " + "-" * 72)
for rod in range(7, 16):
    ef = ef_park_daily(rod)
    vn, vloc = V_normal(rod)
    r = ef / vn if vn else 0
    if r > 1.02:
        ev = "乐园优"
    elif r < 0.98:
        ev = "普通图优"
    else:
        ev = "持平"
    loc_name = vloc["name"] if vloc else "-"
    print(f"  {rod:>4} {ef:>10.1f} {vn:>12.1f} {loc_name:>10} {r*100:>11.0f}% {ev:>8}")

# 平衡判据
print(f"\n{'='*88}")
print("  平衡判据")
print(f"{'='*88}")
r10 = ef_park_daily(10) / V_normal(10)[0]
r11 = ef_park_daily(11) / V_normal(11)[0]
print(f"\n  r@10 = {r10*100:.0f}%  (10级是1阶段满级锚点)")
print(f"  r@11 = {r11*100:.0f}%  (11级若无星空艇，玩家只能留乐园或回10图)")
if r10 >= 1.0:
    print(f"  → 乐园在 1 阶段满级(r10)前不亏，留住玩家挂机产材料。")
if r11 < 1.0:
    print(f"  → rod≥11 乐园收益回落，为二阶段(星空图)留出收益空间。")

# 材料产出
print(f"\n{'='*88}")
print("  满级乐园材料产出（玩家全留乐园时）")
print(f"{'='*88}")
mats_day = casts_24h * MATERIAL_RATE_LV3
print(f"\n  24h 抛竿 {casts_24h} 次 × 材料率 {MATERIAL_RATE_LV3:.0%} = {mats_day:.0f} 个材料/天")
