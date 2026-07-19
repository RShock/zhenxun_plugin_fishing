"""钓鱼数字编码游戏 - 预先测试脚本 (MITM版)

规则：
- 每次钓到一条鱼，编号为 1~999999999 的随机整数
- 当背包中某些鱼的编号之和的尾数有 n 个 9 时，消耗这些鱼获得 1 分，剩余鱼保留
- 背包超过 MAX_BACKPACK 条时丢弃最早的鱼（滚动窗口）
- 用 Meet-in-the-Middle 求解子集和
"""

import random
import time

MAX_BACKPACK = 30


def find_subset_mitm(values, mod_base, target):
    """Meet-in-the-Middle: 找到和 % mod_base == target 的子集"""
    n = len(values)
    if n == 0:
        return None

    mid = n // 2
    left = [v % mod_base for v in values[:mid]]
    right = [v % mod_base for v in values[mid:]]

    # 枚举左半所有子集和
    left_sums = {}
    for mask in range(1 << len(left)):
        s = 0
        for i in range(len(left)):
            if mask & (1 << i):
                s = (s + left[i]) % mod_base
        if s not in left_sums:
            left_sums[s] = mask

    if target in left_sums:
        mask = left_sums[target]
        return [i for i in range(len(left)) if mask & (1 << i)]

    # 枚举右半，查左半
    for rmask in range(1, 1 << len(right)):
        s = 0
        for i in range(len(right)):
            if rmask & (1 << i):
                s = (s + right[i]) % mod_base
        need = (target - s) % mod_base
        if need in left_sums:
            lmask = left_sums[need]
            indices = [i for i in range(len(left)) if lmask & (1 << i)]
            indices += [mid + i for i in range(len(right)) if rmask & (1 << i)]
            return indices

    return None


def simulate(n, target_score, num_trials=100):
    mod_base = 10**n
    target = mod_base - 1
    total_fish = 0
    t0 = time.time()
    max_calc_time = 0
    calc_times = []

    for trial in range(num_trials):
        backpack = []
        fish_count = 0
        score = 0

        while score < target_score:
            new_fish = random.randint(1, 999999999)
            backpack.append(new_fish)
            fish_count += 1

            # 滚动窗口：超过上限丢弃最早的鱼
            if len(backpack) > MAX_BACKPACK:
                backpack.pop(0)

            t1 = time.time()
            combo = find_subset_mitm(backpack, mod_base, target)
            dt = time.time() - t1
            calc_times.append(dt)
            if dt > max_calc_time:
                max_calc_time = dt

            if combo is not None:
                backpack = [v for i, v in enumerate(backpack) if i not in set(combo)]
                score += 1

        total_fish += fish_count
        if (trial + 1) % 10 == 0:
            elapsed = time.time() - t0
            avg_calc = sum(calc_times) / len(calc_times) * 1000
            print(
                f"  进度: {trial + 1}/{num_trials}, 平均: {total_fish / (trial + 1):.1f}鱼, "
                f"单次计算 avg={avg_calc:.1f}ms max={max_calc_time * 1000:.1f}ms, 总耗时: {elapsed:.1f}s",
                flush=True,
            )

    elapsed = time.time() - t0
    avg_calc = sum(calc_times) / len(calc_times) * 1000
    return total_fish / num_trials, elapsed, avg_calc, max_calc_time * 1000


if __name__ == "__main__":
    print(f"=== 钓鱼数字编码游戏模拟 (MITM, 背包上限={MAX_BACKPACK}) ===\n")

    for n in [7, 8, 9]:
        print(f"--- n={n}（尾数{'9' * n}）---")
        trials = 30 if n >= 9 else 50
        avg, elapsed, avg_ms, max_ms = simulate(n, target_score=1, num_trials=trials)
        print(f"  完成 1 分，平均消耗 {avg:.1f} 条鱼")
        print(
            f"  单次计算: avg={avg_ms:.1f}ms, max={max_ms:.1f}ms, 总耗时: {elapsed:.1f}s\n"
        )
