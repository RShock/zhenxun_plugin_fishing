"""
星空鱼系统超拟真模拟程序
==========================
模拟全副武装玩家在11-20图24h/天钓鱼，计算获得究极奖励的平均天数。

玩家配置：
  - 鱼钩等级: 10 (速度×2.0)
  - 鱼饵: 传说鱼饵 (速度+120%)
  - 打窝: 10层 (速度+50%)
  - 幸运药水: 常驻 (星空鱼2选1)
  - 鱼竿: 不计入（不影响星空鱼概率）
  - 天气: 每天随机位于1种天气下

天气分布（11-20图）：
  - 5张图有星空气候 (太阳风/流星雨/恒纪元 各约1/6)
  - 5张图全部迷途风 (1/2)

番型-奖池映射（方案B）：
  - 普通(0分):     无奖励
  - 小吉(1-2分):   低级奖池
  - 良品+稀有(3-5): 中级奖池
  - 稀有+珍品+极品(6-10):高级奖池
  - 传说+神话(11+): 究极奖池

碎片升级链：
  - 5个低级碎片 → 1个中级奖池物品
  - 5个中级碎片 → 1个高级奖池物品
"""

import sys
import csv
import math
import random
import time
import numpy as np
from pathlib import Path
from collections import defaultdict
from itertools import product

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from six_digit_lottery import (
    digits_of, score_digits, FEATURES, FEATURE_BY_LABEL,
    raw_and_max_features, label_cn, band, load_fans
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 加载权重 & 预计算分数分布
# ═══════════════════════════════════════════════════════════════════════════════

def load_weights():
    """从 six_fan_stats.tsv 加载番种权重"""
    fans = load_fans()
    weights = [0.0] * len(FEATURES)
    for r in fans:
        weights[int(r["id"])] = float(r["rarity_points"])
    return weights


def load_normal_distribution():
    """从 six_rounded_score_distribution.tsv 加载正常天气的整数分分布"""
    score_counts = {}
    with (ROOT / "six_rounded_score_distribution.tsv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            score_counts[int(r["rounded_score"])] = int(r["count"])
    return score_counts


def compute_hengjiyuan_distribution(weights, use_cache=True):
    """计算恒纪元天气下的分数分布（每位数字仅取2-8，共7^6=117649个号码）"""
    cache_path = ROOT / "hengjiyuan_score_distribution.tsv"
    if use_cache and cache_path.exists():
        score_counts = {}
        with cache_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for r in reader:
                score_counts[int(r["rounded_score"])] = int(r["count"])
        return score_counts

    digits_pool = [2, 3, 4, 5, 6, 7, 8]
    score_counts = defaultdict(int)
    for d in product(digits_pool, repeat=6):
        score = score_digits(list(d), weights)
        rounded = int(math.floor(score + 0.5))
        score_counts[rounded] += 1

    # 写缓存
    with cache_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rounded_score", "count"])
        for s in sorted(score_counts.keys()):
            writer.writerow([s, score_counts[s]])

    return dict(score_counts)


def compute_max_n_distribution(score_counts, n):
    """
    计算n次独立采样取最大值后的分数分布。
    P(max=k) = CDF(k)^n - CDF(k-1)^n
    """
    total = sum(score_counts.values())
    scores = sorted(score_counts.keys())

    # 构建连续CDF（处理分数缺失，如没有16分）
    max_score = max(scores)
    cdf_array = np.zeros(max_score + 1)
    cum = 0
    for s in range(max_score + 1):
        if s in score_counts:
            cum += score_counts[s]
        cdf_array[s] = cum / total

    # P(max=k) = CDF(k)^n - CDF(k-1)^n
    cdf_n = cdf_array ** n
    prev = 0.0
    result = {}
    for s in range(max_score + 1):
        p = cdf_n[s] - prev
        if p > 1e-15:
            result[s] = p
        prev = cdf_n[s]
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 奖池配置（方案B）
# ═══════════════════════════════════════════════════════════════════════════════

def score_to_pool(score):
    """展示分 → 奖池级别"""
    if score == 0:
        return None
    elif score <= 2:
        return "low"
    elif score <= 5:
        return "mid"
    elif score <= 10:
        return "high"
    else:
        return "ultimate"


POOL_NAMES = ["none", "low", "mid", "high", "ultimate"]
POOL_CN = {"none": "无奖励", "low": "低级奖池", "mid": "中级奖池",
           "high": "高级奖池", "ultimate": "究极奖池"}

LOW_POOL = ["玉米", "黑商额外兑换券", "抽奖碎片"]
MID_POOL = ["多多药水", "幸运药水", "重置药水", "猫框", "中级抽奖碎片"]
HIGH_POOL = ["闪光药水", "时光药水", "UTR自选券"]
ULTIMATE_REST = ["时光药水*10", "UTR自选券*10"]


def compute_pool_probs(max_dist):
    """从 max 分布聚合到奖池概率，返回与 POOL_NAMES 对齐的概率数组"""
    probs = {name: 0.0 for name in POOL_NAMES}
    for score, p in max_dist.items():
        pool = score_to_pool(score)
        key = pool if pool else "none"
        probs[key] += p
    return np.array([probs[name] for name in POOL_NAMES])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 钓鱼速度计算
# ═══════════════════════════════════════════════════════════════════════════════

HOOK_LEVEL = 10
BAIT_SPEED = 120       # 传说鱼饵
NEST_LAYERS = 10
NEST_BONUS = 5          # 每层 +5%
BASE_INTERVAL = 60      # 分钟


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


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 天气系统
# ═══════════════════════════════════════════════════════════════════════════════

STARRY_BASE_RATE = 0.05  # 星空鱼基础掉率 5%

WEATHERS = {
    "lost_wind":     {"prob": 0.5,  "drop_mult": 1.0, "meteor": False, "hengjiyuan": False},
    "solar_wind":    {"prob": 1/6,  "drop_mult": 1.5, "meteor": False, "hengjiyuan": False},
    "meteor_shower": {"prob": 1/6,  "drop_mult": 1.0, "meteor": True,  "hengjiyuan": False},
    "hengjiyuan":    {"prob": 1/6,  "drop_mult": 1.0, "meteor": False, "hengjiyuan": True},
}

WEATHER_NAMES = list(WEATHERS.keys())
WEATHER_PROBS = np.array([WEATHERS[w]["prob"] for w in WEATHER_NAMES])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 奖励追踪器
# ═══════════════════════════════════════════════════════════════════════════════

class RewardTracker:
    def __init__(self):
        self.low_shards = 0
        self.mid_shards = 0
        self.ultimate_reached = False
        self.ultimate_method = None
        self.rewards = defaultdict(int)
        self.total_starry = 0
        self.pool_counts = defaultdict(int)

    def give_reward(self, pool):
        self.total_starry += 1
        self.pool_counts[pool or "none"] += 1
        if pool is None:
            return
        if pool == "low":
            item = random.choice(LOW_POOL)
            if item == "抽奖碎片":
                self.low_shards += 1
                self._check_low_upgrade()
            else:
                self.rewards[item] += 1
        elif pool == "mid":
            item = random.choice(MID_POOL)
            if item == "中级抽奖碎片":
                self.mid_shards += 1
                self._check_mid_upgrade()
            else:
                self.rewards[item] += 1
        elif pool == "high":
            item = random.choice(HIGH_POOL)
            self.rewards[item] += 1
        elif pool == "ultimate":
            if not self.ultimate_reached:
                self.ultimate_reached = True
                self.ultimate_method = "direct"
                self.rewards[random.choice(ULTIMATE_REST)] += 1
            else:
                self.rewards[random.choice(ULTIMATE_REST)] += 1

    def _check_low_upgrade(self):
        while self.low_shards >= 5:
            self.low_shards -= 5
            self.rewards["[升级]低级→中级"] += 1
            item = random.choice(MID_POOL)
            if item == "中级抽奖碎片":
                self.mid_shards += 1
                self._check_mid_upgrade()
            else:
                self.rewards[item] += 1

    def _check_mid_upgrade(self):
        while self.mid_shards >= 5:
            self.mid_shards -= 5
            self.rewards["[升级]中级→高级"] += 1
            item = random.choice(HIGH_POOL)
            self.rewards[item] += 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 模拟主循环
# ═══════════════════════════════════════════════════════════════════════════════

def precompute_weather_data(normal_dist, hengjiyuan_dist, use_lucky=True):
    """预计算每种天气的奖池概率和分数概率"""
    weather_data = {}
    for name, w in WEATHERS.items():
        base_dist = hengjiyuan_dist if w["hengjiyuan"] else normal_dist
        n_meteor = 2 if w["meteor"] else 1
        n_lucky = 2 if use_lucky else 1
        n_total = n_meteor * n_lucky
        max_dist = compute_max_n_distribution(base_dist, n_total)
        pool_probs = compute_pool_probs(max_dist)

        # 分数概率数组（用于分数累积追踪）
        max_score = max(max_dist.keys()) if max_dist else 0
        score_probs = np.zeros(max_score + 1)
        for s, p in max_dist.items():
            score_probs[s] = p

        # 期望单条星空鱼分数
        expected_score = sum(s * p for s, p in max_dist.items())

        weather_data[name] = {
            "pool_probs": pool_probs,
            "score_probs": score_probs,
            "expected_score": expected_score,
            "n_total": n_total,
            "drop_mult": w["drop_mult"],
        }
    return weather_data


def simulate_one(weather_data, max_days=5000):
    """模拟一次完整过程，返回 (天数, 方式, tracker)"""
    tracker = RewardTracker()
    day = 0
    while not tracker.ultimate_reached and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)

        # 随机选择天气
        weather = WEATHER_NAMES[
            np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
        ]
        wd = weather_data[weather]

        catches = catches_per_day(is_weekend)
        drop_rate = STARRY_BASE_RATE * wd["drop_mult"]
        expected_starry = catches * drop_rate
        n_starry = np.random.poisson(expected_starry)

        if n_starry > 0:
            # 批量采样奖池
            pool_indices = np.random.choice(
                len(POOL_NAMES), size=n_starry, p=wd["pool_probs"]
            )
            for idx in pool_indices:
                tracker.give_reward(POOL_NAMES[idx])
                if tracker.ultimate_reached:
                    break

    return day, tracker.ultimate_method, tracker


def simulate_one_with_flash(weather_data, flash_pool_probs, max_days=5000):
    """模拟一次（带闪光药水：每天8小时伽马射线暴）"""
    tracker = RewardTracker()
    day = 0
    while not tracker.ultimate_reached and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)

        # 8小时闪光药水（伽马射线暴：太阳风+流星雨+恒纪元+幸运药水）
        catches_flash = catches_per_day(is_weekend) * (8 / 24)
        drop_flash = STARRY_BASE_RATE * 1.5  # 太阳风 ×1.5
        expected_flash = catches_flash * drop_flash
        n_flash = np.random.poisson(expected_flash)

        if n_flash > 0:
            pool_indices = np.random.choice(
                len(POOL_NAMES), size=n_flash, p=flash_pool_probs
            )
            for idx in pool_indices:
                tracker.give_reward(POOL_NAMES[idx])
                if tracker.ultimate_reached:
                    break

        if tracker.ultimate_reached:
            break

        # 16小时随机天气
        weather = WEATHER_NAMES[
            np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
        ]
        wd = weather_data[weather]
        catches_normal = catches_per_day(is_weekend) * (16 / 24)
        drop_normal = STARRY_BASE_RATE * wd["drop_mult"]
        expected_normal = catches_normal * drop_normal
        n_normal = np.random.poisson(expected_normal)

        if n_normal > 0:
            pool_indices = np.random.choice(
                len(POOL_NAMES), size=n_normal, p=wd["pool_probs"]
            )
            for idx in pool_indices:
                tracker.give_reward(POOL_NAMES[idx])
                if tracker.ultimate_reached:
                    break

    return day, tracker.ultimate_method, tracker


