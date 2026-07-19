from __future__ import annotations

import math
from dataclasses import dataclass

C = 2.0
S = 0.4
SIGMA = 0.8
THETA = 0.05
BASE_1 = 10.0
ANCHOR_LEVEL = 10
ANCHOR_BASE = (
    118.0  # first-part final-map average base price, used only as extension anchor
)
RARITY_CAP = 4  # UR cap for economy simulation
BASE_INTERVAL_MINUTES = 60
HOOK_SPEED_BONUS = 1.0  # max hook: +100%
BAIT_SPEED_BONUS = 1.2  # max bait: +120%
NEST_SPEED_BONUS = 0.7  # default nest: +70%
BAIT_COST = 50
TARGET_DAYS = 7.0

STAR_MAP_NAMES = [
    "牛奶河",
    "月环港",
    "彗尾瀑",
    "星砂漠",
    "云鲸庭",
    "极光井",
    "黑洞涡",
    "水晶星冠",
    "时钟星湖",
    "奇迹彼岸",
]

STAR_FISH_NAMES = [
    ["月乳鲫", "银匙鳐", "星沫鳗", "奶冠鲤", "银河灯鱼"],
    ["月壳蟹鱼", "潮汐银鲈", "环月飞鱼", "玉兔灯鲷", "灰晶鳕"],
    ["彗尾鲑", "焰尘鳟", "长尾星鳅", "白火鲢", "碎冰虹鱼"],
    ["沙星魟", "琉璃沙鳗", "星蝎鲶", "金尘鲷", "海市蜃鱼"],
    ["云须鲸鱼", "鲸歌鲤", "浮庭鲫", "天羽鳐", "雾铃鳕"],
    ["极光鳗", "虹幕鲑", "井心灯鱼", "绿辉鲈", "磁光鳟"],
    ["引力鲶", "暗环魟", "奇点鳕", "坠星鳗", "潮汐黑鲤"],
    ["晶冠鲷", "棱镜鲫", "星核金鱼", "蓝晶鳟", "冠冕灯鲈"],
    ["秒针鲑", "回环鳗", "逆刻鲤", "钟摆鲈", "永昼银鱼"],
    ["奇迹锦鲤", "终星鳐", "愿核灯鱼", "彼岸银鲑", "九曜梦鱼"],
]


@dataclass(frozen=True)
class MapRow:
    location_id: int
    name: str
    difficulty: int
    avg_base: int
    fish_prices: list[int]
    expected_value_d0: float
    daily_net_d0: float
    upgrade_price: int


def raw_distribution(d: int, max_r: int = 20) -> list[float]:
    mu = S * d
    weights = [math.exp(-((r - mu) ** 2) / (2 * SIGMA**2)) for r in range(max_r + 1)]
    total = sum(weights)
    return [w / total for w in weights]


def truncated_distribution(d: int, max_r: int = 20) -> list[float]:
    probs = raw_distribution(d, max_r)
    kept = [p if p >= THETA else 0.0 for p in probs]
    for i, p in enumerate(probs):
        if p >= THETA:
            continue
        kept_indices = [j for j, q in enumerate(kept) if q > 0]
        nearest = min(kept_indices, key=lambda j: (abs(j - i), j))
        kept[nearest] += p
    total = sum(kept)
    return [p / total for p in kept]


def expected_multiplier(d: int, cap: int = RARITY_CAP) -> float:
    return sum(p * (C ** min(r, cap)) for r, p in enumerate(truncated_distribution(d)))


def fit_growth_ratio(max_d: int = 19) -> float:
    xs = list(range(max_d + 1))
    ys = [math.log(expected_multiplier(d)) for d in xs]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    beta = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / sum(
        (x - x_mean) ** 2 for x in xs
    )
    return math.exp(beta)


def catches_per_day() -> float:
    speed = (1 + HOOK_SPEED_BONUS) * (1 + BAIT_SPEED_BONUS) * (1 + NEST_SPEED_BONUS)
    interval = BASE_INTERVAL_MINUTES / speed
    return 24 * 60 / interval


def daily_net(avg_base: float, rod_level: int, difficulty: int) -> float:
    gross = (
        avg_base
        * expected_multiplier(max(0, rod_level - difficulty))
        * catches_per_day()
    )
    bait_cost = BAIT_COST * catches_per_day()
    return gross - bait_cost


def generate_maps(target_total_days: float = 70.0) -> list[MapRow]:
    ratio = fit_growth_ratio()
    base_prices = [
        round(ANCHOR_BASE * (ratio ** (n - ANCHOR_LEVEL))) for n in range(1, 21)
    ]
    multipliers = [0.96, 1.04, 1.00, 0.98, 1.02]  # 极差<=10%约束: max/min=1.083

    rows: list[MapRow] = []
    for idx in range(10):
        location_id = 11 + idx
        difficulty = 10 + idx
        avg_base = base_prices[location_id - 1]
        fish_prices = [round(avg_base * m) for m in multipliers]
        avg_actual = sum(fish_prices) / len(fish_prices)
        net = daily_net(avg_actual, difficulty, difficulty)
        upgrade_price = round(net * target_total_days / 10)
        rows.append(
            MapRow(
                location_id=location_id,
                name=STAR_MAP_NAMES[idx],
                difficulty=difficulty,
                avg_base=avg_base,
                fish_prices=fish_prices,
                expected_value_d0=avg_actual * expected_multiplier(0),
                daily_net_d0=net,
                upgrade_price=upgrade_price,
            )
        )
    return rows


def simulate(
    rows: list[MapRow], rod_buff: int = 0, include_final_upgrade: bool = True
) -> tuple[float, list[tuple[int, int, int, float, float]]]:
    total_days = 0.0
    detail = []
    count = 10 if include_final_upgrade else 9
    for idx, row in enumerate(rows[:count]):
        rod_level = 10 + idx
        avg_base = sum(row.fish_prices) / len(row.fish_prices)
        net = daily_net(avg_base, rod_level + rod_buff, row.difficulty)
        days = row.upgrade_price / net
        total_days += days
        detail.append((rod_level, rod_level + 1, row.location_id, net, days))
    return total_days, detail


def print_report(rows: list[MapRow]) -> None:
    print(f"growth_ratio={fit_growth_ratio():.6f}")
    print(f"catches_per_day={catches_per_day():.2f}")
    print("\nMAPS")
    for row in rows:
        print(
            f"{row.location_id} {row.name} diff={row.difficulty} "
            f"avg={row.avg_base} fish={row.fish_prices} "
            f"E0={row.expected_value_d0:.1f} net={row.daily_net_d0:.0f} price={row.upgrade_price}"
        )
    for include_final in (False, True):
        label = "10 upgrades" if include_final else "9 unlock upgrades"
        for buff in (0, 1):
            days, detail = simulate(
                rows, rod_buff=buff, include_final_upgrade=include_final
            )
            print(f"\nSIM {label} buff={buff} total_days={days:.2f}")
            for from_level, to_level, location_id, net, step_days in detail:
                print(
                    f"  Lv.{from_level}->{to_level} at map {location_id}: net={net:.0f}/day days={step_days:.2f}"
                )


if __name__ == "__main__":
    print_report(generate_maps())
