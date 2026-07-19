"""
猫猫乐园建设节奏拟真测试 v5

基于真实引擎参数（balance_v20 权威解）：
- 基础钓鱼间隔 60 分钟（引擎 timedelta(minutes=...)），非秒
- 24h/天，hook=7，传说鱼饵+满打窝+满展示框 → 约 130 竿/天
- 材料率动态：猫爬架广场 Lv0=30%, Lv1=35%, Lv2=40%, Lv3=45%
- 3 材料等权掉落：毛线团 / 小鱼干 / 逗猫棒
- 建筑成本错落分布：ab/bc/ac 各 2 组 + a/b/c 各 1 组
- 雕像门控：8 栋全 Lv1→雕像Lv1→8栋全Lv2→雕像Lv2→8栋全Lv3→雕像Lv3

运行：
    python tests/cat_park_sim/simulation.py            # 单次详细
    python tests/cat_park_sim/simulation.py 42         # 指定种子
    python tests/cat_park_sim/simulation.py batch      # 批量 50 次统计
"""

import random
from collections import defaultdict

# ============================================================
# 1. 材料系统（3 种，等权）
# ============================================================
MAT_YARN = "毛线团"
MAT_FISH = "小鱼干"
MAT_WAND = "逗猫棒"

ALL_MATERIALS = [MAT_YARN, MAT_FISH, MAT_WAND]
MATERIAL_RATE_BASE = 0.30  # 基础材料率（猫爬架广场 Lv0）

# ============================================================
# 2. 建筑成本（ab/bc/ac 各 2 组 + a/b/c 各 1 组）
#    a=毛线团  b=小鱼干  c=逗猫棒
#    Lv1 降 25%, Lv2 降 15%, Lv3 不变 → 平滑前期过渡
# ============================================================
BUILDING_COSTS = {
    # 单材料（a/b/c 各 1）
    "猫猫小木屋": {  # a
        1: {MAT_YARN: 15}, 2: {MAT_YARN: 30}, 3: {MAT_YARN: 55},
    },
    "喵喵鱼塘": {  # b
        1: {MAT_FISH: 18}, 2: {MAT_FISH: 34}, 3: {MAT_FISH: 60},
    },
    "猫爬架广场": {  # c
        1: {MAT_WAND: 15}, 2: {MAT_WAND: 30}, 3: {MAT_WAND: 55},
    },
    # ab 各 2
    "喵咖咖啡馆": {
        1: {MAT_YARN: 9, MAT_FISH: 9}, 2: {MAT_YARN: 17, MAT_FISH: 17}, 3: {MAT_YARN: 30, MAT_FISH: 30},
    },
    "猫猫过山车": {
        1: {MAT_YARN: 9, MAT_FISH: 9}, 2: {MAT_YARN: 17, MAT_FISH: 17}, 3: {MAT_YARN: 30, MAT_FISH: 30},
    },
    # bc 各 2
    "旋转逗猫棒": {
        1: {MAT_FISH: 9, MAT_WAND: 9}, 2: {MAT_FISH: 17, MAT_WAND: 17}, 3: {MAT_FISH: 30, MAT_WAND: 30},
    },
    "水晶猫城堡": {
        1: {MAT_FISH: 9, MAT_WAND: 9}, 2: {MAT_FISH: 17, MAT_WAND: 17}, 3: {MAT_FISH: 30, MAT_WAND: 30},
    },
    # ac 各 2（含雕像）
    "猫咪摩天轮": {
        1: {MAT_YARN: 9, MAT_WAND: 9}, 2: {MAT_YARN: 17, MAT_WAND: 17}, 3: {MAT_YARN: 30, MAT_WAND: 30},
    },
    "传奇猫雕像": {
        1: {MAT_YARN: 12, MAT_WAND: 12}, 2: {MAT_YARN: 24, MAT_WAND: 24}, 3: {MAT_YARN: 42, MAT_WAND: 42},
    },
}

# 建筑效果（仅列出影响建设节奏的；其余不影响材料获取）
BUILDING_EFFECTS = {
    "猫猫小木屋": [0, 0.03, 0.06, 0.10],   # 鱼饵节省（不影响材料）
    "喵喵鱼塘": [1.0, 1.03, 1.06, 1.10],   # 钓鱼速度独立乘区 → 影响竿数
    "猫爬架广场": [0.30, 0.35, 0.40, 0.45],  # 材料率（随建筑等级递增）
    "喵咖咖啡馆": [0, 0.03, 0.06, 0.10],   # 鱼价（不影响材料）
    "旋转逗猫棒": [0, 0.01, 0.03, 0.05],   # 双倍鱼（不影响材料）
    "猫咪摩天轮": [0, 1, 2, 3],            # 签到抽数
    "猫猫过山车": [0, 0.03, 0.06, 0.10],   # 天气增幅 → 影响雨天速度
    "水晶猫城堡": [0, 0.05, 0.15, 0.30],   # 钓鱼等级+1概率（不影响材料）
    "传奇猫雕像": [0, 1, 2, 3],            # 门控
}

