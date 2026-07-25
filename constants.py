"""
游戏设计常量 — 不可变的游戏数值、稀有度表、概率分布、天气数据。

此处定义的所有数据都是游戏设计层面不可变的常量。
运行时配置（如 JSON 加载）保留在 config.py 中。
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 稀有度系统
# ═══════════════════════════════════════════════════════════════════════════════

RARITY_INDEX = {"N": 1, "R": 2, "SR": 3, "SSR": 4, "UR": 5, "UTR": 6}
INDEX_RARITY = {v: k for k, v in RARITY_INDEX.items()}

RARITY_MAP = {
    "n": "N",
    "r": "R",
    "sr": "SR",
    "ssr": "SSR",
    "ur": "UR",
    "utr": "UTR",
}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "UTR": 5}

RARITY_COLORS = {
    "N": "#808080",
    "R": "#4169E1",
    "SR": "#9932CC",
    "SSR": "#FFD700",
    "UR": "#FF4500",
    "UTR": "#FF1493",
}

RARITY_NAMES = {
    "N": "普通",
    "R": "稀有",
    "SR": "超稀有",
    "SSR": "超超稀有",
    "UR": "极稀有",
    "UTR": "传说",
}

RARITY_MIN_LEVEL = {
    "N": 1,
    "R": 1,
    "SR": 3,
    "SSR": 5,
    "UR": 8,
    "UTR": 999,
}

RARITY_MULTIPLIER = {
    "N": 1,
    "R": 2,
    "SR": 4,
    "SSR": 8,
    "UR": 16,
    "UTR": 32,
}

_RARITY_KEYS = ["N", "R", "SR", "SSR", "UR", "UTR"]

# ═══════════════════════════════════════════════════════════════════════════════
# 展示栏 / 猫框
# ═══════════════════════════════════════════════════════════════════════════════

DISPLAY_SLOT_COSTS = {4: 1, 5: 2, 6: 3, 7: 5, 8: 8, 9: 13, 10: 21}

UPGRADE_DISPLAY_COSTS = {
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5,
    6: 6, 7: 7, 8: 8, 9: 9, 10: 10,
}

# 星空展示框（建设星空艇后，用星空框升级；费用 1+2+…+10=55）
STARRY_FRAMES_MAX = 10
STARRY_FRAME_UPGRADE_COSTS = {
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5,
    6: 6, 7: 7, 8: 8, 9: 9, 10: 10,
}

CAT_EAT_CHANCE = 0.15
CAT_FRAME_PITY_THRESHOLD = 15
FRAME_PITY_THRESHOLD = 150
UTR_PITY_THRESHOLD = 150
STARRY_FISH_DROP_RATE = 0.05
# 鱼竿等级超过 10 后，每高 1 级额外 +0.5% 星空鱼掉落率（绝对加值）
STARRY_FISH_ROD_BONUS_THRESHOLD = 10
STARRY_FISH_ROD_BONUS_PER_LEVEL = 0.005
# 太阳风：掉落率 +2.5%（绝对加值，不与鱼竿加成相乘叠加）
STARRY_FISH_SOLAR_WIND_BONUS = 0.025

# ═══════════════════════════════════════════════════════════════════════════════
# 每日限制
# ═══════════════════════════════════════════════════════════════════════════════

DAILY_ACTION_LIMIT = 4
MAX_STATUS_PER_DAY = 3
DAILY_SELL_LIMIT = 3
DAILY_NEST_LIMIT = 2
DAILY_GIFT_LIMIT = 1

MAX_NEST_LAYERS = 10
MAX_FRAME_BUFF_LAYERS = 10

# ═══════════════════════════════════════════════════════════════════════════════
# 概率分布表（按 rod_level - location_difficulty 差值索引）
# ═══════════════════════════════════════════════════════════════════════════════

# 第 6 项及后续项会映射为 UTR，这些概率项仅为未来扩展稀有度体系预留。
# 当前星空钓鱼的实际抽选会在 core/engine.py 将 index >= 5 的质量截断并归并到 UR，
# 因此概率表本身的 UTR 当前不可达；这些预留项不可删除，也不可直接改写成 UR 概率。
RARITY_DISTRIBUTION: list[list[float]] = [
    [0.6655, 0.3345, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.4964, 0.4246, 0.0790, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.3153, 0.5039, 0.1808, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.1638, 0.4890, 0.3472, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0677, 0.3774, 0.4412, 0.1137, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.2335, 0.5101, 0.2564, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0291, 0.5209, 0.4000, 0.0500, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.1937, 0.6863, 0.1200, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.1638, 0.4890, 0.3472, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0677, 0.3774, 0.4412, 0.1137, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.2335, 0.5101, 0.2564, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.1085, 0.4426, 0.3785, 0.0704, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.3153, 0.5039, 0.1808, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.1638, 0.4890, 0.3472, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0677, 0.3774, 0.4412, 0.1137, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.2335, 0.5101, 0.2564, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.1085, 0.4426, 0.3785, 0.0704, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.3153, 0.5039, 0.1808, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.1638, 0.4890, 0.3472, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0677, 0.3774, 0.4412, 0.1137, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000],
]

# ═══════════════════════════════════════════════════════════════════════════════
# 天气系统
# ═══════════════════════════════════════════════════════════════════════════════

WEATHER_EMOJI = {
    "sunny": "☀️",
    "rain": "🌧️",
    "meteor": "🌠",
    "storm": "⛈️",
    "lost_wind": "🌀",
    "cat": "🐱",
    "solar_wind": "🌬️",
    "meteor_shower": "💫",
    "hengjiyuan": "🏛️",
    "chaotic_era": "🌫️",
}

WEATHER_NAME = {
    "sunny": "晴天",
    "rain": "雨天",
    "meteor": "流星",
    "storm": "暴雨",
    "lost_wind": "迷途风",
    "cat": "猫！",
    "solar_wind": "太阳风",
    "meteor_shower": "流星雨",
    "hengjiyuan": "恒纪元",
    "chaotic_era": "乱纪元",
}

WEATHER_EFFECT_DESC = {
    "sunny": "",
    "rain": "上鱼速度+10%",
    "meteor": "最高稀有度+2%",
    "storm": "鱼饵消耗减半",
    "lost_wind": "有概率UTR",
    "cat": "随机吃鱼！",
    "solar_wind": "流星鱼出现率+2.5%",
    "meteor_shower": "星空鱼变得幸运",
    "hengjiyuan": "流星鱼数字限定为2-8",
    "chaotic_era": "",
}

# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def normalize_fish_numeric_id(numeric_id: str | int | None) -> str:
    """统一鱼编号格式；猫猫乐园鱼使用小写 s1 前缀。"""
    if numeric_id is None:
        return ""
    numeric_id = str(numeric_id).strip()
    if len(numeric_id) == 4 and numeric_id.startswith("-1") and numeric_id[2:].isdigit():
        return f"s1{numeric_id[2:]}"
    if len(numeric_id) == 4 and numeric_id[:2].lower() == "s1" and numeric_id[2:].isdigit():
        return f"s1{numeric_id[2:]}"
    return numeric_id


def generate_fish_numeric_id(location_id: str, fish_index: int, rarity: str) -> str:
    """根据钓场、鱼索引、稀有度生成鱼的编号。"""
    if location_id.upper() == "S1":
        loc_num = "s1"
    else:
        loc_num = int(location_id) if location_id.isdigit() else 1
    rarity_num = RARITY_INDEX.get(rarity, 1)
    return f"{loc_num}{fish_index}{rarity_num}"


def calculate_fish_price(
    fish: "FishData", rarity: str, location_difficulty: int = 0
) -> int:
    """根据鱼的基础价格和稀有度计算实际价格。"""
    multiplier = RARITY_MULTIPLIER.get(rarity, 1)
    return int(fish.base_price * multiplier)


def get_rarity_probabilities_full(
    rod_level: int, location_difficulty: int
) -> list[float]:
    """获取完整的稀有度概率数组（含扩展位）。"""
    d = rod_level - location_difficulty
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    return list(RARITY_DISTRIBUTION[d])


def get_lost_wind_utr_probability(rod_level: int, location_difficulty: int) -> float:
    """迷途风 UTR 概率：基础 0.2%，鱼竿每领先场景等级 1 级 +0.1%。"""
    location_level = location_difficulty + 1
    lead = max(0, rod_level - location_level)
    return 0.002 + lead * 0.001


def get_rarity_probabilities(
    rod_level: int, location_difficulty: int
) -> dict[str, float]:
    """获取 6 个稀有度的概率分布字典。"""
    probs = get_rarity_probabilities_full(rod_level, location_difficulty)
    result: dict[str, float] = {}
    for i, key in enumerate(_RARITY_KEYS):
        if i < len(_RARITY_KEYS) - 1:
            result[key] = probs[i]
        else:
            result[key] = sum(probs[i:])
    return result


def get_display_probabilities(
    rod_level: int,
    location_difficulty: int,
    duoduo_count: int = 0,
    max_rarity: str = "UR",
) -> dict[str, float]:
    """获取用于展示的概率分布（含多多翻倍、稀有度封顶）。"""
    probs = get_rarity_probabilities_full(rod_level, location_difficulty)
    order = ["N", "R", "SR", "SSR", "UR", "UTR"]
    max_idx = order.index(max_rarity) if max_rarity in order else len(order) - 1

    quantity_mult = 1 << duoduo_count

    display = [0.0] * len(order)
    for r, p in enumerate(probs):
        if p <= 0:
            continue
        capped_r = min(r, max_idx)
        display[capped_r] += p * quantity_mult

    result: dict[str, float] = {}
    for i, key in enumerate(order):
        result[key] = display[i]
    return result


def apply_meteor_effect(probabilities: list[float], bonus: float = 2) -> list[float]:
    """流星天气：将最高非零稀有度概率提升 bonus%，降低次高稀有度概率。"""
    bonus = bonus / 100.0
    result = list(probabilities)
    top_idx = -1
    for i in range(len(result) - 1, -1, -1):
        if result[i] > 0:
            top_idx = i
            break
    if top_idx <= 0:
        return result
    lower_idx = top_idx - 1
    # 只能转移次高稀有度实际拥有的概率质量，绝不产生负概率或凭空增量。
    transferred = min(bonus, max(0.0, result[lower_idx]))
    result[top_idx] += transferred
    result[lower_idx] -= transferred
    return result


def get_meteor_adjusted_probabilities(
    rod_level: int, location_difficulty: int, weather_luck_boost: float
) -> dict[str, float]:
    """流星天气调整后的稀有度概率分布。"""
    raw_probs = get_rarity_probabilities_full(rod_level, location_difficulty)
    modified_probs = apply_meteor_effect(raw_probs, weather_luck_boost)
    prob_dict: dict[str, float] = {}
    for i, key in enumerate(_RARITY_KEYS):
        if i < len(_RARITY_KEYS) - 1:
            prob_dict[key] = modified_probs[i] if i < len(modified_probs) else 0
        else:
            prob_dict[key] = sum(modified_probs[i:]) if i < len(modified_probs) else 0
    return prob_dict
