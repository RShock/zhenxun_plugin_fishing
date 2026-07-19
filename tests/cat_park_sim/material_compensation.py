"""
猫猫乐园鱼价下调后的材料价格补偿分析
目标：后5条鱼砍到6级均价52后，计算材料单价补偿到多少较合理。
口径：与同difficulty=6图（长江中游）比较；材料按每次材料掉落产出1个，独立卖价补偿。
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
    LOCS = json.load(f)["locations"]

NORMAL6 = next(l for l in LOCS if l["id"] == "7")
PARK = next(l for l in LOCS if l["id"] == "S1")


def calc_M_UR(d):
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = sum(probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]] for i in range(4))
    m += sum(probs[4:]) * RARITY_MULTIPLIER["UR"]
    return m


def avg(loc):
    return sum(FISH[fid] for fid in loc["fish_pool"] if fid in FISH) / len(loc["fish_pool"])


normal_avg = avg(NORMAL6)
park_avg = avg(PARK)
old_park_avg = 60.0

# 满级建筑
MATERIAL_RATE = 0.45
FISH_RATE = 1 - MATERIAL_RATE
DAILY_MULT = 1.10 * 1.10 * 1.04 * 1.10 * 1.01
CASTLE_PROB = 0.30


def castle_m(rod, diff=6):
    return (1 - CASTLE_PROB) * calc_M_UR(rod - diff) + CASTLE_PROB * calc_M_UR(rod + 1 - diff)


def park_fish_income(avg_price, rod):
    return FISH_RATE * avg_price * castle_m(rod) * DAILY_MULT


def normal_income(rod):
    return normal_avg * calc_M_UR(rod - 6)


def break_even_material_price(rod, target_ratio=1.0):
    target = normal_income(rod) * target_ratio
    fish_part = park_fish_income(park_avg, rod)
    # 材料掉落发生时不钓鱼，但每次材料给 material_price 金币；材料也吃满级通用乘区中的速度，不吃鱼价/稀有度。
    # 这里按“每次抛竿期望”补偿：MATERIAL_RATE * price = 缺口
    return max(0, (target - fish_part) / MATERIAL_RATE)


print("=" * 90)
print("  鱼价下调后：材料价格补偿分析")
print("=" * 90)
print(f"\n  6级普通图(长江中游)均价 = {normal_avg:.1f}")
print(f"  乐园旧均价 = {old_park_avg:.1f}")
print(f"  乐园新均价 = {park_avg:.1f}")
print(f"  乐园均价变化 = {old_park_avg:.1f} → {park_avg:.1f} ({park_avg/old_park_avg*100:.1f}%)")
print(f"  材料率 = {MATERIAL_RATE:.0%}，鱼获率 = {FISH_RATE:.0%}")

print(f"\n  {'rod':>4} {'普通6级收益':>12} {'乐园鱼币(材料0)':>16} {'比例':>8} {'补到100%材料价':>16} {'补到105%材料价':>16}")
print("  " + "-" * 84)
for rod in [9, 10, 11]:
    n = normal_income(rod)
    p0 = park_fish_income(park_avg, rod)
    be100 = break_even_material_price(rod, 1.00)
    be105 = break_even_material_price(rod, 1.05)
    print(f"  {rod:>4} {n:>12.1f} {p0:>16.1f} {p0/n*100:>7.0f}% {be100:>15.1f} {be105:>15.1f}")

print(f"\n{'='*90}")
print("  建议")
print(f"{'='*90}")
prices = [0, 20, 40, 60, 80, 100, 115]
print(f"\n  材料价格敏感性（乐园总收益 / 普通6级收益）：")
print(f"  {'材料价':>6} {'rod9':>8} {'rod10':>8} {'rod11':>8}")
print("  " + "-" * 36)
for price in prices:
    vals = []
    for rod in [9, 10, 11]:
        total = park_fish_income(park_avg, rod) + MATERIAL_RATE * price
        vals.append(total / normal_income(rod) * 100)
    print(f"  {price:>6} {vals[0]:>7.0f}% {vals[1]:>7.0f}% {vals[2]:>7.0f}%")

print("""
  结论：
  - 砍价后，材料=0 时乐园约为同级6图的 84%~86%，金币明显亏，换材料进度。
  - 若希望乐园金币基本不亏，需要材料单价约 42~80：
      rod9 需要约42，rod10约65，rod11约80。
  - 当前采用材料卖价 80：rod11 正好持平，rod9/10 略赚；适合作为竣工后的剩余材料回收价。
  - 不建议沿用 115：会让乐园金币收益达到 107%~125%，重新偏强。
""")