# ═══════════════════════════════════════════════════════════════════════════════
# 6b. 分数累积模拟（新机制：努力值达标获得S2入场券）
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_score_for_days(weather_data, n_days, use_flash=False, flash_score_probs=None):
    """模拟 n_days 天，返回总累积分数和星空鱼总数"""
    total_score = 0
    total_starry = 0

    for day in range(1, n_days + 1):
        is_weekend = (day % 7) in (6, 0)

        if use_flash:
            # 8小时闪光药水
            catches_flash = catches_per_day(is_weekend) * (8 / 24)
            drop_flash = STARRY_BASE_RATE * 1.5
            expected_flash = catches_flash * drop_flash
            n_flash = np.random.poisson(expected_flash)
            if n_flash > 0:
                scores = np.random.choice(
                    len(flash_score_probs), size=n_flash, p=flash_score_probs
                )
                total_score += scores.sum()
                total_starry += n_flash

            # 16小时随机天气
            weather = WEATHER_NAMES[
                np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
            ]
            wd = weather_data[weather]
            catches_normal = catches_per_day(is_weekend) * (16 / 24)
            drop_normal = STARRY_BASE_RATE * wd["drop_mult"]
            expected_normal = catches_normal * drop_normal
            n_normal = np.random.poisson(expected_normal)
            if n_normal > 0:
                scores = np.random.choice(
                    len(wd["score_probs"]), size=n_normal, p=wd["score_probs"]
                )
                total_score += scores.sum()
                total_starry += n_normal
        else:
            # 纯随机天气
            weather = WEATHER_NAMES[
                np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
            ]
            wd = weather_data[weather]
            catches = catches_per_day(is_weekend)
            drop_rate = STARRY_BASE_RATE * wd["drop_mult"]
            expected_starry = catches * drop_rate
            n_starry = np.random.poisson(expected_starry)
            if n_starry > 0:
                scores = np.random.choice(
                    len(wd["score_probs"]), size=n_starry, p=wd["score_probs"]
                )
                total_score += scores.sum()
                total_starry += n_starry

    return total_score, total_starry


