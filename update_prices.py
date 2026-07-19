"""
更新鱼的价格和钓竿价格
"""

import json
import math

MAX_STARS = 15

STAR_COLORS = {
    "gold": "★",
    "blue": "☆",
    "red": "✦",
}


def star_name(stars: int) -> str:
    if stars <= 5:
        return STAR_COLORS["gold"] * stars
    elif stars <= 10:
        blue_stars = stars - 5
        return STAR_COLORS["blue"] * blue_stars
    else:
        red_stars = stars - 10
        return STAR_COLORS["red"] * red_stars


def star_multiplier(stars: int) -> int:
    return 2 ** (stars - 1)


def normal_pdf(x: float, mean: float, std: float) -> float:
    return math.exp(-((x - mean) ** 2) / (2 * std**2)) / (std * math.sqrt(2 * math.pi))


def generate_distribution(expected_value: float, variance: float = 1.0) -> dict[int, float]:
    std = math.sqrt(variance)
    
    probs = {}
    for stars in range(1, MAX_STARS + 1):
        prob = normal_pdf(stars, expected_value, std)
        probs[stars] = prob
    
    total = sum(probs.values())
    if total > 0:
        for s in probs:
            probs[s] /= total
    
    return probs


def truncate_distribution(probs: dict[int, float], threshold: float = 0.05) -> dict[int, float]:
    truncated = {}
    accumulated = 0.0
    
    for stars in sorted(probs.keys()):
        prob = probs[stars]
        if prob >= threshold:
            truncated[stars] = prob
        else:
            accumulated += prob
    
    if accumulated > 0 and truncated:
        last_stars = max(truncated.keys())
        truncated[last_stars] += accumulated
    
    total = sum(truncated.values())
    if total > 0:
        for s in truncated:
            truncated[s] /= total
    
    return truncated


MANUAL_PROBABILITIES = {}

for level in range(11):
    expected_value = level * 0.4 + 1
    raw_probs = generate_distribution(expected_value, variance=0.2)
    truncated_probs = truncate_distribution(raw_probs, threshold=0.05)
    MANUAL_PROBABILITIES[level] = truncated_probs


def calculate_expected_multiplier(probs: dict[int, float]) -> float:
    return sum(probs[s] * star_multiplier(s) for s in probs)


def get_rarity_probabilities(rod_level: int, location_difficulty: int) -> dict[int, float]:
    effective_level = max(0, rod_level - location_difficulty)
    effective_level = min(effective_level, 10)
    return MANUAL_PROBABILITIES[effective_level].copy()


def calculate_base_prices():
    expected_multipliers = {}
    for level in range(11):
        probs = MANUAL_PROBABILITIES[level]
        expected_multipliers[level] = calculate_expected_multiplier(probs)
    
    base_income_lv1 = 13.8
    adjusted_base_prices = {}
    for rod_level in range(11):
        if rod_level == 0:
            target_income = base_income_lv1 * 0.8
        else:
            target_income = base_income_lv1 * rod_level
        
        expected_mult = expected_multipliers[rod_level]
        adjusted_base_price = target_income / expected_mult
        adjusted_base_prices[rod_level] = adjusted_base_price
    
    return adjusted_base_prices


def calculate_fibonacci_prices():
    fibonacci = [1, 2, 3, 5, 8, 13, 21, 34, 55]
    
    adjusted_base_prices = calculate_base_prices()
    
    prices = {}
    for i, days in enumerate(fibonacci):
        level = i + 1
        hours = days * 24
        
        probs = get_rarity_probabilities(level, 0)
        expected_mult = calculate_expected_multiplier(probs)
        base_price = adjusted_base_prices[level]
        income_per_hour = expected_mult * base_price
        
        rod_price = hours * income_per_hour
        prices[level + 1] = int(rod_price)
    
    return prices


def update_fish_prices():
    with open('config/fish.json', 'r', encoding='utf-8') as f:
        fish_data = json.load(f)
    
    with open('config/locations.json', 'r', encoding='utf-8') as f:
        location_data = json.load(f)
    
    adjusted_base_prices = calculate_base_prices()
    
    location_base_prices = {}
    for location in location_data['locations']:
        difficulty = location['difficulty']
        if difficulty <= 9:
            base_price = adjusted_base_prices.get(difficulty, adjusted_base_prices[10])
        else:
            base_price = adjusted_base_prices[10]
        location_base_prices[location['id']] = base_price
    
    fish_price_map = {}
    for location in location_data['locations']:
        location_id = location['id']
        base_price = location_base_prices[location_id]
        
        for fish_id in location['fish_pool']:
            fish_price_map[fish_id] = int(base_price)
    
    for fish in fish_data['fish']:
        fish_id = fish['id']
        if fish_id in fish_price_map:
            fish['base_price'] = fish_price_map[fish_id]
    
    with open('config/fish.json', 'w', encoding='utf-8') as f:
        json.dump(fish_data, f, ensure_ascii=False, indent=2)
    
    print("鱼的价格已更新！")
    print("\n【地点基础鱼价】")
    for location in location_data['locations']:
        location_id = location['id']
        base_price = location_base_prices[location_id]
        print(f"  {location['name']} (难度{location['difficulty']}): {base_price:.1f}鱼币")


def update_rod_prices():
    rod_prices = calculate_fibonacci_prices()
    
    print("\n【钓竿价格（斐波那契数列）】")
    fibonacci = [1, 2, 3, 5, 8, 13, 21, 34, 55]
    cumulative_days = 0
    for i, days in enumerate(fibonacci):
        level = i + 2
        cumulative_days += days
        price = rod_prices[level]
        print(f"  Lv.{level-1} → Lv.{level}: {days}天 (累计{cumulative_days}天) 价格: {price}鱼币")
    
    print(f"\n总升级时间: {cumulative_days}天 ({cumulative_days/30:.1f}个月)")
    
    with open('config/shop.json', 'r', encoding='utf-8') as f:
        shop_data = json.load(f)
    
    for level_str in shop_data['rod_upgrade_prices']:
        level = int(level_str)
        if level in rod_prices:
            shop_data['rod_upgrade_prices'][level_str] = rod_prices[level]
    
    shop_data['initial_gift']['rod_level'] = 1
    
    with open('config/shop.json', 'w', encoding='utf-8') as f:
        json.dump(shop_data, f, ensure_ascii=False, indent=2)
    
    print("\n钓竿价格已更新到shop.json！")
    print("初始鱼竿等级已设置为Lv.1！")


if __name__ == "__main__":
    update_fish_prices()
    update_rod_prices()