SIGN_IN_POOL = ["真多多药水", "时光药水", "幸运药水", "猫猫框", "玉米"]

# ============================================================
# 3. 钓鱼参数（真实引擎）
# ============================================================
BASE_INTERVAL_MIN = 60          # 基础间隔 60 分钟（引擎 base_fishing_interval=60，单位分钟）
HOOK_LEVEL = 7
BAIT_BONUS = 120                # 传说鱼饵 +120%
NEST_LAYERS = 10                # 打窝满层 +50%
FRAME_LAYERS = 10               # 展示框满层 +50%
FISHING_HOURS = 24              # 每日钓鱼时长

# ============================================================
# 4. 天气（6 种）
# ============================================================
WEATHERS = [
    ("晴天", 25, 0.0),    # 名称, 权重, 速度加成%
    ("雨天", 20, 10.0),
    ("流星", 15, 0.0),
    ("暴雨", 15, 0.0),
    ("迷途风", 10, 0.0),
    ("猫！", 15, 0.0),
]
WEATHER_TOTAL = sum(w for _, w, _ in WEATHERS)


def random_weather() -> tuple[str, float]:
    r = random.randint(1, WEATHER_TOTAL)
    cum = 0
    for name, weight, speed in WEATHERS:
        cum += weight
        if r <= cum:
            return name, speed
    return "晴天", 0.0


# ============================================================
# 5. 引擎间隔计算（与 config.py calculate_fishing_interval 一致）
# ============================================================
def calc_interval(pond_mult: float = 1.0) -> float:
    """返回钓鱼间隔（分钟）。pond_mult 为喵喵鱼塘独立乘区（1.0~1.10）。"""
    hook_m = 1 + HOOK_LEVEL * 10 / 100                  # 1.7
    total_bait = BAIT_BONUS + NEST_LAYERS * 5 + FRAME_LAYERS * 5  # 220
    bait_m = 1 + total_bait / 100                        # 鱼饵+打窝+展示框
    return BASE_INTERVAL_MIN / (hook_m * bait_m * pond_mult)


def daily_casts(pond_mult: float, weather_speed_pct: float, coaster_bonus: float) -> int:
    """每日竿数。weather_speed 受猫猫过山车增幅。"""
    interval = calc_interval(pond_mult)
    if weather_speed_pct > 0:
        # 过山车增幅天气速度
        wx_mult = 1 + weather_speed_pct / 100 * (1 + coaster_bonus)
        interval /= wx_mult
    return int(FISHING_HOURS * 60 / interval)


def roll_material() -> str:
    return random.choice(ALL_MATERIALS)


# ============================================================
# 6. 模拟主流程
# ============================================================
def run_simulation(seed: int | None = None, verbose: bool = True) -> dict:
    if seed is not None:
        random.seed(seed)

    building_levels = {name: 0 for name in BUILDING_COSTS}
    inventory = {m: 0 for m in ALL_MATERIALS}

    log = []
    def L(msg: str):
        log.append(msg)
        if verbose:
            print(msg)

    total_casts = 0
    total_materials = 0
    sign_in_results: list[str] = []

    all_lv1_day = 0
    all_lv2_day = 0
    all_lv3_day = 0

    def lv(name: str) -> int:
        return building_levels[name]

    def eff(name: str) -> float | int:
        return BUILDING_EFFECTS[name][lv(name)]

    def can_upgrade(name: str) -> bool:
        cur = lv(name)
        if cur >= 3:
            return False
        statue = "传奇猫雕像"
        if name == statue:
            if cur == 0:
                return all(lv(n) >= 1 for n in BUILDING_EFFECTS if n != statue)
            if cur == 1:
                return all(lv(n) >= 2 for n in BUILDING_EFFECTS if n != statue)
            return all(lv(n) >= 3 for n in BUILDING_EFFECTS if n != statue)
        if cur == 0:
            return True
        if cur == 1:
            return lv(statue) >= 1
        return lv(statue) >= 2

    def check_all_level(level: int) -> bool:
        return all(lv(n) >= level for n in BUILDING_EFFECTS)

    total_cost = sum(sum(c.values()) for b in BUILDING_COSTS.values() for c in b.values())
    base_casts = daily_casts(1.0, 0, 0)
    L("🐱 猫猫乐园 v5 — 3材料·错落成本·动态材料率")
    L(f"   基础竿数: ~{base_casts}/天 | 材料率 {MATERIAL_RATE_BASE*100:.0f}%~45% | 总成本 {total_cost}")

    MAX_DAYS = 60
    day = 1
    done = False

    while day <= MAX_DAYS and not done:
        weather_name, weather_speed = random_weather()

        # 签到
        draws = int(eff("猫咪摩天轮"))
        today_sign = []
        for _ in range(draws):
            prize = random.choice(SIGN_IN_POOL)
            today_sign.append(prize)
            sign_in_results.append(prize)

        # 当日参数
        pond_mult = eff("喵喵鱼塘")
        coaster_b = eff("猫猫过山车")
        casts = daily_casts(pond_mult, weather_speed, coaster_b)
        total_casts += casts

        # 材料掉落（材料率随猫爬架广场等级动态变化）
        material_rate = eff("猫爬架广场")
        mats_today: dict[str, int] = defaultdict(int)
        for _ in range(casts):
            if random.random() < material_rate:
                mat = roll_material()
                inventory[mat] += 1
                mats_today[mat] += 1
                total_materials += 1

        # 建造（贪婪：能升就升，重复直到无法升级）
        built = []
        progressed = True
        while progressed:
            progressed = False
            for name in BUILDING_COSTS:
                cur = lv(name)
                if cur >= 3 or not can_upgrade(name):
                    continue
                cost = BUILDING_COSTS[name][cur + 1]
                if all(inventory.get(m, 0) >= q for m, q in cost.items()):
                    for m, q in cost.items():
                        inventory[m] -= q
                    building_levels[name] += 1
                    built.append(f"{name}→Lv{lv(name)}")
                    progressed = True

        build_log = "; ".join(built) if built else "—"
        total_lv = sum(lv(n) for n in BUILDING_EFFECTS)
        mat_info = ", ".join(f"{k}×{v}" for k, v in sorted(mats_today.items())) if mats_today else "无"
        sign_info = f"签:{','.join(today_sign)}" if today_sign else ""

        L(f"[Day {day:>3}] {weather_name} | {casts}竿 | 材:{mat_info} | "
          f"库存 {MAT_YARN}{inventory[MAT_YARN]} {MAT_FISH}{inventory[MAT_FISH]} {MAT_WAND}{inventory[MAT_WAND]} | "
          f"图纸{total_lv}/27 | {build_log} | {sign_info}")

        if all_lv1_day == 0 and check_all_level(1):
            all_lv1_day = day
            L(f"  🔓 全9栋Lv1！雕像解锁Lv2建筑！")
        if all_lv2_day == 0 and check_all_level(2):
            all_lv2_day = day
            L(f"  🔓 全9栋Lv2！雕像解锁Lv3建筑！")
        if check_all_level(3):
            all_lv3_day = day
            L(f"  🏆 竣工！鱼竿+1(外部生效)！")
            done = True

        day += 1

    return {
        "total_days": day - 1,
        "all_lv1_day": all_lv1_day,
        "all_lv2_day": all_lv2_day,
        "all_lv3_day": all_lv3_day,
        "total_casts": total_casts,
        "total_materials": total_materials,
        "sign_in_results": sign_in_results,
        "building_levels": dict(building_levels),
        "inventory": dict(inventory),
        "log": log,
    }


