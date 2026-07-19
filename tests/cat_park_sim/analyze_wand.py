"""
旋转逗猫棒灵敏度分析（相对边际法，不依赖绝对可行性）
核心：旋转逗猫棒是 DAILY_MULT 中的独立乘区，其对乐园收入的贡献 = (1+双倍率)。
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
PARK_DIFF = 6
diff6_locs = [loc for loc in LOCATIONS if loc["difficulty"] == 6]
park_avg = sum(LOC_AVG[l["id"]] for l in diff6_locs) / len(diff6_locs)

# 乐园在 rod=10、无 DAILY_MULT 时的单次期望（castle 混合）
CASTLE_PROB = 0.30


def ef_raw(rod):
    d = max(0, rod - PARK_DIFF)
    return park_avg * calc_M_UR(d)


def ef_castle(rod):
    return (1 - CASTLE_PROB) * ef_raw(rod) + CASTLE_PROB * ef_raw(rod + 1)


ef_castle_10 = ef_castle(10)

# DAILY_MULT 的其它 4 个 Lv3 因子（不随旋转逗猫棒变化）
BASE_MULT = 1.10 * 1.04 * 1.10 * 1.01  # 鱼价 × 天气 × 鱼塘速度 × 饵节省

print("=" * 90)
print("  旋转逗猫棒 — 边际贡献分析")
print("=" * 90)

print(f"\n  乐园 rod10 单次基础期望 ef_castle(10) = {ef_castle_10:.2f}")
print(f"  其它四建筑 Lv3 乘区 BASE_MULT = {BASE_MULT:.4f}")
print(f"  DAILY_MULT = BASE_MULT × (1 + 双倍率)\n")

# 各档对比
print(f"  {'档位':<18}{'双倍率':>6}{'DAILY_MULT':>12}"
      f"{'乐园日收入*':>14}{'相对当前':>10}")
print("  " + "-" * 70)

cur_dm = BASE_MULT * 1.05
cases = [
    ("移除该建筑", 0.00),
    ("当前 Lv1", 0.01),
    ("改成 3%", 0.03),
    ("当前 Lv3(模拟值)", 0.05),
    ("设计文档 Lv2", 0.06),
    ("设计文档 Lv3", 0.10),
]
for label, rate in cases:
    dm = BASE_MULT * (1 + rate)
    daily = ef_castle_10 * dm  # D=1
    rel = dm / cur_dm
    marker = "  ← 模拟所用" if rate == 0.05 else ""
    print(f"  {label:<18}{rate*100:>5.0f}%{dm:>12.4f}{daily:>14.2f}{rel:>9.2%}{marker}")

print(f"\n  * 乐园日收入 = ef_castle(10) × DAILY_MULT × D(=1) × 24h抂数，此处仅展示乘区乘积")

# 同级建筑横向对比（Lv3 对乐园收入的乘区贡献）
print(f"\n{'='*90}")
print("  同级建筑横向对比（Lv3 各自对乐园收入的乘区贡献）")
print(f"{'='*90}\n")
siblings = [
    ("喵咖咖啡馆", "鱼价", 1.10),
    ("喵喵鱼塘", "钓鱼速度", 1.10),
    ("猫猫过山车", "天气增幅(折算)", 1.04),
    ("猫猫小木屋", "饵节省(折算)", 1.01),
    ("旋转逗猫棒", "双倍鱼获", 1.05),
]
print(f"  {'建筑':<12}{'效果':<16}{'Lv3乘区':>10}{'相对最强':>10}")
print("  " + "-" * 50)
top = max(s[2] for s in siblings)
for name, eff, factor in siblings:
    print(f"  {name:<12}{eff:<16}{factor:>9.2f}x{factor/top:>9.1%}")

print(f"\n  → 旋转逗猫棒 Lv3=×1.05，约为最强建筑(×1.10)的 95%，并非最弱。")
print(f"     最弱是 猫猫小木屋(饵节省折算 ×1.01)。")

# 关键结论：双倍率对 DAILY_MULT 的弹性
print(f"\n{'='*90}")
print("  关键结论")
print(f"{'='*90}")
print(f"""
  1) 模拟用值：balance_v20 的 DAILY_MULT 中，旋转逗猫棒 = "双倍1.05"，
     即 Lv3=5%（对应 cat_park.py 中 double_rate=[0,0.01,0.03,0.05]）。
     用户看到的 "1%" 只是 Lv1 档，模拟用的是满级 Lv3=5%。

  2) 数值异常：cat_park.py 中旋转逗猫棒 = 1%/3%/5%，
     而①同级其它百分比建筑(鱼价/速度/天气/饵节省)统一是 3%/6%/10%；
       ②GAME_DESIGN.md 原设计也是 3%/6%/10%。
     → 该建筑在代码里被整体"腰斩"了，约为应有的强度的一半。
     → 这才是它"显得垃圾"的根因：不是机制差，是数值被砍了。

  3) 弹性：双倍率每 +1pp，DAILY_MULT 提升 {BASE_MULT*0.01:.4f}（约 +1%）。
     从当前 Lv3=5% 提到设计文档 Lv3=10%，乐园收入 ×{BASE_MULT*1.10/BASE_MULT/1.05:.4f}（+4.76%）。
     但乐园仅占总收入的 (1-m) 成，对总收入影响进一步被稀释。

  4) 若只是把 Lv1 从 1%→3%（对齐同级），不影响模拟（模拟用 Lv3），
     只影响前期单建筑体验，属于合理的数值对齐修复。
""")
