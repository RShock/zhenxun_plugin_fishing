import json
import random
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"

RARITY_DISTRIBUTION = [
    [0.6655, 0.3345, 0.0000, 0.0000, 0.0000, 0.0000],
    [0.4964, 0.4246, 0.0790, 0.0000, 0.0000, 0.0000],
    [0.3153, 0.5039, 0.1808, 0.0000, 0.0000, 0.0000],
    [0.1638, 0.4890, 0.3472, 0.0000, 0.0000, 0.0000],
    [0.0677, 0.3774, 0.4412, 0.1137, 0.0000, 0.0000],
    [0.0000, 0.2335, 0.5101, 0.2564, 0.0000, 0.0000],
    [0.0000, 0.1085, 0.4426, 0.3785, 0.0704, 0.0000],
    [0.0000, 0.0000, 0.3153, 0.5039, 0.1808, 0.0000],
    [0.0000, 0.0000, 0.1638, 0.4890, 0.3472, 0.0000],
    [0.0000, 0.0000, 0.0677, 0.3774, 0.4412, 0.1137],
    [0.0000, 0.0000, 0.0000, 0.2335, 0.5101, 0.2564],
    [0.0000, 0.0000, 0.0000, 0.1085, 0.4426, 0.3785],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.3153, 0.6847],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.1638, 0.8362],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0677, 0.9323],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],
]
_RARITY_KEYS = ["N", "R", "SR", "SSR", "UR", "UTR"]
_RARITY_MULTIPLIER = {"N": 1, "R": 2, "SR": 4, "SSR": 8, "UR": 16, "UTR": 32}
_MAX_RARITY_INDEX = 3

LOCATION_DATA = [
    (
        "1",
        "乡间浅溪",
        0,
        ["小鲫鱼", "麦穗鱼", "白条鱼", "鳑鲏鱼", "泥鳅"],
        [9, 11, 10, 9, 11],
    ),
    (
        "2",
        "田园池塘",
        1,
        ["草鱼", "鲤鱼", "鲢鱼", "鳙鱼", "黄鳝"],
        [12, 14, 13, 12, 14],
    ),
    (
        "3",
        "平缓内河",
        2,
        ["翘嘴鲌", "鲶鱼", "土凤鱼", "黑鱼", "黄颡鱼"],
        [15, 19, 17, 16, 18],
    ),
    (
        "4",
        "宽阔大湖",
        3,
        ["青鱼", "鳊鱼", "赤眼鳟", "银鱼", "花鲢"],
        [21, 25, 23, 22, 24],
    ),
    (
        "5",
        "山泉深潭",
        4,
        ["马口鱼", "石斑鱼", "光唇鱼", "宽鳍鱲", "小银鲫"],
        [27, 33, 30, 28, 32],
    ),
    (
        "6",
        "芦苇浅荡",
        5,
        ["革胡子鲶", "麦鲮鱼", "泰鲮鱼", "罗非鱼", "食蚊鱼"],
        [35, 43, 39, 37, 41],
    ),
    (
        "7",
        "大江中游",
        6,
        ["江团鱼", "刀鲚", "黄尾鲴", "细鳞鱼", "重唇鱼"],
        [47, 57, 52, 49, 55],
    ),
    (
        "8",
        "河口交汇",
        7,
        ["海鲈", "鲻鱼", "梭鱼", "弹涂鱼", "小海鳗"],
        [61, 75, 68, 64, 72],
    ),
    (
        "9",
        "高山冷湖",
        8,
        ["虹鳟鱼", "金鳟鱼", "柳根鱼", "高原鳅", "细鳞鲑"],
        [80, 98, 89, 84, 94],
    ),
    (
        "10",
        "原生古河",
        9,
        ["胭脂鱼", "斑鳜", "大眼鳜", "长吻鮠", "乌苏里拟鲿"],
        [106, 130, 118, 112, 124],
    ),
]

FRAME_DROP_RATE = 0.007
FRAME_PITY = 150


def load_shop_data() -> dict:
    with open(CONFIG_DIR / "shop.json", encoding="utf-8") as f:
        return json.load(f)


