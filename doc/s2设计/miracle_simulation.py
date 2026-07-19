"""
奇迹功能模拟程序
=================
模拟全副武装玩家通过奇迹功能获取55个星辰木框所需天数。

奇迹机制：
  - 背包里的星空鱼ID为6位随机数(0~999999)
  - 当存在子集，其ID之和 ≡ 999999 (mod 1000000) 时触发奇迹
  - 触发后消耗该子集的鱼，获得1个星辰木框
  - 需要约22条鱼才能触发（2^22 ≈ 4M子集 vs 1M模空间）

目标：55个星辰木框（1+2+3+...+10 = 55，用于升级星空木框10次）

动态过程：
  - 每天获得星空鱼（Poisson分布）
  - 每天检查是否可触发奇迹
  - 触发后消耗鱼，剩余鱼继续累积
  - 重复直到获得55个星辰木框

玩家配置（同星空鱼模拟）：
  - 鱼钩10级 + 传说鱼饵 + 10层打窝
  - 幸运药水常驻
  - 24h/天钓鱼
  - 随机位于1种天气下
"""

import random
import numpy as np
import time
from bisect import bisect_left

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 钓鱼速度（同星空鱼模拟）
# ═══════════════════════════════════════════════════════════════════════════════

HOOK_LEVEL = 10
BAIT_SPEED = 120
NEST_LAYERS = 10
NEST_BONUS = 5
BASE_INTERVAL = 60
STARRY_BASE_RATE = 0.05

WEATHERS = {
    "lost_wind":     {"prob": 0.50, "drop_mult": 1.0},
    "solar_wind":    {"prob": 1/6,  "drop_mult": 1.5},
    "meteor_shower": {"prob": 1/6,  "drop_mult": 1.0},
    "hengjiyuan":    {"prob": 1/6,  "drop_mult": 1.0},
}
WEATHER_NAMES = list(WEATHERS.keys())
WEATHER_PROBS = [WEATHERS[w]["prob"] for w in WEATHER_NAMES]

MIRACLE_TARGET = 7777777
MOD = 10000000


def fishing_interval(is_weekend):
    hook_mult = 1 + HOOK_LEVEL * 10 / 100
    total_speed = BAIT_SPEED + NEST_LAYERS * NEST_BONUS
    bait_mult = 1 + total_speed / 100
    speed = hook_mult * bait_mult
    if is_weekend:
        speed *= 1.3
    return max(1.0, BASE_INTERVAL / speed)


def catches_per_day(is_weekend):
    return 24 * 60 / fishing_interval(is_weekend)


def avg_starry_per_day():
    weekday = catches_per_day(False)
    weekend = catches_per_day(True)
    avg_catches = (5 * weekday + 2 * weekend) / 7
    avg_drop = STARRY_BASE_RATE * sum(
        WEATHERS[w]["prob"] * WEATHERS[w]["drop_mult"] for w in WEATHER_NAMES
    )
    return avg_catches * avg_drop


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Meet-in-the-Middle 子集和搜索
# ═══════════════════════════════════════════════════════════════════════════════

def find_miracle_subset(fish_ids, target=MIRACLE_TARGET, mod=MOD):
    """
    使用meet-in-the-middle寻找子集，使其和 ≡ target (mod mod)。
    返回消耗的鱼索引列表，若不存在返回None。
    
    n ≤ 40时使用精确MITM，n > 40时使用随机化采样。
    """
    n = len(fish_ids)
    if n == 0:
        return None
    
    # 取模
    arr = [x % mod for x in fish_ids]
    
    if n <= 40:
        return _mitm_exact(arr, target, mod)
    else:
        return _mitm_randomized(arr, target, mod, n)


def _mitm_exact(arr, target, mod):
    """精确meet-in-the-middle，n ≤ 40"""
    n = len(arr)
    mid = n // 2
    left = arr[:mid]
    right = arr[mid:]
    
    nl = len(left)
    nr = len(right)
    
    # 用numpy加速子集和生成
    left_sums = np.zeros(1 << nl, dtype=np.int64)
    for i in range(nl):
        left_sums[1 << i : 1 << (i + 1)] = left_sums[: 1 << i] + left[i]
    left_sums %= mod
    
    right_sums = np.zeros(1 << nr, dtype=np.int64)
    for i in range(nr):
        right_sums[1 << i : 1 << (i + 1)] = right_sums[: 1 << i] + right[i]
    right_sums %= mod
    
    # 排序右半，二分查找
    right_order = np.argsort(right_sums)
    right_sorted = right_sums[right_order]
    
    for li in range(len(left_sums)):
        need = (target - left_sums[li]) % mod
        idx = np.searchsorted(right_sorted, need)
        if idx < len(right_sorted) and right_sorted[idx] == need:
            ri = right_order[idx]
            # 构造消耗的鱼索引
            consumed = []
            lm = li
            for i in range(nl):
                if lm & (1 << i):
                    consumed.append(i)
            rm = ri
            for i in range(nr):
                if rm & (1 << i):
                    consumed.append(mid + i)
            if consumed:
                return consumed
    
    return None


