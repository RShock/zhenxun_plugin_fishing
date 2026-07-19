"""
乐园 vs 普通图 收益因式分解（仅 rod 9/10/11）
逐层拆解：为什么乐园均价只高 15%，最终领先却达 50~70%？
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

NORMAL_LOCS = [l for l in ALL_LOCS if l["id"] in {str(i) for i in range(1, 11)}]
PARK = next(l for l in ALL_LOCS if l["id"] == "S1")
PARK_DIFF = 6


def calc_M_UR(d):
    """d = rod - difficulty，返回期望倍率（按 UR 封顶）"""
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    m = sum(probs[i] * RARITY_MULTIPLIER[_RARITY_KEYS[i]] for i in range(4))
    m += sum(probs[4:]) * RARITY_MULTIPLIER["UR"]   # UR 及以上统一按 UR
    return m


def loc_avg(loc):
    ps = [FISH[fid] for fid in loc["fish_pool"] if fid in FISH]
    return sum(ps) / len(ps) if ps else 0


def best_normal(rod):
    """普通图最优单次期望 + 来源"""
    best, best_loc = 0, None
    for loc in NORMAL_LOCS:
        if loc["difficulty"] > rod:
            continue
        exp = loc_avg(loc) * calc_M_UR(rod - loc["difficulty"])
        if exp > best:
            best, best_loc = exp, loc
    return best, best_loc


# 乐园核心机制
CASTLE_PROB = 0.30
DAILY_MULT = 1.10 * 1.10 * 1.04 * 1.10 * 1.01  # = 1.399（满级全Lv3）
park_avg = loc_avg(PARK)


def ef_park(rod):
    """乐园单次期望（含城堡 rod+1、满级 DAILY_MULT）"""
    raw = park_avg * calc_M_UR(max(0, rod - PARK_DIFF))
    raw_next = park_avg * calc_M_UR(max(0, rod + 1 - PARK_DIFF))
    castle_mix = (1 - CASTLE_PROB) * raw + CASTLE_PROB * raw_next
    return castle_mix * DAILY_MULT


print("=" * 92)
print("  乐园 vs 普通图 — 收益因式分解（rod 9/10/11）")
print("=" * 92)
print(f"\n  满级 DAILY_MULT = {DAILY_MULT:.4f}  (鱼价1.10 × 双倍1.10 × 天气1.04 × 速度1.10 × 饵节省1.01)")
print(f"  城堡 rod+1 概率 = {CASTLE_PROB:.0%}    乐园均价 = {park_avg:.1f}    乐园 difficulty = {PARK_DIFF}\n")

print(f"  {'项':<32}{'rod=9':>14}{'rod=10':>14}{'rod=11':>14}")
print("  " + "-" * 74)

# === A. 基础鱼价 × 概率期望 ===
print("\n  【A】如果乐园只是『一张普通6级图』（无任何乐园机制）")
for rod in [9, 10, 11]:
    d_park = max(0, rod - PARK_DIFF)
    m_park = calc_M_UR(d_park)
    raw_park = park_avg * m_park
    vn, vloc = best_normal(rod)
    d_norm = rod - vloc["difficulty"]
    m_norm = calc_M_UR(d_norm)
    base_norm = loc_avg(vloc) * m_norm
    ratio = raw_park / base_norm
    print(f"    rod={rod}: 乐园(均价{park_avg:.0f}×d={d_park},M={m_park:.2f})={raw_park:.1f}  "
          f"vs  {vloc['name']}(均价{loc_avg(vloc):.0f}×d={d_norm},M={m_norm:.2f})={base_norm:.1f}  "
          f"→ {ratio*100:.0f}%")

print(f"\n  {'项':<32}{'rod=9':>14}{'rod=10':>14}{'rod=11':>14}")
print("  " + "-" * 74)

# === B. 逐层叠加 ===
rows = []
for rod in [9, 10, 11]:
    vn, vloc = best_normal(rod)
    d_park = max(0, rod - PARK_DIFF)
    m_park = calc_M_UR(d_park)

    # Layer 0: 普通图基准
    v_norm = vn
    # Layer 1: 乐园裸图（同 d 下，乐园鱼价优势）
    raw_park = park_avg * m_park
    # Layer 2: + 水晶猫城堡 rod+1 (30%)
    raw_next = park_avg * calc_M_UR(max(0, rod + 1 - PARK_DIFF))
    castle_mix = (1 - CASTLE_PROB) * raw_park + CASTLE_PROB * raw_next
    # Layer 3: + DAILY_MULT (满级四建筑)
    full_park = castle_mix * DAILY_MULT

    rows.append((rod, v_norm, vloc, raw_park, castle_mix, full_park, m_park))

# Layer 表
print()
L0 = "  Layer 0  普通图基准 V(rod)"
L1 = "  Layer 1  乐园裸图 (park_avg × M)"
L2 = "  Layer 2  + 城堡 rod+1 (30%)"
L3 = "  Layer 3  + DAILY_MULT ×1.399"
for label, idx in [(L0, 1), (L1, 3), (L2, 4), (L3, 5)]:
    vals = [f"{r[idx]:>12.1f}" for r in rows]
    print(f"{label:<32}" + "".join(vals))

print()
REL = "  相对 Layer 0"
for label, idx in [("乐园裸图 vs 普通", 3), ("+城堡 vs 普通", 4), ("满级乐园 vs 普通", 5)]:
    vals = [f"{r[idx]/r[1]*100:>11.0f}%" for r in rows]
    print(f"  {label:<30}" + "".join(vals))

# === C. 增益归因 ===
print(f"\n{'='*92}")
print("  增益归因：满级乐园 vs 普通图 的总增益从哪来")
print(f"{'='*92}\n")
for rod, v_norm, vloc, raw_park, castle_mix, full_park, m_park in rows:
    total = full_park / v_norm
    # 各因子贡献（乘法模型下取对数可加，这里用相对增量近似）
    fish_price_gain = raw_park / v_norm                      # 鱼价+d组合
    castle_gain = castle_mix / raw_park                       # 城堡边际
    daily_gain = full_park / castle_mix                       # DAILY_MULT
    print(f"  rod={rod}:")
    print(f"    总增益 = {total*100:.0f}%")
    print(f"      ├─ 鱼价×概率优势 (乐园{park_avg:.0f}/d={max(0,rod-6)} vs {vloc['name']}{loc_avg(vloc):.0f}/d={rod-vloc['difficulty']})  ×{fish_price_gain:.3f}")
    print(f"      ├─ 水晶猫城堡 rod+1 (30%概率)           ×{castle_gain:.3f}")
    print(f"      └─ DAILY_MULT (满级四建筑)               ×{daily_gain:.3f}")
    print()

# === D. 点破关键 ===
print(f"{'='*92}")
print("  关键洞察")
print(f"{'='*92}")
print(f"""
  『乐园只有 15% 鱼价加成』是拿『乐园前5鱼 vs 长江中游』算的——
  但这是静态、单条、同难度下的鱼价对比，不是收益对比。

  真实收益对比下，乐园还白送了三层乘区：

  1) 概率期望差（rod 9-11 最大贡献者）
     乐园 difficulty=6，玩家 rod=9/10/11 进入时 d=3/4/5；
     V_normal 选的是『最优普通图』：
       rod=9  → 原生古河(diff 9) d=0，M={calc_M_UR(0):.2f}
       rod=10 → 原生古河(diff 9) d=1，M={calc_M_UR(1):.2f}
       rod=11 → 原生古河(diff 9) d=2，M={calc_M_UR(2):.2f}
     乐园 d=3/4/5 的 M 远高于普通图 d=0/1/2 ——
     玩家在普通图『刚刚解锁』，在乐园却已『碾压级领先』。

  2) 水晶猫城堡：30% 概率 rod+1，相当于免费升半级，约 ×1.05~1.10。

  3) DAILY_MULT ×1.399：满级四建筑叠加，纯额外乘区，普通图没有。

  所以『15% 鱼价』只是冰山一角，真正让乐园领先的是：
     难度锚定(6) + 城堡 + DAILY_MULT 三层叠加。
  当 rod 超过 6 越多，乐园的 d 越大、M 越高，领先越夸张。
""")