def simulate_to_score_threshold(weather_data, threshold, use_flash=False, flash_score_probs=None, max_days=20000):
    """模拟直到累积分数达到阈值，返回天数"""
    total_score = 0
    day = 0
    while total_score < threshold and day < max_days:
        day += 1
        is_weekend = (day % 7) in (6, 0)

        if use_flash:
            # 8小时闪光药水
            catches_flash = catches_per_day(is_weekend) * (8 / 24)
            drop_flash = STARRY_BASE_RATE * 1.5
            expected_flash = catches_flash * drop_flash
            n_flash = np.random.poisson(expected_flash)
            if n_flash > 0:
                scores = np.random.choice(
                    len(flash_score_probs), size=n_flash, p=flash_score_probs
                )
                total_score += scores.sum()

            # 16小时随机天气
            weather = WEATHER_NAMES[
                np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
            ]
            wd = weather_data[weather]
            catches_normal = catches_per_day(is_weekend) * (16 / 24)
            drop_normal = STARRY_BASE_RATE * wd["drop_mult"]
            expected_normal = catches_normal * drop_normal
            n_normal = np.random.poisson(expected_normal)
            if n_normal > 0:
                scores = np.random.choice(
                    len(wd["score_probs"]), size=n_normal, p=wd["score_probs"]
                )
                total_score += scores.sum()
        else:
            weather = WEATHER_NAMES[
                np.random.choice(len(WEATHER_NAMES), p=WEATHER_PROBS)
            ]
            wd = weather_data[weather]
            catches = catches_per_day(is_weekend)
            drop_rate = STARRY_BASE_RATE * wd["drop_mult"]
            expected_starry = catches * drop_rate
            n_starry = np.random.poisson(expected_starry)
            if n_starry > 0:
                scores = np.random.choice(
                    len(wd["score_probs"]), size=n_starry, p=wd["score_probs"]
                )
                total_score += scores.sum()

    return day, total_score