def _mitm_randomized(arr, target, mod, n):
    """随机化采样，n > 40"""
    # 随机采样大量子集，寻找目标和
    n_samples = min(200000, 1 << 20)
    seen_sums = {}
    
    for _ in range(n_samples):
        mask = random.randint(1, (1 << n) - 1)
        s = 0
        for i in range(n):
            if mask & (1 << i):
                s = (s + arr[i]) % mod
        need = (target - s) % mod
        if need in seen_sums:
            # 找到匹配
            other_mask = seen_sums[need]
            combined = mask | other_mask
            if combined != mask:  # 确保有交集
                consumed = []
                for i in range(n):
                    if combined & (1 << i):
                        consumed.append(i)
                if consumed:
                    return consumed
        seen_sums[s] = mask
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 奇迹模拟
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_miracle(target_frames=55, max_days=50000, verbose=False):
    """
    模拟获取指定数量星辰木框所需天数。
    
    返回: (天数, 星辰木框数, 统计信息)
    """
    fish_ids = []
    star_frames = 0
    day = 0
    
    # 统计
    total_fish_caught = 0
    total_fish_consumed = 0
    miracle_triggers = []  # 每次触发时的天数和消耗鱼数
    
    avg_starry = avg_starry_per_day()
    
    while star_frames < target_frames and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)
        
        # 生成当天星空鱼
        weather = WEATHER_NAMES[np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)]
        wd = WEATHERS[weather]
        catches = catches_per_day(is_weekend)
        drop_rate = STARRY_BASE_RATE * wd["drop_mult"]
        expected_starry = catches * drop_rate
        n_starry = np.random.poisson(expected_starry)
        
        # 添加新鱼ID
        for _ in range(n_starry):
            fish_ids.append(random.randint(0, 999999))
        total_fish_caught += n_starry
        
        # 检查奇迹触发（可能连续触发多次）
        while len(fish_ids) >= 5:
            subset = find_miracle_subset(fish_ids)
            if subset is None:
                break
            
            # 消耗鱼（从后往前删除以保持索引正确）
            consumed_count = len(subset)
            for idx in sorted(subset, reverse=True):
                fish_ids.pop(idx)
            
            star_frames += 1
            total_fish_consumed += consumed_count
            miracle_triggers.append((day, consumed_count))
            
            if verbose and star_frames % 10 == 0:
                print(f"    第{star_frames}个星辰木框: 第{day}天, "
                      f"消耗{consumed_count}条鱼, 剩余{len(fish_ids)}条")
            
            if star_frames >= target_frames:
                break
    
    stats = {
        "total_fish_caught": total_fish_caught,
        "total_fish_consumed": total_fish_consumed,
        "miracle_triggers": miracle_triggers,
        "final_fish_count": len(fish_ids),
    }
    return day, star_frames, stats


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 预分析：单次奇迹触发概率
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_single_miracle_probability():
    """分析不同鱼数量下单次奇迹触发概率"""
    print("单次奇迹触发概率分析（10000次采样）")
    print(f"{'鱼数量':>6} │ {'触发概率':>8} │ {'平均消耗':>8} │ {'平均剩余':>8}")
    print(f"{'─'*6}─┼─{'─'*8}─┼─{'─'*8}─┼─{'─'*8}")
    
    for n_fish in [10, 12, 14, 16, 18, 20, 22, 24, 26, 28]:
        triggers = 0
        consumed_list = []
        remaining_list = []
        
        trials = 5000
        for _ in range(trials):
            fish = [random.randint(0, 999999) for _ in range(n_fish)]
            subset = find_miracle_subset(fish)
            if subset is not None:
                triggers += 1
                consumed_list.append(len(subset))
                remaining_list.append(n_fish - len(subset))
        
        p = triggers / trials
        avg_consumed = np.mean(consumed_list) if consumed_list else 0
        avg_remaining = np.mean(remaining_list) if remaining_list else 0
        print(f"{n_fish:>6} │ {p*100:>7.2f}% │ {avg_consumed:>8.1f} │ {avg_remaining:>8.1f}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 主模拟
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     奇迹功能模拟 — 55个星辰木框收集时间                    ║")
    print("║   动态累积 + 消耗 + 再累积的完整模拟                       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    avg_starry = avg_starry_per_day()
    print(f"\n钓鱼速度: 平均 {140.7:.1f} 次/天, 平均星空鱼 {avg_starry:.2f} 条/天")
    print(f"奇迹目标: 子集和 ≡ {MIRACLE_TARGET} (mod {MOD})")
    print(f"目标: 55个星辰木框")
    
    # ── 单次奇迹概率分析 ──
    print(f"\n{'='*70}")
    analyze_single_miracle_probability()
    
    # ── 蒙特卡洛模拟 ──
    N_RUNS = 2000  # MITM较慢，降到2000次
    
    print(f"\n{'='*70}")
    print(f"蒙特卡洛模拟: 55个星辰木框 (完整动态模拟)")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")
    
    t0 = time.time()
    days_results = np.zeros(N_RUNS, dtype=int)
    fish_caught_results = np.zeros(N_RUNS, dtype=int)
    fish_consumed_results = np.zeros(N_RUNS, dtype=int)
    first_trigger_days = np.zeros(N_RUNS, dtype=int)
    
    for i in range(N_RUNS):
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        
        day, frames, stats = simulate_miracle(target_frames=55)
        days_results[i] = day
        fish_caught_results[i] = stats["total_fish_caught"]
        fish_consumed_results[i] = stats["total_fish_consumed"]
        if stats["miracle_triggers"]:
            first_trigger_days[i] = stats["miracle_triggers"][0][0]
        else:
            first_trigger_days[i] = day
    
    print(f"  完成，耗时 {time.time()-t0:.1f}s")
    
    # ── 结果统计 ──
    print(f"\n  55个星辰木框收集天数统计:")
    print(f"    平均:       {np.mean(days_results):.1f} 天")
    print(f"    中位数:     {np.median(days_results):.1f} 天")
    print(f"    标准差:     {np.std(days_results):.1f} 天")
    print(f"    最小:       {np.min(days_results)} 天")
    print(f"    最大:       {np.max(days_results)} 天")
    print(f"    25分位:     {np.percentile(days_results, 25):.1f} 天")
    print(f"    75分位:     {np.percentile(days_results, 75):.1f} 天")
    print(f"    90分位:     {np.percentile(days_results, 90):.1f} 天")
    print(f"    95分位:     {np.percentile(days_results, 95):.1f} 天")
    print(f"    99分位:     {np.percentile(days_results, 99):.1f} 天")
    
    print(f"\n  首次奇迹触发天数:")
    print(f"    平均:       {np.mean(first_trigger_days):.1f} 天")
    print(f"    中位数:     {np.median(first_trigger_days):.1f} 天")
    
    print(f"\n  鱼获统计:")
    print(f"    平均总钓获:   {np.mean(fish_caught_results):.0f} 条")
    print(f"    平均总消耗:   {np.mean(fish_consumed_results):.0f} 条")
    print(f"    平均消耗/木框: {np.mean(fish_consumed_results)/55:.1f} 条")
    
    print(f"\n  换算实际时间（24h/天钓鱼）:")
    print(f"    {np.mean(days_results):.1f} 天 ≈ {np.mean(days_results)/30:.1f} 月 ≈ {np.mean(days_results)/365:.2f} 年")
    
    # ── 与其他系统对比 ──
    print(f"\n{'='*70}")
    print("与其他系统对比")
    print(f"{'='*70}")
    print(f"\n{'系统':<25} │ {'平均天数':>8} │ {'中位数':>8} │ {'99分位':>8}")
    print(f"{'─'*25}─┼─{'─'*8}─┼─{'─'*8}─┼─{'─'*8}")
    print(f"{'S2入场券(70天基准×130%)':<25} │ {'91.6':>8} │ {'91.0':>8} │ {'104.0':>8}")
    print(f"{'55猫框(幸运药水)':<25} │ {'20.0':>8} │ {'20.0':>8} │ {'30.0':>8}")
    print(f"{'55星辰木框(奇迹)':<25} │ {np.mean(days_results):>8.1f} │ {np.median(days_results):>8.1f} │ {np.percentile(days_results, 99):>8.1f}")
    
    print(f"\n换算实际时间（24h/天钓鱼）:")
    print(f"  55星辰木框: {np.mean(days_results):.1f} 天 ≈ {np.mean(days_results)/30:.1f} 月 ≈ {np.mean(days_results)/365:.2f} 年")


if __name__ == "__main__":
    main()