def print_summary(r: dict):
    print()
    print("=" * 70)
    print("  猫猫乐园拟真 v5 — 3材料·错落成本 (24h/天)")
    print("=" * 70)
    print(f"  总天数:          {r['total_days']} 天")
    if r['all_lv1_day']: print(f"  全Lv1(解锁Lv2): Day {r['all_lv1_day']}")
    if r['all_lv2_day']: print(f"  全Lv2(解锁Lv3): Day {r['all_lv2_day']}")
    if r['all_lv3_day']: print(f"  全Lv3(竣工):    Day {r['all_lv3_day']}")
    print(f"  总竿数:          {r['total_casts']:,}")
    print(f"  总材料:          {r['total_materials']:,}")
    print(f"  签到:            {dict((p, r['sign_in_results'].count(p)) for p in SIGN_IN_POOL)}")
    print()
    for name in BUILDING_EFFECTS:
        lv = r['building_levels'][name]
        bar = "█" * lv + "░" * (3 - lv)
        print(f"    {name:<10} Lv{lv} {bar}")
    inv = r['inventory']
    print(f"\n  剩余材料: {MAT_YARN}{inv.get(MAT_YARN,0)} {MAT_FISH}{inv.get(MAT_FISH,0)} {MAT_WAND}{inv.get(MAT_WAND,0)}")
    print("=" * 70)


def run_batch(n: int = 50):
    print(f"\n批量拟真 {n} 次 (24h/天, 材料率30%~45%动态)")
    print("-" * 55)
    days = []
    lv1_days = []
    lv2_days = []
    for _ in range(n):
        seed = random.randint(0, 2 ** 31 - 1)
        r = run_simulation(seed=seed, verbose=False)
        days.append(r['total_days'])
        if r['all_lv1_day']: lv1_days.append(r['all_lv1_day'])
        if r['all_lv2_day']: lv2_days.append(r['all_lv2_day'])
    avg = sum(days) / len(days)
    print(f"  平均: {avg:.1f}天 | 最短: {min(days)} | 最长: {max(days)}")
    if lv1_days:
        print(f"  全Lv1平均: {sum(lv1_days)/len(lv1_days):.1f}天")
    if lv2_days:
        print(f"  全Lv2平均: {sum(lv2_days)/len(lv2_days):.1f}天")
    print(f"  18~22天占比: {sum(1 for d in days if 18 <= d <= 22) / len(days) * 100:.0f}%")
    print(f"  分布: {sorted(days)}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        run_batch(50)
    else:
        seed = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
        r = run_simulation(seed=seed, verbose=True)
        print_summary(r)