def load_fish_data() -> dict:
    with open(CONFIG_DIR / "fish.json", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class LocationData:
    id: str
    name: str
    difficulty: int
    fish_pool: list[str]
    fish_prices: list[int]


@dataclass
class FishData:
    id: str
    base_price: int


@dataclass
class DisplaySlot:
    fish_name: str
    rarity: str
    daily_income: int


@dataclass
class PlayerState:
    gold: int = 0
    rod_level: int = 0
    hook_level: int = 0
    bait_id: int = 0
    bait_count: int = 0
    total_fish_caught: int = 0
    total_gold_earned: int = 0
    total_bait_spent: int = 0
    fishing_hours: float = 0.0
    display_slots_count: int = 3
    display_frames: int = 0
    display: list[DisplaySlot] = field(default_factory=list)
    collection: dict[str, set[str]] = field(default_factory=dict)
    completed_achievements: set[str] = field(default_factory=set)
    achievement_gold: int = 0
    display_gold: int = 0
    frame_pity_counter: int = 0

    def get_bait_info(self, baits: list[dict]) -> dict:
        for b in baits:
            if b["id"] == self.bait_id:
                return b
        return {"id": 0, "name": "无饵", "speed_bonus": 0, "price": 0}

    def get_fishing_interval(
        self, baits: list[dict], base_interval: int, hook_speed_per_level: int
    ) -> float:
        bait_info = self.get_bait_info(baits)
        hook_multiplier = 1 + self.hook_level * hook_speed_per_level / 100
        bait_multiplier = 1 + bait_info["speed_bonus"] / 100
        return base_interval / (hook_multiplier * bait_multiplier)

    def get_display_income(self) -> int:
        return sum(s.daily_income for s in self.display)

    def update_display(self, caught_fish: list[tuple[FishData, str, int]]):
        displayed_keys = {(s.fish_name, s.rarity) for s in self.display}
        for fish, rarity, price in caught_fish:
            if fish.id == "展示木框":
                continue
            key = (fish.id, rarity)
            if key in displayed_keys:
                continue
            income = fish.base_price * _RARITY_MULTIPLIER.get(rarity, 1) * 2
            if len(self.display) < self.display_slots_count:
                self.display.append(DisplaySlot(fish.id, rarity, income))
                displayed_keys.add(key)
            else:
                min_income = min(s.daily_income for s in self.display)
                if income > min_income:
                    min_idx = next(
                        i
                        for i, s in enumerate(self.display)
                        if s.daily_income == min_income
                    )
                    replaced_key = (
                        self.display[min_idx].fish_name,
                        self.display[min_idx].rarity,
                    )
                    self.display[min_idx] = DisplaySlot(fish.id, rarity, income)
                    displayed_keys.discard(replaced_key)
                    displayed_keys.add(key)

    def try_expand_display(self):
        next_slot = self.display_slots_count + 1
        if next_slot > 10:
            return False
        display_slot_costs = {4: 1, 5: 2, 6: 3, 7: 5, 8: 8, 9: 13, 10: 21}
        frames_needed = display_slot_costs.get(next_slot, next_slot - 3)
        if self.display_frames >= frames_needed:
            self.display_frames -= frames_needed
            self.display_slots_count = next_slot
            return True
        return False


def get_rarity_probabilities(
    rod_level: int, location_difficulty: int
) -> dict[str, float]:
    d = rod_level - location_difficulty
    d = max(0, min(d, len(RARITY_DISTRIBUTION) - 1))
    probs = RARITY_DISTRIBUTION[d]
    return {_RARITY_KEYS[i]: probs[i] for i in range(6)}


def cap_rarity(rarity: str, max_index: int = _MAX_RARITY_INDEX) -> str:
    idx = _RARITY_KEYS.index(rarity)
    if idx > max_index:
        return _RARITY_KEYS[max_index]
    return rarity


def calculate_fish_price(base_price: int, rarity: str) -> int:
    multiplier = _RARITY_MULTIPLIER.get(rarity, 1)
    return base_price * multiplier


def calculate_expected_income(rod_level: int, location: LocationData) -> float:
    probs = get_rarity_probabilities(rod_level, location.difficulty)
    avg_base_price = sum(location.fish_prices) / len(location.fish_prices)
    expected_value = 0.0
    for rarity, prob in probs.items():
        capped = cap_rarity(rarity)
        expected_value += prob * calculate_fish_price(avg_base_price, capped)
    return expected_value


class FishingSimulation:
    def __init__(self):
        self.shop = load_shop_data()
        self.fish_json = load_fish_data()
        self.locations = self._create_locations()
        self.fish_dict = self._create_fish_dict()
        self.rod_prices = {
            int(k): v for k, v in self.shop["rod_upgrade_prices"].items()
        }
        self.hook_prices = {
            int(k): v for k, v in self.shop["hook_upgrade_prices"].items()
        }
        self.rod_names = {int(k): v for k, v in self.shop["rod_names"].items()}
        self.baits = self.shop["baits"]
        self.base_interval = self.shop.get("base_fishing_interval", 60)
        self.hook_speed_per_level = self.shop.get("hook_speed_bonus_per_level", 10)

    def _create_locations(self) -> list[LocationData]:
        return [
            LocationData(id, name, difficulty, fish_pool, fish_prices)
            for id, name, difficulty, fish_pool, fish_prices in LOCATION_DATA
        ]

    def _create_fish_dict(self) -> dict[str, FishData]:
        fish_dict = {}
        for loc in self.locations:
            for name, price in zip(loc.fish_pool, loc.fish_prices):
                fish_dict[name] = FishData(name, price)
        return fish_dict

    def catch_fish(
        self, player: PlayerState, location: LocationData
    ) -> tuple[FishData, str, int]:
        player.frame_pity_counter += 1
        if random.random() < FRAME_DROP_RATE or player.frame_pity_counter >= FRAME_PITY:
            frame_fish = FishData(id="展示木框", base_price=0)
            player.frame_pity_counter = 0
            return frame_fish, "UTR", 0

        probs = get_rarity_probabilities(player.rod_level, location.difficulty)
        all_rarities = ["N", "R", "SR", "SSR", "UR", "UTR"]
        available = {r: probs.get(r, 0) for r in all_rarities}
        total = sum(available.values())
        rand = random.random() * total
        cumulative = 0
        selected_rarity = "N"
        for r in all_rarities:
            cumulative += available[r]
            if rand <= cumulative:
                selected_rarity = r
                break
        selected_rarity = cap_rarity(selected_rarity)
        fish_name = random.choice(location.fish_pool)
        fish = self.fish_dict[fish_name]
        price = calculate_fish_price(fish.base_price, selected_rarity)
        return fish, selected_rarity, price

    def check_achievements(self, player: PlayerState, location: LocationData) -> int:
        bonus_total = 0
        RARITIES = ["N", "R", "SR", "SSR"]

        for rarity in RARITIES:
            key = f"collect_rarity_{location.id}_{rarity}"
            if key in player.completed_achievements:
                continue
            all_collected = True
            total_price = 0
            for fish_name in location.fish_pool:
                fish = self.fish_dict[fish_name]
                collection_key = f"{fish_name}_{rarity}"
                if collection_key not in player.collection:
                    all_collected = False
                    break
                total_price += calculate_fish_price(fish.base_price, rarity)
            if all_collected:
                player.completed_achievements.add(key)
                bonus = total_price * 3
                bonus_total += bonus

        for fish_name in location.fish_pool:
            fish = self.fish_dict[fish_name]
            key = f"collect_fish_{location.id}_{fish_name}"
            if key in player.completed_achievements:
                continue
            all_collected = True
            total_price = 0
            for rarity in RARITIES:
                collection_key = f"{fish_name}_{rarity}"
                if collection_key not in player.collection:
                    all_collected = False
                    break
                total_price += calculate_fish_price(fish.base_price, rarity)
            if all_collected:
                player.completed_achievements.add(key)
                bonus = total_price * 3
                bonus_total += bonus

        key = f"collect_scene_{location.id}"
        if key not in player.completed_achievements:
            all_collected = True
            total_price = 0
            for fish_name in location.fish_pool:
                fish = self.fish_dict[fish_name]
                for rarity in RARITIES:
                    if f"{fish_name}_{rarity}" not in player.collection:
                        all_collected = False
                        break
                    total_price += calculate_fish_price(fish.base_price, rarity)
                if not all_collected:
                    break
            if all_collected:
                player.completed_achievements.add(key)
                bonus = total_price * 3
                bonus_total += bonus

        return bonus_total

    def choose_location(self, player: PlayerState, day: int) -> LocationData:
        accessible = [
            loc for loc in self.locations if player.rod_level >= loc.difficulty
        ]
        if not accessible:
            return self.locations[0]

        best_loc = accessible[0]
        best_score = -1

        for loc in accessible:
            income = calculate_expected_income(player.rod_level, loc)
            missing = 0
            for fish_name in loc.fish_pool:
                for rarity in ["N", "R", "SR", "SSR"]:
                    if f"{fish_name}_{rarity}" not in player.collection:
                        missing += 1

            if missing > 0:
                score = 100000 + missing * 1000 + income
            else:
                score = income

            if score > best_score:
                best_score = score
                best_loc = loc

        return best_loc

    def choose_bait(
        self, player: PlayerState, location: LocationData, hours: float
    ) -> tuple[int, int, int]:
        expected_income = calculate_expected_income(player.rod_level, location)
        hook_multiplier = 1 + player.hook_level * self.hook_speed_per_level / 100
        base_fish_count = int(hours * 60 / (self.base_interval / hook_multiplier))

        best_bait_id = 0
        best_net = base_fish_count * expected_income

        for bait in self.baits:
            bait_multiplier = 1 + bait["speed_bonus"] / 100
            speed_factor = hook_multiplier * bait_multiplier
            fish_count = int(hours * 60 / (self.base_interval / speed_factor))
            gross = fish_count * expected_income
            bait_cost = fish_count * bait["price"]
            net = gross - bait_cost
            if net > best_net and player.gold >= bait_cost:
                best_net = net
                best_bait_id = bait["id"]

        if best_bait_id > 0:
            bait_info = next(b for b in self.baits if b["id"] == best_bait_id)
            bait_multiplier = 1 + bait_info["speed_bonus"] / 100
            speed_factor = hook_multiplier * bait_multiplier
            fish_count = int(hours * 60 / (self.base_interval / speed_factor))
            total_cost = fish_count * bait_info["price"]
            return best_bait_id, fish_count, total_cost

        return 0, 0, 0

    def simulate_fishing(
        self, player: PlayerState, hours: float, location: LocationData
    ) -> tuple[int, int, list[tuple[FishData, str, int]]]:
        hook_multiplier = 1 + player.hook_level * self.hook_speed_per_level / 100
        bait_info = player.get_bait_info(self.baits)
        bait_multiplier = 1 + bait_info["speed_bonus"] / 100
        fishing_interval = self.base_interval / (hook_multiplier * bait_multiplier)
        fish_count = int(hours * 60 / fishing_interval)
        total_gold = 0
        caught = []
        for _ in range(fish_count):
            if player.bait_count > 0:
                player.bait_count -= 1
                player.total_bait_spent += 1
            elif player.bait_id > 0:
                player.bait_id = 0

            fish, rarity, price = self.catch_fish(player, location)
            if fish.id == "展示木框":
                player.display_frames += 1
                caught.append((fish, rarity, price))
            else:
                total_gold += price
                player.collection[f"{fish.id}_{rarity}"] = True
                caught.append((fish, rarity, price))

        player.gold += total_gold
        player.total_fish_caught += fish_count
        player.total_gold_earned += total_gold
        player.fishing_hours += hours
        return fish_count, total_gold, caught

    def try_upgrade(self, player: PlayerState) -> str:
        if player.try_expand_display():
            return f"display_{player.display_slots_count}"

        rod_cost = self.rod_prices.get(player.rod_level + 1, float("inf"))
        hook_cost = self.hook_prices.get(player.hook_level + 1, float("inf"))

        if player.rod_level >= 10 and player.hook_level >= 10:
            return "max"

        can_rod = player.rod_level < 10 and player.gold >= rod_cost
        can_hook = player.hook_level < 10 and player.gold >= hook_cost

        accessible = [
            loc for loc in self.locations if player.rod_level >= loc.difficulty
        ]
        new_accessible = [
            loc for loc in self.locations if player.rod_level + 1 >= loc.difficulty
        ]

        rod_roi = 0
        hook_roi = 0

        if player.rod_level < 10 and len(new_accessible) > len(accessible):
            old_best = (
                max(
                    calculate_expected_income(player.rod_level, loc)
                    for loc in accessible
                )
                if accessible
                else 0
            )
            new_best = max(
                calculate_expected_income(player.rod_level + 1, loc)
                for loc in new_accessible
            )
            rod_roi = (new_best - old_best) / rod_cost
        elif player.rod_level < 10:
            old_best = (
                max(
                    calculate_expected_income(player.rod_level, loc)
                    for loc in accessible
                )
                if accessible
                else 0
            )
            new_best = (
                max(
                    calculate_expected_income(player.rod_level + 1, loc)
                    for loc in accessible
                )
                if accessible
                else 0
            )
            rod_roi = (new_best - old_best) / rod_cost

        if player.hook_level < 10:
            current_best = (
                max(
                    calculate_expected_income(player.rod_level, loc)
                    for loc in accessible
                )
                if accessible
                else 0
            )
            current_speed = 1 + player.hook_level * self.hook_speed_per_level / 100
            new_speed = 1 + (player.hook_level + 1) * self.hook_speed_per_level / 100
            hook_roi = current_best * (new_speed / current_speed - 1) / hook_cost

        if rod_roi >= hook_roi:
            if can_rod:
                player.gold -= rod_cost
                player.rod_level += 1
                return f"rod_{player.rod_level}"
            if can_hook:
                player.gold -= hook_cost
                player.hook_level += 1
                return f"hook_{player.hook_level}"
        else:
            if can_hook:
                player.gold -= hook_cost
                player.hook_level += 1
                return f"hook_{player.hook_level}"
            if can_rod:
                player.gold -= rod_cost
                player.rod_level += 1
                return f"rod_{player.rod_level}"

        return "wait"

    def run_simulation(self, days: int = 90, hours_per_day: float = 24.0) -> dict:
        player = PlayerState()

        print("=" * 150)
        print("钓鱼系统模拟测试 - 24h/天, 先钓后买 (数据来自shop.json & fish.json)")
        print("=" * 150)

        print("\n【当前升级价格(来自shop.json)】")
        print(f"  鱼竿: {dict(sorted(self.rod_prices.items()))}")
        print(f"  鱼钩: {dict(sorted(self.hook_prices.items()))}")
        print(f"  基础钓鱼间隔: {self.base_interval}分钟")
        print(f"  鱼钩每级速度加成: +{self.hook_speed_per_level}%")

        print("\n【收益增长验证】(按最优地点)")
        prev_income = None
        for rod in range(11):
            best_income = 0
            best_name = ""
            for loc in self.locations:
                if rod >= loc.difficulty:
                    income = calculate_expected_income(rod, loc)
                    if income > best_income:
                        best_income = income
                        best_name = loc.name
            if prev_income is not None:
                growth = best_income / prev_income
                print(
                    f"Lv.{rod}: {best_income:.1f} ({best_name})  增长={growth:.2f}x  {'OK' if abs(growth - 1.3) < 0.05 else '  '}"
                )
            else:
                print(f"Lv.{rod}: {best_income:.1f} ({best_name})")
            prev_income = best_income

        print(f"\n{'=' * 135}")
        print(f"模拟开始: {days}天, 每天{hours_per_day:.0f}h钓鱼, 先钓后买策略")
        print(f"{'=' * 135}")

        header = (
            f"{'Day':>4} | {'地点':<12} | {'鱼竿':<10} | {'鱼钩':<5} | {'鱼饵':<10} | "
            f"{'钓鱼数':>5} | {'钓鱼收入':>8} | {'鱼饵花费':>8} | {'展示收入':>8} | {'成就奖励':>8} | "
            f"{'金币总计':>10} | {'升级':<12}"
        )
        print(header)
        print("-" * 150)

        upgrade_history = []

        for day in range(1, days + 1):
            display_income = player.get_display_income()
            if display_income > 0:
                player.gold += display_income
                player.display_gold += display_income

            location = self.choose_location(player, day)

            fishing_bait_info = player.get_bait_info(self.baits)
            fishing_bait_name = fishing_bait_info["name"]
            fishing_bait_id = player.bait_id

            total_fish = 0
            total_gold = 0
            all_caught = []
            f, g, caught = self.simulate_fishing(player, hours_per_day, location)
            total_fish += f
            total_gold += g
            all_caught.extend(caught)

            ach_gold = self.check_achievements(player, location)
            if ach_gold > 0:
                player.gold += ach_gold
                player.achievement_gold += ach_gold

            player.update_display(all_caught)

            bait_cost_for_display = 0
            if fishing_bait_id > 0:
                bait_info = next(b for b in self.baits if b["id"] == fishing_bait_id)
                bait_cost_for_display = total_fish * bait_info["price"]

            upgrade = self.try_upgrade(player)
            if upgrade.startswith("rod") or upgrade.startswith("hook"):
                upgrade_history.append((day, upgrade))

            next_bait_id, next_bait_count, next_bait_cost = self.choose_bait(
                player, location, hours_per_day
            )
            if (
                next_bait_id > 0
                and next_bait_cost > 0
                and player.gold >= next_bait_cost
            ):
                player.gold -= next_bait_cost
                player.bait_id = next_bait_id
                player.bait_count = next_bait_count
            else:
                player.bait_id = 0
                player.bait_count = 0

            rod_name = self.rod_names.get(player.rod_level, f"Lv.{player.rod_level}")

            print(
                f"{day:>4} | {location.name:<12} | {rod_name:<10} | Lv.{player.hook_level:<3} | {fishing_bait_name:<10} | "
                f"{total_fish:>5} | {total_gold:>8,} | {bait_cost_for_display:>8,} | {display_income:>8,} | {ach_gold:>8,} | "
                f"{player.gold:>10,} | {upgrade:<12}"
            )

            if player.rod_level >= 10 and player.hook_level >= 10 and day > 60:
                if player.gold > 50000:
                    print(f"\n>>> 在第{day}天达到满级且资金充裕！")
                    break

        print(f"\n{'=' * 135}")
        print("最终统计")
        print(f"{'=' * 135}")
        print(
            f"  鱼竿等级: Lv.{player.rod_level} ({self.rod_names.get(player.rod_level, '')})"
        )
        print(f"  鱼钩等级: Lv.{player.hook_level}")
        print(f"  剩余金币: {player.gold:,}")
        print(f"  总钓鱼数: {player.total_fish_caught:,}")
        print(f"  钓鱼收益: {player.total_gold_earned:,}")
        print(f"  鱼饵花费: {player.total_bait_spent:,}")
        print(f"  展示收益: {player.display_gold:,}")
        print(f"  成就奖励: {player.achievement_gold:,}")
        print(
            f"  展示栏位: {player.display_slots_count}格, 日收益{player.get_display_income()}"
        )
        print(
            f"  图鉴收集: {len(player.collection)}/{sum(len(loc.fish_pool) for loc in self.locations) * 4}"
        )
        print(f"  成就完成: {len(player.completed_achievements)}个")
        print(f"  展示木框: {player.display_frames}个")
        print(f"  总钓鱼时间: {player.fishing_hours:.0f}小时")

        print("\n【升级历史】")
        for d, u in upgrade_history:
            if u.startswith("rod"):
                lvl = int(u.split("_")[1])
                print(f"  第{d:>3}天: {u} ({self.rod_names.get(lvl, '')})")
            else:
                print(f"  第{d:>3}天: {u}")

        print("\n【展示栏内容】")
        for i, slot in enumerate(sorted(player.display, key=lambda s: -s.daily_income)):
            print(
                f"  栏位{i + 1}: {slot.fish_name}({slot.rarity}) 日收益={slot.daily_income}"
            )

        print("\n【成就完成情况】")
        for key in sorted(player.completed_achievements):
            if key.startswith("collect_rarity_"):
                parts = key.split("_")
                loc_id = parts[2]
                rarity = parts[3]
                loc_name = next((l.name for l in self.locations if l.id == loc_id), "?")
                print(f"  稀有度全鱼收集: {loc_name} - {rarity}")
            elif key.startswith("collect_fish_"):
                parts = key.split("_")
                loc_id = parts[2]
                fish_name = "_".join(parts[3:])
                loc_name = next((l.name for l in self.locations if l.id == loc_id), "?")
                print(f"  鱼全稀有度收集: {loc_name} - {fish_name}")
            elif key.startswith("collect_scene_"):
                loc_id = key.split("_")[2]
                loc_name = next((l.name for l in self.locations if l.id == loc_id), "?")
                print(f"  场景全收集: {loc_name}")

        return {"player": player}


if __name__ == "__main__":
    sim = FishingSimulation()
    sim.run_simulation(90)
