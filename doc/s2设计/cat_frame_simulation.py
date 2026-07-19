"""
星空木框升级模拟程序
=====================
模拟全副武装玩家获取55个猫框（升级10次星空木框）所需天数。

升级费用：1+2+3+...+10 = 55 个猫框

猫框获取链路：
  1. 1-10图每天5张普通天气(rain/meteor/storm/cat各25%), 3张迷途风, 2张晴天
  2. S1猫猫乐园独立天气: 50%迷途风, 40%普通(各10%), 10%晴天
  3. 猫天气时每条鱼15%概率被猫吃 → 触发猫礼物
  4. 猫礼物: 15%概率给猫框(0.30≤roll<0.45), 保底15次
  5. 幸运药水: 猫框判定双roll(独立15%×2)
  6. 11-20图无猫天气

玩家配置：
  - 鱼钩10级 + 传说鱼饵 + 10层打窝 (速度同星空鱼模拟)
  - 幸运药水常驻
  - 24h/天钓鱼
  - 猫天气期间在猫天气图钓鱼，无猫天气时在其他图钓(不影响猫框)
"""

import random
import numpy as np
import time

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 钓鱼速度（同星空鱼模拟）
# ═══════════════════════════════════════════════════════════════════════════════

HOOK_LEVEL = 10
BAIT_SPEED = 120       # 传说鱼饵
NEST_LAYERS = 10
NEST_BONUS = 5          # 每层 +5%
BASE_INTERVAL = 60      # 分钟

CAT_EAT_CHANCE = 0.15
CAT_FRAME_DROP_CHANCE = 0.15  # 0.30 ≤ roll < 0.45 → 15%
CAT_FRAME_PITY = 15


def fishing_interval(is_weekend):
    """钓鱼间隔（分钟）"""
    hook_mult = 1 + HOOK_LEVEL * 10 / 100          # 2.0
    total_speed = BAIT_SPEED + NEST_LAYERS * NEST_BONUS  # 170
    bait_mult = 1 + total_speed / 100               # 2.7
    speed = hook_mult * bait_mult                   # 5.4
    if is_weekend:
        speed *= 1.3
    return max(1.0, BASE_INTERVAL / speed)


def catches_per_day(is_weekend):
    """每天钓鱼次数"""
    return 24 * 60 / fishing_interval(is_weekend)


def avg_catches_per_day():
    """一周平均每天钓鱼次数"""
    weekday = catches_per_day(False)
    weekend = catches_per_day(True)
    return (5 * weekday + 2 * weekend) / 7


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 天气系统模拟
# ═══════════════════════════════════════════════════════════════════════════════

WEATHER_NORMAL_TYPES = ["rain", "meteor", "storm", "cat"]
WEATHER_LOST_WIND_COUNT = 3  # 1-10图迷途风数量
WEATHER_MIN_HOURS = 6
WEATHER_MAX_HOURS = 18


