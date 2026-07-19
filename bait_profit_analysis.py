import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config"

RARITY_MIN_LEVEL = {
    "N": 1,
    "R": 1,
    "SR": 3,
    "SSR": 5,
    "UR": 8,
    "UTR": 10,
}

RARITY_MULTIPLIER = {
    "N": 1,
    "R": 2,
    "SR": 3,
    "SSR": 4,
    "UR": 5,
    "UTR": 6,
}


def get_rarity_probabilities(rod_level: int, location_difficulty: int) -> dict[str, float]:
    effective_level = max(1, rod_level - location_difficulty)

    base_probs = {
        "N": 80.0,
        "R": 15.0,
        "SR": 3.5,
        "SSR": 1.0,
        "UR": 0.4,
        "UTR": 0.1,
    }

    for rarity, min_level in RARITY_MIN_LEVEL.items():
        if effective_level < min_level:
            base_probs[rarity] = 0.0

    for _ in range(effective_level - 1):
        transfer = base_probs["N"] * 0.05
        base_probs["N"] -= transfer

        transfer_r = transfer * 0.6
        transfer_sr = transfer * 0.25
        transfer_ssr = transfer * 0.1
        transfer_ur = transfer * 0.04
        transfer_utr = transfer * 0.01

        if effective_level >= RARITY_MIN_LEVEL["R"]:
            base_probs["R"] += transfer_r
        else:
            base_probs["N"] += transfer_r

        if effective_level >= RARITY_MIN_LEVEL["SR"]:
            base_probs["SR"] += transfer_sr
        else:
            base_probs["N"] += transfer_sr

        if effective_level >= RARITY_MIN_LEVEL["SSR"]:
            base_probs["SSR"] += transfer_ssr
        else:
            base_probs["N"] += transfer_ssr

        if effective_level >= RARITY_MIN_LEVEL["UR"]:
            base_probs["UR"] += transfer_ur
        else:
            base_probs["N"] += transfer_ur

        if effective_level >= RARITY_MIN_LEVEL["UTR"]:
            base_probs["UTR"] += transfer_utr
        else:
            base_probs["N"] += transfer_utr

    base_probs["N"] = max(5.0, base_probs.get("N", 0))

    return base_probs


def calculate_fish_price(base_price: int, rarity: str, location_difficulty: int) -> int:
    multiplier = RARITY_MULTIPLIER.get(rarity, 1)
    difficulty_bonus = 1 + location_difficulty * 0.1
    return int(base_price * multiplier * difficulty_bonus)


def load_json(filename: str) -> dict:
    with open(CONFIG_PATH / filename, encoding="utf-8") as f:
        return json.load(f)


def calculate_expected_fish_value(
    fish_pool: list[str],
    fish_data: dict[str, dict],
    rod_level: int,
    location_difficulty: int
) -> float:
    probabilities = get_rarity_probabilities(rod_level, location_difficulty)
    total_prob = sum(probabilities.values())
    
    expected_value = 0.0
    
    for fish_id in fish_pool:
        fish = fish_data.get(fish_id)
        if not fish:
            continue
        
        base_price = fish["base_price"]
        
        for rarity, prob in probabilities.items():
            if prob > 0:
                price = calculate_fish_price(base_price, rarity, location_difficulty)
                expected_value += (prob / total_prob) * price
    
    return expected_value