def run_simulation(n_runs, use_lucky, use_flash, label, normal_dist, hengjiyuan_dist):
    """运行完整模拟（接受预计算的分布数据）"""
    print(f"\n{'='*70}")
    print(f"模拟场景: {label}")
    print(f"  幸运药水: {'开启' if use_lucky else '关闭'}")
    print(f"  闪光药水: {'开启(8h/天)' if use_flash else '关闭'}")
    print(f"  模拟次数: {n_runs}")
    print(f"{'='*70}")

    # 预计算天气数据
    print("预计算天气奖池概率...")
    weather_data = precompute_weather_data(normal_dist, hengjiyuan_dist, use_lucky)

    for name in WEATHER_NAMES:
        wd = weather_data[name]
        w = WEATHERS[name]
        probs_str = ", ".join(
            f"{POOL_CN[POOL_NAMES[i]]}={wd['pool_probs'][i]*100:.4f}%"
            for i in range(len(POOL_NAMES))
        )
        print(f"  {name} (n={wd['n_total']}, 掉率×{w['drop_mult']}): {probs_str}")

    # 闪光药水数据
    flash_pool_probs = None
    if use_flash:
        # 伽马射线暴: 太阳风(掉率×1.5) + 流星雨(2选1) + 恒纪元(数字2-8) + 幸运药水(2选1)
        flash_n = 2 * (2 if use_lucky else 1)  # 流星雨×幸运
        flash_max_dist = compute_max_n_distribution(hengjiyuan_dist, flash_n)
        flash_pool_probs = compute_pool_probs(flash_max_dist)
        probs_str = ", ".join(
            f"{POOL_CN[POOL_NAMES[i]]}={flash_pool_probs[i]*100:.4f}%"
            for i in range(len(POOL_NAMES))
        )
        print(f"  闪光药水 (n={flash_n}, 掉率×1.5): {probs_str}")

    # 钓鱼速度
    weekday_catches = catches_per_day(False)
    weekend_catches = catches_per_day(True)
    avg_catches = (5 * weekday_catches + 2 * weekend_catches) / 7
    print(f"\n钓鱼速度:")
    print(f"  工作日: {weekday_catches:.1f} 次/天 (间隔 {fishing_interval(False):.2f} 分钟)")
    print(f"  周末: {weekend_catches:.1f} 次/天 (间隔 {fishing_interval(True):.2f} 分钟)")
    print(f"  平均: {avg_catches:.1f} 次/天")

    # 平均星空鱼/天
    avg_starry = avg_catches * STARRY_BASE_RATE * sum(
        WEATHERS[w]["prob"] * WEATHERS[w]["drop_mult"] for w in WEATHER_NAMES
    )
    print(f"  平均星空鱼: {avg_starry:.2f} 条/天")

    # 运行模拟
    print(f"\n开始模拟 {n_runs} 次...")
    t0 = time.time()
    results = []
    for i in range(n_runs):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (n_runs - i - 1)
            print(f"  进度: {i+1}/{n_runs} ({(i+1)/n_runs*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")

        if use_flash:
            result = simulate_one_with_flash(weather_data, flash_pool_probs)
        else:
            result = simulate_one(weather_data)
        results.append(result)

    total_time = time.time() - t0
    print(f"模拟完成，总耗时 {total_time:.1f}s ({total_time/n_runs*1000:.1f}ms/次)")

    # ── 统计分析 ──
    days_list = np.array([r[0] for r in results])
    methods = [r[1] for r in results if r[1] is not None]

    print(f"\n{'─'*50}")
    print(f"模拟结果")
    print(f"{'─'*50}")
    print(f"模拟次数:       {n_runs}")
    print(f"平均天数:       {np.mean(days_list):.1f} 天")
    print(f"中位数:         {np.median(days_list):.1f} 天")
    print(f"标准差:         {np.std(days_list):.1f} 天")
    print(f"最小:           {np.min(days_list)} 天")
    print(f"最大:           {np.max(days_list)} 天")
    print(f"25分位:         {np.percentile(days_list, 25):.1f} 天")
    print(f"75分位:         {np.percentile(days_list, 75):.1f} 天")
    print(f"90分位:         {np.percentile(days_list, 90):.1f} 天")
    print(f"95分位:         {np.percentile(days_list, 95):.1f} 天")
    print(f"99分位:         {np.percentile(days_list, 99):.1f} 天")

    direct = sum(1 for m in methods if m == "direct")
    shards = sum(1 for m in methods if m == "shards")
    total = len(methods)
    print(f"\n究极获得方式:")
    print(f"  直接获得(传说+神话):  {direct:5d} ({direct/total*100:.1f}%)")
    print(f"  碎片升级:            {shards:5d} ({shards/total*100:.1f}%)")

    # 平均星空鱼数
    avg_starry_count = np.mean([r[2].total_starry for r in results])
    print(f"\n平均星空鱼总数:  {avg_starry_count:.1f} 条")
    print(f"平均每天星空鱼:  {avg_starry_count / np.mean(days_list):.2f} 条/天")

    # 奖池命中分布（最后一次模拟的样本统计）
    sample_tracker = results[-1][2]
    total_starry_sample = sample_tracker.total_starry
    print(f"\n最后一次模拟的奖池命中分布:")
    for name in POOL_NAMES:
        count = sample_tracker.pool_counts.get(name, 0)
        pct = count / total_starry_sample * 100 if total_starry_sample > 0 else 0
        print(f"  {POOL_CN[name]:8s}: {count:5d} ({pct:.2f}%)")

    # 换算为实际时间
    avg_days = np.mean(days_list)
    print(f"\n换算实际时间（24h/天）:")
    print(f"  {avg_days:.1f} 天 = {avg_days/30:.1f} 个月 = {avg_days/365:.2f} 年")

    return results, days_list


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 番型-奖池映射详情表
# ═══════════════════════════════════════════════════════════════════════════════