def generate_daily_cat_coverage():
    """
    模拟一天的天气分配，返回猫天气覆盖的小时数（union）。
    
    1-10图: 5张普通天气(各25%猫), 3张迷途风, 2张晴天
    S1: 50%迷途风, 40%普通(各10%), 10%晴天
    
    返回: 猫天气覆盖的小时数 (0~24)
    """
    cat_intervals = []
    
    # ── 1-10图 ──
    # 10张图中选5张普通天气
    normal_locs = random.sample(range(10), 5)
    for loc in normal_locs:
        wtype = random.choice(WEATHER_NORMAL_TYPES)
        if wtype == "cat":
            duration = random.randint(WEATHER_MIN_HOURS, WEATHER_MAX_HOURS)
            start_hour = random.randint(0, 24 - duration)
            cat_intervals.append((start_hour, start_hour + duration))
    
    # ── S1猫猫乐园 ──
    s1_roll = random.random()
    if s1_roll < 0.10:
        # 10%晴天
        pass
    elif s1_roll < 0.50:
        # 40%普通天气 (rain/meteor/storm/cat 各10%)
        s1_wtype = random.choice(WEATHER_NORMAL_TYPES)
        if s1_wtype == "cat":
            duration = random.randint(WEATHER_MIN_HOURS, WEATHER_MAX_HOURS)
            start_hour = random.randint(0, 24 - duration)
            cat_intervals.append((start_hour, start_hour + duration))
    # else: 50%迷途风 → 无猫
    
    # 计算猫天气覆盖的union小时数
    if not cat_intervals:
        return 0.0
    
    # 合并区间
    cat_intervals.sort()
    merged = [cat_intervals[0]]
    for start, end in cat_intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    
    total_hours = sum(end - start for start, end in merged)
    return min(total_hours, 24.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 猫框获取模拟
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_cat_frame_acquisition(target_frames=55, use_lucky=True, max_days=50000):
    """
    模拟获取指定数量猫框所需天数。
    
    返回: (天数, 猫框数, 猫吃鱼总数)
    """
    cat_frames = 0
    cat_pity = 0
    total_cat_eaten = 0
    day = 0
    
    while cat_frames < target_frames and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)
        
        # 生成当天猫天气覆盖
        cat_hours = generate_daily_cat_coverage()
        if cat_hours <= 0:
            continue
        
        # 当天在猫天气期间的钓鱼次数
        catches = catches_per_day(is_weekend) * (cat_hours / 24.0)
        
        # 猫吃鱼数: 每条鱼15%概率被吃
        n_eaten = np.random.binomial(int(catches), CAT_EAT_CHANCE)
        # 处理小数部分
        if catches > 0 and random.random() < (catchs := catches - int(catches)) if hasattr(catches, '__float__') else False:
            n_eaten += np.random.binomial(1, CAT_EAT_CHANCE)
        
        total_cat_eaten += n_eaten
        
        # 每条被吃的鱼触发猫礼物
        for _ in range(n_eaten):
            cat_pity += 1
            
            # 第一次roll
            roll = random.random()
            got_frame = cat_pity >= CAT_FRAME_PITY or (0.30 <= roll < 0.45)
            
            # 幸运药水: 第二次独立roll
            if use_lucky and not got_frame:
                roll2 = random.random()
                got_frame = 0.30 <= roll2 < 0.45
            
            if got_frame:
                cat_frames += 1
                cat_pity = 0
                if cat_frames >= target_frames:
                    break
    
    return day, cat_frames, total_cat_eaten


