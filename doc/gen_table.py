import numpy as np
import pandas as pd

# 防止 pandas 省略行列
pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

# ========== 可调参数 ==========
C = 2.0  # 稀有度价格倍率
s = 0.4  # 均值移动速度：μ(d) = s * d
sigma = 0.8  # 离散化高斯的标准差（控制集中度）
threshold = 0.05  # 尾部裁剪阈值
d_max = 19  # 最大钓鱼等级（前20个等级）
max_level_show = 10  # 显示关卡 1~10
max_rarity_show = 10  # 显示稀有度 0~9
show_rarity_dist = 16  # 分布表显示稀有度 0~15

# 稀有度截断最大值：根据最大μ+5σ确定
max_r_calc = int(np.ceil(s * d_max + 5 * sigma)) + 1

# ========== 1. 生成裁剪后的分布及矩母函数 M(d) ==========
distributions = {}  # d -> probability array for r=0..max_r_calc
M_d = np.zeros(d_max + 1)

for d in range(d_max + 1):
    mu = s * d
    r_vals = np.arange(max_r_calc + 1)
    weights = np.exp(-0.5 * ((r_vals - mu) / sigma) ** 2)
    probs = weights / weights.sum()

    # 尾部裁剪：将 < threshold 的概率合并到最近的非尾部等级
    keep = probs >= threshold
    new_probs = np.zeros_like(probs)
    for i in range(len(probs)):
        if keep[i]:
            new_probs[i] = probs[i]
        else:
            dists = np.where(keep)[0]
            idx = dists[np.argmin(np.abs(dists - i))]
            new_probs[idx] += probs[i]
    new_probs /= new_probs.sum()
    distributions[d] = new_probs
    M_d[d] = np.sum(new_probs * (C**r_vals))

# ========== 2. 拟合 log M(d) = alpha + beta * d ==========
coeff = np.polyfit(np.arange(d_max + 1), np.log(M_d), 1)
beta, alpha = coeff[0], coeff[1]
A = np.exp(beta)
print(f"拟合 beta = {beta:.6f}, A = {A:.6f}")

# 基准：令 base_1 = 10（取整后仍为10）
B = 10.0 / A
# 生成基础价格（理论值，保留浮点以备取整前查看）
base_prices_raw = np.array([B * (A**n) for n in range(1, max_level_show + 1)])
# ***** 关键修改：基础价格取整 *****
base_prices = np.round(base_prices_raw).astype(int)
print("基础价格（取整后）:", base_prices)

# ========== 3. 价格矩阵（前10关，稀有度0~9）取整 ==========
price_matrix = np.zeros((max_level_show, max_rarity_show), dtype=int)
for n_idx in range(max_level_show):
    base = base_prices[n_idx]
    for r in range(max_rarity_show):
        raw_price = base * (C**r)
        price_matrix[n_idx, r] = int(np.round(raw_price))  # 四舍五入取整

print("\n表1：不同关卡的不同稀有度鱼的价格（整数）")
df_price = pd.DataFrame(
    price_matrix,
    index=[f"关卡{n + 1}" for n in range(max_level_show)],
    columns=[f"稀有度{r}" for r in range(max_rarity_show)],
)
print(df_price.to_string())

# ========== 4. 稀有度分布表（完整 d=0~19）==========
dist_table = np.zeros((d_max + 1, show_rarity_dist))
for d in range(d_max + 1):
    probs = distributions[d][:show_rarity_dist]
    dist_table[d, : len(probs)] = probs

print("\n表2：不同钓鱼等级的稀有度分布（裁剪后）")
cols = [f"r={r}" for r in range(show_rarity_dist)]
df_dist = pd.DataFrame(
    dist_table, index=[f"d={d}" for d in range(d_max + 1)], columns=cols
)
print(df_dist.to_string(float_format="%.4f"))

# ========== 5. 验证期望收益 ==========
print("\n期望收益验证（使用取整后价格，鱼竿等级 x=1..10）")
for x in range(1, max_level_show + 1):
    revenues = []
    for n in range(1, x + 1):
        d = x - n
        # 使用取整后的 base_prices[n-1]
        base_int = base_prices[n - 1]
        exp_mult = M_d[d]
        exp_rev = base_int * exp_mult
        revenues.append((n, exp_rev))
    rev_str = " | ".join([f"关{n}:{rev:.2f}" for n, rev in revenues])
    diffs = [r[1] for r in revenues]
    max_diff = max(diffs) - min(diffs)
    rel = max_diff / np.mean(diffs) * 100
    print(f"x={x:2d}: {rev_str}  最大差异={max_diff:.2f} ({rel:.2f}%)")