def main():
    fish_json = load_json("fish.json")
    locations_json = load_json("locations.json")
    shop_json = load_json("shop.json")
    
    fish_data = {f["id"]: f for f in fish_json["fish"]}
    
    baits = shop_json["baits"]
    basic_bait = baits[0]
    
    print("=" * 80)
    print("钓鱼插件 - 高级鱼饵收益分析报告")
    print("=" * 80)
    
    print("\n【一、鱼饵基本信息】")
    print("-" * 80)
    print(f"{'鱼饵名称':<12} {'钓鱼间隔':<12} {'购买价格':<12} {'单价(每条)':<12} {'效率倍率'}")
    print("-" * 80)
    
    for bait in baits:
        price_per_fish = bait["price"] / 10
        efficiency = basic_bait["interval"] / bait["interval"]
        print(f"{bait['name']:<12} {bait['interval']}分钟{'':<6} {bait['price']}金币{'':<6} {price_per_fish:.1f}金币{'':<6} {efficiency:.2f}x")
    
    print("\n" + "=" * 80)
    print("【二、各钓鱼地点期望鱼价】")
    print("=" * 80)
    print("(期望鱼价 = 考虑稀有度概率后的平均鱼价值)")
    print()
    
    rod_levels = [1, 3, 5, 7, 10]
    
    print(f"{'地点名称':<16} {'难度':<6}", end="")
    for level in rod_levels:
        print(f"Lv.{level:<10}", end="")
    print()
    print("-" * 80)
    
    for location in locations_json["locations"]:
        print(f"{location['name']:<16} {location['difficulty']:<6}", end="")
        for rod_level in rod_levels:
            expected_value = calculate_expected_fish_value(
                location["fish_pool"],
                fish_data,
                rod_level,
                location["difficulty"]
            )
            print(f"{expected_value:<12.1f}", end="")
        print()
    
    print("\n" + "=" * 80)
    print("【三、鱼饵收益临界点分析】")
    print("=" * 80)
    print("""
收益临界点说明:
- 临界时间: 使用高级鱼饵后，需要钓鱼多少分钟才能弥补额外成本
- 如果钓鱼时间 > 临界时间，则使用高级鱼饵有收益
- 如果钓鱼时间 < 临界时间，则使用普通鱼饵更划算
    """)
    
    results = []
    
    for location in locations_json["locations"]:
        for rod_level in [1, 3, 5, 7, 10]:
            expected_value = calculate_expected_fish_value(
                location["fish_pool"],
                fish_data,
                rod_level,
                location["difficulty"]
            )
            
            if expected_value <= 0:
                continue
            
            for bait in baits[1:]:
                price_per_fish = bait["price"] / 10
                basic_price_per_fish = basic_bait["price"] / 10
                
                efficiency_ratio = basic_bait["interval"] / bait["interval"]
                
                extra_cost = price_per_fish - basic_price_per_fish
                
                extra_fish_per_hour = (60 / bait["interval"]) - (60 / basic_bait["interval"])
                
                if extra_fish_per_hour <= 0:
                    continue
                
                break_even_fish = extra_cost / expected_value
                break_even_minutes = break_even_fish / extra_fish_per_hour * 60
                
                results.append({
                    "location": location["name"],
                    "difficulty": location["difficulty"],
                    "rod_level": rod_level,
                    "bait": bait["name"],
                    "expected_value": expected_value,
                    "break_even_minutes": break_even_minutes,
                    "break_even_fish": break_even_fish,
                })
    
    print("\n【各鱼饵推荐使用场景】")
    print("-" * 80)
    
    for bait in baits[1:]:
        print(f"\n>>> {bait['name']} (价格: {bait['price']}金币/10个)")
        print(f"    钓鱼间隔: {bait['interval']}分钟, 效率: {basic_bait['interval']/bait['interval']:.1f}倍")
        
        bait_results = [r for r in results if r["bait"] == bait["name"]]
        
        min_break_even = min(r["break_even_minutes"] for r in bait_results)
        max_break_even = max(r["break_even_minutes"] for r in bait_results)
        avg_break_even = sum(r["break_even_minutes"] for r in bait_results) / len(bait_results)
        
        print(f"    临界时间范围: {min_break_even:.1f} ~ {max_break_even:.1f} 分钟")
        print(f"    平均临界时间: {avg_break_even:.1f} 分钟")
        
        if avg_break_even < 5:
            print("    >>> 推荐程度: ★★★★★ 极力推荐")
            print("    >>> 只要钓鱼超过5分钟就有收益，几乎任何情况都值得使用!")
        elif avg_break_even < 15:
            print("    >>> 推荐程度: ★★★★☆ 强烈推荐")
            print("    >>> 钓鱼15分钟内即可回本，大多数情况都值得使用!")
        elif avg_break_even < 30:
            print("    >>> 推荐程度: ★★★☆☆ 推荐")
            print("    >>> 钓鱼30分钟内可回本，适合中等时长钓鱼!")
        elif avg_break_even < 60:
            print("    >>> 推荐程度: ★★☆☆☆ 谨慎使用")
            print("    >>> 需要钓鱼1小时才能回本，建议长时间钓鱼时使用!")
        elif avg_break_even < 120:
            print("    >>> 推荐程度: ★☆☆☆☆ 不太推荐")
            print("    >>> 需要钓鱼2小时才能回本，仅适合长时间挂机!")
        else:
            print("    >>> 推荐程度: ☆☆☆☆☆ 不推荐")
            print("    >>> 回本时间太长，不建议使用!")
    
    print("\n" + "=" * 80)
    print("【四、详细临界时间表】")
    print("=" * 80)
    print("\n按地点和鱼竿等级分类:")
    
    for location in locations_json["locations"]:
        print(f"\n{location['name']} (难度{location['difficulty']}):")
        print(f"{'鱼竿等级':<10}", end="")
        for bait in baits[1:]:
            print(f"{bait['name'][:6]:<10}", end="")
        print()
        print("-" * 70)
        
        for rod_level in [1, 3, 5, 7, 10]:
            print(f"Lv.{rod_level:<7}", end="")
            for bait in baits[1:]:
                expected_value = calculate_expected_fish_value(
                    location["fish_pool"],
                    fish_data,
                    rod_level,
                    location["difficulty"]
                )
                
                price_per_fish = bait["price"] / 10
                basic_price_per_fish = basic_bait["price"] / 10
                extra_cost = price_per_fish - basic_price_per_fish
                extra_fish_per_hour = (60 / bait["interval"]) - (60 / basic_bait["interval"])
                
                if extra_fish_per_hour > 0 and expected_value > 0:
                    break_even_minutes = (extra_cost / expected_value) / extra_fish_per_hour * 60
                    print(f"{break_even_minutes:<10.1f}", end="")
                else:
                    print(f"{'N/A':<10}", end="")
            print()
    
    print("\n" + "=" * 80)
    print("【五、总结与建议】")
    print("=" * 80)
    print("""
【新手阶段 (鱼竿Lv.1-2)】
1. 蚯蚓鱼饵: ✅ 强烈推荐 - 临界时间极短，立即可获得收益
2. 虾米鱼饵: ✅ 推荐 - 在乡间浅溪等低难度地点即可回本
3. 拟饵及以上: ⚠️ 需谨慎 - 建议在田园池塘或更高难度地点使用

【中期阶段 (鱼竿Lv.3-5)】
1. 蚯蚓鱼饵: ✅ 极力推荐 - 任何地点都有收益
2. 虾米鱼饵: ✅ 强烈推荐 - 所有地点都有收益
3. 拟饵: ✅ 推荐 - 在平缓内河及以上地点有收益
4. 黄金鱼饵: ⚠️ 需谨慎 - 建议在宽阔大湖及以上地点使用

【后期阶段 (鱼竿Lv.6-8)】
1. 蚯蚓鱼饵: ✅ 极力推荐
2. 虾米鱼饵: ✅ 极力推荐
3. 拟饵: ✅ 强烈推荐
4. 黄金鱼饵: ✅ 推荐 - 在山泉深潭及以上地点有收益
5. 魔法鱼饵: ⚠️ 需谨慎 - 建议在大江中游及以上地点使用

【终极阶段 (鱼竿Lv.9-10)】
1. 所有鱼饵在古河道都有极高收益
2. 传说鱼饵仅在古河道+满级鱼竿时值得考虑
3. 高级鱼饵的效率优势在后期更加明显

【关键结论】
- 鱼饵的收益主要取决于: 地点难度 + 鱼竿等级 + 钓鱼时长
- 地点难度越高，鱼的期望价值越高，高级鱼饵越划算
- 鱼竿等级越高，稀有鱼概率越高，高级鱼饵越划算
- 钓鱼时间越长，高级鱼饵的效率优势越明显
    """)


if __name__ == "__main__":
    main()