def print_mapping_table(normal_dist, hengjiyuan_dist):
    """打印番型-奖池映射详情"""
    print(f"\n{'='*70}")
    print("番型-奖池映射表（方案B）")
    print(f"{'='*70}")
    print(f"{'展示分':>6} │ {'段位':4} │ {'数量':>10} │ {'概率':>10} │ {'至少该分概率':>12} │ {'奖池':8}")
    print(f"{'─'*6}─┼─{'─'*4}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*12}─┼─{'─'*8}")

    total = sum(normal_dist.values())
    cum_from_top = 0
    for score in sorted(normal_dist.keys()):
        count = normal_dist[score]
        prob = count / total
        cum_from_top += count
        ge_prob = cum_from_top / total
        pool = score_to_pool(score)
        pool_name = POOL_CN[pool] if pool else POOL_CN["none"]
        print(f"{score:>6} │ {band(score):4} │ {count:>10,} │ {prob:>10.6f} │ {ge_prob:>12.6f} │ {pool_name:8}")

    # 恒纪元分布
    print(f"\n恒纪元天气分数分布（数字仅2-8，共{sum(hengjiyuan_dist.values()):,}个号码）:")
    print(f"{'展示分':>6} │ {'段位':4} │ {'数量':>10} │ {'概率':>10} │ {'奖池':8}")
    print(f"{'─'*6}─┼─{'─'*4}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*8}")
    hj_total = sum(hengjiyuan_dist.values())
    for score in sorted(hengjiyuan_dist.keys()):
        count = hengjiyuan_dist[score]
        prob = count / hj_total
        pool = score_to_pool(score)
        pool_name = POOL_CN[pool] if pool else POOL_CN["none"]
        print(f"{score:>6} │ {band(score):4} │ {count:>10,} │ {prob:>10.6f} │ {pool_name:8}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     星空鱼系统模拟 — 努力值机制（S2入场券）                 ║")
    print("║   70天分数中位数 → 130%阈值 → 达标天数                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # 加载基础数据（只计算一次）
    weights = load_weights()
    normal_dist = load_normal_distribution()

    print("计算恒纪元天气分数分布（数字2-8）...")
    t0 = time.time()
    hengjiyuan_dist = compute_hengjiyuan_distribution(weights)
    print(f"  完成，耗时 {time.time()-t0:.1f}s\n")

    # 打印映射表
    print_mapping_table(normal_dist, hengjiyuan_dist)

    # ── 预计算天气数据 ──
    # 场景A: 幸运药水常驻（无闪光）
    wd_lucky = precompute_weather_data(normal_dist, hengjiyuan_dist, use_lucky=True)
    # 场景B: 幸运药水 + 闪光药水
    wd_lucky_flash = wd_lucky  # 基础天气数据相同

    # 闪光药水的分数概率（伽马射线暴: 太阳风+流星雨+恒纪元+幸运, n=4）
    flash_n = 2 * 2  # 流星雨×幸运
    flash_max_dist = compute_max_n_distribution(hengjiyuan_dist, flash_n)
    flash_max_score = max(flash_max_dist.keys()) if flash_max_dist else 0
    flash_score_probs = np.zeros(flash_max_score + 1)
    for s, p in flash_max_dist.items():
        flash_score_probs[s] = p

    # 钓鱼速度信息
    weekday_catches = catches_per_day(False)
    weekend_catches = catches_per_day(True)
    avg_catches = (5 * weekday_catches + 2 * weekend_catches) / 7
    avg_starry = avg_catches * STARRY_BASE_RATE * sum(
        WEATHERS[w]["prob"] * WEATHERS[w]["drop_mult"] for w in WEATHER_NAMES
    )

    print(f"\n钓鱼速度: 平均 {avg_catches:.1f} 次/天, 平均星空鱼 {avg_starry:.2f} 条/天")

    # 每种天气的期望单条分数
    print(f"\n各天气期望单条星空鱼分数:")
    for name in WEATHER_NAMES:
        wd = wd_lucky[name]
        print(f"  {name:15s}: 期望分数={wd['expected_score']:.4f}, "
              f"n={wd['n_total']}, 掉率×{WEATHERS[name]['drop_mult']}")
    print(f"  闪光药水        : 期望分数={sum(s*p for s,p in flash_max_dist.items()):.4f}, n={flash_n}, 掉率×1.5")

    # ═══════════════════════════════════════════════════════════════════════════
    # 第一阶段：模拟70天分数累积，取中位数
    # ═══════════════════════════════════════════════════════════════════════════
    N_RUNS = 10000
    TARGET_DAYS = 70

    # ── 场景1: 幸运药水（无闪光）──
    print(f"\n{'='*70}")
    print(f"阶段1: 模拟 {TARGET_DAYS} 天分数累积（幸运药水, 无闪光）")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")

    t0 = time.time()
    scores_120_lucky = np.zeros(N_RUNS, dtype=float)
    starry_120_lucky = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        s, n = simulate_score_for_days(wd_lucky, TARGET_DAYS)
        scores_120_lucky[i] = s
        starry_120_lucky[i] = n

    print(f"  完成，耗时 {time.time()-t0:.1f}s")

    median_score_lucky = np.median(scores_120_lucky)
    mean_score_lucky = np.mean(scores_120_lucky)
    threshold_lucky = median_score_lucky * 1.3

    print(f"\n  70天分数累积统计:")
    print(f"    平均分:     {mean_score_lucky:.1f}")
    print(f"    中位数:     {median_score_lucky:.1f}")
    print(f"    标准差:     {np.std(scores_120_lucky):.1f}")
    print(f"    10分位:     {np.percentile(scores_120_lucky, 10):.1f}")
    print(f"    25分位:     {np.percentile(scores_120_lucky, 25):.1f}")
    print(f"    75分位:     {np.percentile(scores_120_lucky, 75):.1f}")
    print(f"    90分位:     {np.percentile(scores_120_lucky, 90):.1f}")
    print(f"    最小:       {np.min(scores_120_lucky):.1f}")
    print(f"    最大:       {np.max(scores_120_lucky):.1f}")
    print(f"\n  ★ 130%中位数阈值 = {threshold_lucky:.1f} 分")
    print(f"    70天平均星空鱼数: {np.mean(starry_120_lucky):.1f} 条")
    print(f"    平均每条星空鱼分数: {mean_score_lucky / np.mean(starry_120_lucky):.4f}")

    # ── 场景2: 幸运药水 + 闪光药水 ──
    print(f"\n{'='*70}")
    print(f"阶段1b: 模拟 {TARGET_DAYS} 天分数累积（幸运+闪光药水）")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")

    t0 = time.time()
    scores_120_flash = np.zeros(N_RUNS, dtype=float)
    starry_120_flash = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        s, n = simulate_score_for_days(wd_lucky_flash, TARGET_DAYS,
                                       use_flash=True, flash_score_probs=flash_score_probs)
        scores_120_flash[i] = s
        starry_120_flash[i] = n

    print(f"  完成，耗时 {time.time()-t0:.1f}s")

    median_score_flash = np.median(scores_120_flash)
    mean_score_flash = np.mean(scores_120_flash)
    threshold_flash = median_score_flash * 1.3

    print(f"\n  70天分数累积统计:")
    print(f"    平均分:     {mean_score_flash:.1f}")
    print(f"    中位数:     {median_score_flash:.1f}")
    print(f"    标准差:     {np.std(scores_120_flash):.1f}")
    print(f"    10分位:     {np.percentile(scores_120_flash, 10):.1f}")
    print(f"    25分位:     {np.percentile(scores_120_flash, 25):.1f}")
    print(f"    75分位:     {np.percentile(scores_120_flash, 75):.1f}")
    print(f"    90分位:     {np.percentile(scores_120_flash, 90):.1f}")
    print(f"    最小:       {np.min(scores_120_flash):.1f}")
    print(f"    最大:       {np.max(scores_120_flash):.1f}")
    print(f"\n  ★ 130%中位数阈值 = {threshold_flash:.1f} 分")
    print(f"    70天平均星空鱼数: {np.mean(starry_120_flash):.1f} 条")
    print(f"    平均每条星空鱼分数: {mean_score_flash / np.mean(starry_120_flash):.4f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 第二阶段：模拟达到130%阈值所需天数
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 场景1: 幸运药水（无闪光）──
    print(f"\n{'='*70}")
    print(f"阶段2: 达到130%阈值所需天数（幸运药水, 无闪光）")
    print(f"  阈值: {threshold_lucky:.1f} 分")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")

    t0 = time.time()
    days_to_threshold_lucky = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        d, _ = simulate_to_score_threshold(wd_lucky, threshold_lucky)
        days_to_threshold_lucky[i] = d

    print(f"  完成，耗时 {time.time()-t0:.1f}s")

    print(f"\n  达标天数统计:")
    print(f"    平均:       {np.mean(days_to_threshold_lucky):.1f} 天")
    print(f"    中位数:     {np.median(days_to_threshold_lucky):.1f} 天")
    print(f"    标准差:     {np.std(days_to_threshold_lucky):.1f} 天")
    print(f"    最小:       {np.min(days_to_threshold_lucky)} 天")
    print(f"    最大:       {np.max(days_to_threshold_lucky)} 天")
    print(f"    25分位:     {np.percentile(days_to_threshold_lucky, 25):.1f} 天")
    print(f"    75分位:     {np.percentile(days_to_threshold_lucky, 75):.1f} 天")
    print(f"    90分位:     {np.percentile(days_to_threshold_lucky, 90):.1f} 天")
    print(f"    95分位:     {np.percentile(days_to_threshold_lucky, 95):.1f} 天")
    print(f"    99分位:     {np.percentile(days_to_threshold_lucky, 99):.1f} 天")

    # ── 场景2: 幸运药水 + 闪光药水 ──
    print(f"\n{'='*70}")
    print(f"阶段2b: 达到130%阈值所需天数（幸运+闪光药水）")
    print(f"  阈值: {threshold_flash:.1f} 分")
    print(f"  模拟次数: {N_RUNS}")
    print(f"{'='*70}")

    t0 = time.time()
    days_to_threshold_flash = np.zeros(N_RUNS, dtype=int)
    for i in range(N_RUNS):
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_RUNS - i - 1)
            print(f"  进度: {i+1}/{N_RUNS} ({(i+1)/N_RUNS*100:.1f}%) "
                  f"已用 {elapsed:.1f}s, 预计剩余 {eta:.1f}s")
        d, _ = simulate_to_score_threshold(wd_lucky_flash, threshold_flash,
                                           use_flash=True, flash_score_probs=flash_score_probs)
        days_to_threshold_flash[i] = d

    print(f"  完成，耗时 {time.time()-t0:.1f}s")

    print(f"\n  达标天数统计:")
    print(f"    平均:       {np.mean(days_to_threshold_flash):.1f} 天")
    print(f"    中位数:     {np.median(days_to_threshold_flash):.1f} 天")
    print(f"    标准差:     {np.std(days_to_threshold_flash):.1f} 天")
    print(f"    最小:       {np.min(days_to_threshold_flash)} 天")
    print(f"    最大:       {np.max(days_to_threshold_flash)} 天")
    print(f"    25分位:     {np.percentile(days_to_threshold_flash, 25):.1f} 天")
    print(f"    75分位:     {np.percentile(days_to_threshold_flash, 75):.1f} 天")
    print(f"    90分位:     {np.percentile(days_to_threshold_flash, 90):.1f} 天")
    print(f"    95分位:     {np.percentile(days_to_threshold_flash, 95):.1f} 天")
    print(f"    99分位:     {np.percentile(days_to_threshold_flash, 99):.1f} 天")

    # ═══════════════════════════════════════════════════════════════════════════
    # 汇总对比
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("努力值机制汇总对比")
    print(f"{'='*70}")

    print(f"\n{'指标':<28} │ {'幸运药水':>12} │ {'幸运+闪光':>12}")
    print(f"{'─'*28}─┼─{'─'*12}─┼─{'─'*12}")
    print(f"{'70天分数中位数':<28} │ {median_score_lucky:>12.1f} │ {median_score_flash:>12.1f}")
    print(f"{'70天分数平均值':<28} │ {mean_score_lucky:>12.1f} │ {mean_score_flash:>12.1f}")
    print(f"{'130%阈值':<28} │ {threshold_lucky:>12.1f} │ {threshold_flash:>12.1f}")
    print(f"{'达标平均天数':<28} │ {np.mean(days_to_threshold_lucky):>12.1f} │ {np.mean(days_to_threshold_flash):>12.1f}")
    print(f"{'达标中位数':<28} │ {np.median(days_to_threshold_lucky):>12.1f} │ {np.median(days_to_threshold_flash):>12.1f}")
    print(f"{'达标90分位':<28} │ {np.percentile(days_to_threshold_lucky, 90):>12.1f} │ {np.percentile(days_to_threshold_flash, 90):>12.1f}")
    print(f"{'达标95分位':<28} │ {np.percentile(days_to_threshold_lucky, 95):>12.1f} │ {np.percentile(days_to_threshold_flash, 95):>12.1f}")
    print(f"{'达标99分位':<28} │ {np.percentile(days_to_threshold_lucky, 99):>12.1f} │ {np.percentile(days_to_threshold_flash, 99):>12.1f}")

    print(f"\n换算实际时间（24h/天钓鱼）:")
    print(f"  幸运药水:    平均 {np.mean(days_to_threshold_lucky):.1f} 天 ≈ "
          f"{np.mean(days_to_threshold_lucky)/30:.1f} 月 ≈ "
          f"{np.mean(days_to_threshold_lucky)/365:.2f} 年")
    print(f"  幸运+闪光:   平均 {np.mean(days_to_threshold_flash):.1f} 天 ≈ "
          f"{np.mean(days_to_threshold_flash)/30:.1f} 月 ≈ "
          f"{np.mean(days_to_threshold_flash)/365:.2f} 年")

    # 与旧机制对比
    print(f"\n与旧机制（随机掉落）对比:")
    print(f"  旧机制(幸运,无闪光): 平均 65.2 天, 中位 61.0 天, 99分位 184.0 天")
    print(f"  旧机制(幸运+闪光):   平均 25.4 天, 中位 23.0 天, 99分位 76.0 天")
    print(f"  新机制(幸运,无闪光): 平均 {np.mean(days_to_threshold_lucky):.1f} 天, "
          f"中位 {np.median(days_to_threshold_lucky):.1f} 天, "
          f"99分位 {np.percentile(days_to_threshold_lucky, 99):.1f} 天")
    print(f"  新机制(幸运+闪光):   平均 {np.mean(days_to_threshold_flash):.1f} 天, "
          f"中位 {np.median(days_to_threshold_flash):.1f} 天, "
          f"99分位 {np.percentile(days_to_threshold_flash, 99):.1f} 天")


if __name__ == "__main__":
    main()
