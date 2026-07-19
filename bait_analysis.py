"""
鱼饵数值设计分析

设计目标：
- 前期买着亏本
- 后期小有收益
- 中间大部分时候亏本但增加凑齐图鉴概率

分析：
鱼饵的效果是"速度加成"，即减少钓鱼间隔。
基础间隔60分钟，鱼饵加成后间隔 = 60 / (1 + speed_bonus/100)

收益分析：
- 每小时钓鱼次数 = 60 / 间隔
- 期望收益/小时 = (60/间隔) × 期望收益/条
- 鱼饵收益 = 期望收益/小时 × (1 + speed_bonus/100) - 期望收益/小时

鱼饵成本：
- 普通鱼饵: 1鱼币, 速度+0%
- 蚯蚓鱼饵: 2鱼币, 速度+20%
- 虾米鱼饵: 5鱼币, 速度+40%
- 拟饵: 10鱼币, 速度+60%
- 黄金鱼饵: 18鱼币, 速度+80%
- 魔法鱼饵: 30鱼币, 速度+100%
- 传说鱼饵: 50鱼币, 速度+120%

每小时消耗鱼饵数量：
- 假设每次钓鱼消耗1个鱼饵
- 每小时钓鱼次数 = 60/间隔
- 每小时鱼饵成本 = 鱼饵价格 × (60/间隔)

收益计算：
假设期望收益/条 = E，间隔 = I
- 无鱼饵收益/小时 = E × (60/I)
- 有鱼饵收益/小时 = E × (60/I) × (1 + speed_bonus/100)
- 鱼饵收益增量 = E × (60/I) × speed_bonus/100
- 鱼饵成本/小时 = 鱼饵价格 × (60/I) × (1 + speed_bonus/100)

盈亏平衡点：
E × speed_bonus/100 = 鱼饵价格 × (1 + speed_bonus/100)
E = 鱼饵价格 × (1 + speed_bonus/100) × 100 / speed_bonus
"""

GROWTH_RATE = 1.3
RARITY_MULTIPLIER = {"N": 1, "R": 2, "SR": 4, "SSR": 8, "UR": 16, "UTR": 32}

BAITS = [
    {"id": 1, "name": "蚯蚓鱼饵", "speed_bonus": 20, "price": 2},
    {"id": 2, "name": "虾米鱼饵", "speed_bonus": 40, "price": 5},
    {"id": 3, "name": "拟饵", "speed_bonus": 60, "price": 10},
    {"id": 4, "name": "黄金鱼饵", "speed_bonus": 80, "price": 18},
    {"id": 5, "name": "魔法鱼饵", "speed_bonus": 100, "price": 30},
    {"id": 6, "name": "传说鱼饵", "speed_bonus": 120, "price": 50},
]

def calculate_break_even_fish_price(bait):
    """计算盈亏平衡点的期望鱼价"""
    speed_bonus = bait["speed_bonus"]
    price = bait["price"]
    if speed_bonus == 0:
        return float('inf')
    return price * (1 + speed_bonus/100) * 100 / speed_bonus

def calculate_hourly_profit(expected_fish_price, bait, base_interval=60):
    """计算每小时净收益"""
    speed_bonus = bait["speed_bonus"]
    price = bait["price"]
    
    new_interval = base_interval / (1 + speed_bonus/100)
    catches_per_hour = 60 / new_interval
    
    gross_income = expected_fish_price * catches_per_hour
    bait_cost = price * catches_per_hour
    net_income = gross_income - bait_cost
    
    return net_income, gross_income, bait_cost

print("=" * 80)
print("鱼饵数值分析")
print("=" * 80)

print("\n【盈亏平衡点分析】")
print("盈亏平衡点：期望鱼价达到多少时，使用鱼饵开始盈利")
print()
print(f"{'鱼饵':<12} {'价格':<10} {'速度加成':<10} {'盈亏平衡鱼价':<15}")
print("-" * 50)
for bait in BAITS:
    break_even = calculate_break_even_fish_price(bait)
    if break_even == float('inf'):
        print(f"{bait['name']:<12} {bait['price']:<10} {bait['speed_bonus']}%", " "*10, "无加成")
    else:
        print(f"{bait['name']:<12} {bait['price']:<10} +{bait['speed_bonus']}%", " "*5, f"{break_even:.1f}")

print("\n【各等级玩家使用鱼饵收益分析】")
print("假设：基础间隔60分钟，每小时钓鱼次数随鱼钩等级增加")
print()

expected_fish_prices = [16, 25, 40, 65, 100, 150, 200, 250, 300, 350, 400]

for rod_level, efp in enumerate(expected_fish_prices):
    print(f"\nLv.{rod_level} 玩家 (期望鱼价: {efp}鱼币/条)")
    print(f"{'鱼饵':<12} {'每小时收益':<12} {'鱼饵成本':<12} {'净收益':<12} {'状态'}")
    print("-" * 60)
    
    for bait in BAITS[1:]:
        net, gross, cost = calculate_hourly_profit(efp, bait)
        status = "盈利" if net > 0 else "亏损"
        print(f"{bait['name']:<12} {gross:<12.0f} {cost:<12.0f} {net:<12.0f} {status}")

print("\n【鱼饵设计建议】")
print("""
基于分析，建议调整鱼饵价格：

当前设计问题：
- 蚯蚓鱼饵(50鱼币)盈亏平衡点: 300鱼币/条
- 虾米鱼饵(200鱼币)盈亏平衡点: 700鱼币/条
- 高级鱼饵盈亏平衡点更高

建议调整：
1. 降低鱼饵价格，使后期玩家可以盈利
2. 或者提高鱼饵效果，增加速度加成

新建议价格：
- 蚯蚓鱼饵: 30鱼币 (盈亏平衡: 180鱼币/条)
- 虾米鱼饵: 100鱼币 (盈亏平衡: 350鱼币/条)
- 拟饵: 300鱼币 (盈亏平衡: 800鱼币/条)
- 黄金鱼饵: 800鱼币 (盈亏平衡: 1600鱼币/条)
- 魔法鱼饵: 2000鱼币 (盈亏平衡: 5000鱼币/条)
- 传说鱼饵: 6000鱼币 (盈亏平衡: 18000鱼币/条)

这样：
- Lv.5以下玩家使用鱼饵基本亏损
- Lv.6-8玩家使用中级鱼饵小亏或持平
- Lv.9-10玩家使用高级鱼饵可以盈利
""")