def simulate_cat_frame_fast(target_frames=55, use_lucky=True, max_days=50000):
    """
    快速版模拟：用Poisson + 解析方法加速。
    """
    cat_frames = 0
    cat_pity = 0
    day = 0
    
    # 预计算每次猫礼物的猫框概率
    if use_lucky:
        p_frame = 1 - (1 - CAT_FRAME_DROP_CHANCE) ** 2  # 0.2775
    else:
        p_frame = CAT_FRAME_DROP_CHANCE  # 0.15
    
    while cat_frames < target_frames and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)
        
        # 生成当天猫天气覆盖
        cat_hours = generate_daily_cat_coverage()
        if cat_hours <= 0:
            continue
        
        # 当天在猫天气期间的钓鱼次数
        daily_catches = catches_per_day(is_weekend) * (cat_hours / 24.0)
        
        # 猫吃鱼数: Poisson近似
        expected_eaten = daily_catches * CAT_EAT_CHANCE
        n_eaten = np.random.poisson(expected_eaten)
        
        # 每条被吃的鱼触发猫礼物
        for _ in range(n_eaten):
            cat_pity += 1
            
            # 猫框判定
            got_frame = cat_pity >= CAT_FRAME_PITY or (random.random() < p_frame)
            
            if got_frame:
                cat_frames += 1
                cat_pity = 0
                if cat_frames >= target_frames:
                    break
    
    return day, cat_frames


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 主模拟
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     星空木框升级模拟 — 55个猫框收集时间                     ║")
    print("║   升级10次: 1+2+3+...+10 = 55 个猫框                       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    avg_catches = avg_catches_per_day()
    print(f"\n钓鱼速度: 平均 {avg_catches:.1f} 次/天")
    print(f"猫吃鱼概率: {CAT_EAT_CHANCE*100:.0f}%")
    print(f"猫框掉率: {CAT_FRAME_DROP_CHANCE*100:.0f}% (保底{CAT_FRAME_PITY}次)")
    print(f"幸运药水: 猫框双roll → 有效概率 {(1-(1-0.15)**2)*100:.2f}%")
    print(f"目标: 55个猫框")
    
    # ── 预采样天气统计 ──
    print(f"\n预采样天气分布 (100000天)...")
    t0 = time.time()
    cat_hours_samples = [generate_daily_cat_coverage() for _ in range(100000)]
    cat_hours_arr = np.array(cat_hours_samples)
    print(f"  耗时 {time.time()-t0:.1f}s")
    
    no_cat_days = np.sum(cat_hours_arr == 0)
    print(f"\n猫天气覆盖统计:")
    print(f"  无猫天气天数:   {no_cat_days} ({no_cat_days/len(cat_hours_arr)*100:.1f}%)")
    print(f"  平均猫天气小时: {np.mean(cat_hours_arr):.2f} h/天")
    print(f"  中位数:         {np.median(cat_hours_arr):.1f} h")
    print(f"  25分位:         {np.percentile(cat_hours_arr, 25):.1f} h")
    print(f"  75分位:         {np.percentile(cat_hours_arr, 75):.1f} h")
    print(f"  90分位:         {np.percentile(cat_hours_arr, 90):.1f} h")
    print(f"  最大:           {np.max(cat_hours_arr):.1f} h")
    
    # 猫天气覆盖率为0的天数比例
    cat_coverage_ratio = np.mean(cat_hours_arr) / 24.0
    print(f"\n  平均猫天气覆盖率: {cat_coverage_ratio*100:.1f}%")
    
    # 预期猫吃鱼数/天
    expected_eaten_per_day = avg_catches * cat_coverage_ratio * CAT_EAT_CHANCE
    print(f"  预期猫吃鱼/天:   {expected_eaten_per_day:.2f} 条")
    
    # 预期猫框/天 (含保底, 幸运药水)
    p_frame = 1 - (1 - 0.15) ** 2  # 0.2775
    # 含保底的期望礼物数/猫框 ≈ 3.583 (幸运), 6.084 (无幸运)
    expected_gifts_per_frame_lucky = 3.583
    expected_frames_per_day_lucky = expected_eaten_per_day / expected_gifts_per_frame_lucky
    print(f"  预期猫框/天(幸运): {expected_frames_per_day_lucky:.3f} 个")
    print(f"  理论预期天数(幸运): {55 / expected_frames_per_day_lucky:.0f} 天")
    
    p_frame_no_lucky = 0.15
    expected_gifts_per_frame_no_lucky = 6.084
    expected_frames_per_day_no_lucky = expected_eaten_per_day / expected_gifts_per_frame_no_lucky
    print(f"  预期猫框/天(无幸运): {expected_frames_per_day_no_lucky:.3f} 个")
    print(f"  理论预期天数(无幸运): {55 / expected_frames_per_day_no_lucky:.0f} 天")
    
    # ── 蒙特卡洛模拟 ──
    N_RUNS = 10000
    
    # 场景1: 幸运药水常驻
    print(f"\n{'='*70}")
    print(f"蒙特卡洛模拟: 55个猫框 (幸运药水常驻)")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")
    
    t0 = time.time()
    days_lucky = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        d, _ = simulate_cat_frame_fast(target_frames=55, use_lucky=True)
        days_lucky[i] = d
    
    print(f"  完成，耗时 {time.time()-t0:.1f}s")
    
    print(f"\n  55个猫框收集天数统计 (幸运药水):")
    print(f"    平均:       {np.mean(days_lucky):.1f} 天")
    print(f"    中位数:     {np.median(days_lucky):.1f} 天")
    print(f"    标准差:     {np.std(days_lucky):.1f} 天")
    print(f"    最小:       {np.min(days_lucky)} 天")
    print(f"    最大:       {np.max(days_lucky)} 天")
    print(f"    25分位:     {np.percentile(days_lucky, 25):.1f} 天")
    print(f"    75分位:     {np.percentile(days_lucky, 75):.1f} 天")
    print(f"    90分位:     {np.percentile(days_lucky, 90):.1f} 天")
    print(f"    95分位:     {np.percentile(days_lucky, 95):.1f} 天")
    print(f"    99分位:     {np.percentile(days_lucky, 99):.1f} 天")
    
    print(f"\n  换算实际时间（24h/天钓鱼）:")
    print(f"    {np.mean(days_lucky):.1f} 天 ≈ {np.mean(days_lucky)/30:.1f} 月 ≈ {np.mean(days_lucky)/365:.2f} 年")
    
    # 场景2: 无幸运药水
    print(f"\n{'='*70}")
    print(f"蒙特卡洛模拟: 55个猫框 (无幸运药水)")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")
    
    t0 = time.time()
    days_no_lucky = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        d, _ = simulate_cat_frame_fast(target_frames=55, use_lucky=False)
        days_no_lucky[i] = d
    
    print(f"  完成，耗时 {time.time()-t0:.1f}s")
    
    print(f"\n  55个猫框收集天数统计 (无幸运药水):")
    print(f"    平均:       {np.mean(days_no_lucky):.1f} 天")
    print(f"    中位数:     {np.median(days_no_lucky):.1f} 天")
    print(f"    标准差:     {np.std(days_no_lucky):.1f} 天")
    print(f"    最小:       {np.min(days_no_lucky)} 天")
    print(f"    最大:       {np.max(days_no_lucky)} 天")
    print(f"    25分位:     {np.percentile(days_no_lucky, 25):.1f} 天")
    print(f"    75分位:     {np.percentile(days_no_lucky, 75):.1f} 天")
    print(f"    90分位:     {np.percentile(days_no_lucky, 90):.1f} 天")
    print(f"    95分位:     {np.percentile(days_no_lucky, 95):.1f} 天")
    print(f"    99分位:     {np.percentile(days_no_lucky, 99):.1f} 天")
    
    print(f"\n  换算实际时间（24h/天钓鱼）:")
    print(f"    {np.mean(days_no_lucky):.1f} 天 ≈ {np.mean(days_no_lucky)/30:.1f} 月 ≈ {np.mean(days_no_lucky)/365:.2f} 年")
    
    # ── 汇总 ──
    print(f"\n{'='*70}")
    print("汇总对比")
    print(f"{'='*70}")
    print(f"\n{'指标':<20} │ {'幸运药水':>12} │ {'无幸运药水':>12}")
    print(f"{'─'*20}─┼─{'─'*12}─┼─{'─'*12}")
    print(f"{'平均天数':<20} │ {np.mean(days_lucky):>12.1f} │ {np.mean(days_no_lucky):>12.1f}")
    print(f"{'中位数':<20} │ {np.median(days_lucky):>12.1f} │ {np.median(days_no_lucky):>12.1f}")
    print(f"{'标准差':<20} │ {np.std(days_lucky):>12.1f} │ {np.std(days_no_lucky):>12.1f}")
    print(f"{'90分位':<20} │ {np.percentile(days_lucky, 90):>12.1f} │ {np.percentile(days_no_lucky, 90):>12.1f}")
    print(f"{'95分位':<20} │ {np.percentile(days_lucky, 95):>12.1f} │ {np.percentile(days_no_lucky, 95):>12.1f}")
    print(f"{'99分位':<20} │ {np.percentile(days_lucky, 99):>12.1f} │ {np.percentile(days_no_lucky, 99):>12.1f}")
    
    print(f"\n换算实际时间（24h/天钓鱼）:")
    print(f"  幸运药水:   平均 {np.mean(days_lucky):.1f} 天 ≈ {np.mean(days_lucky)/30:.1f} 月 ≈ {np.mean(days_lucky)/365:.2f} 年")
    print(f"  无幸运药水: 平均 {np.mean(days_no_lucky):.1f} 天 ≈ {np.mean(days_no_lucky)/30:.1f} 月 ≈ {np.mean(days_no_lucky)/365:.2f} 年")
    
    # 与S2入场券对比
    print(f"\n与S2入场券努力值机制对比:")
    print(f"  S2入场券(70天基准):   平均 91.6 天, 中位 91.0 天")
    print(f"  55猫框(幸运药水):     平均 {np.mean(days_lucky):.1f} 天, 中位 {np.median(days_lucky):.1f} 天")
    print(f"  55猫框(无幸运):       平均 {np.mean(days_no_lucky):.1f} 天, 中位 {np.median(days_no_lucky):.1f} 天")


if __name__ == "__main__":
    main()
