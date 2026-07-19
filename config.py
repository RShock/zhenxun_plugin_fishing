"""
配置管理模块 — Pydantic 数据模型 + ConfigManager（JSON 加载/缓存）。

游戏设计常量已移至 constants.py，本模块从中重新导出以保持向后兼容。
新增代码应直接从 constants.py 导入常量。
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# ── 从 constants.py 重新导出（向后兼容）───────────────────────────────────────
from .constants import (
    CAT_EAT_CHANCE,  # noqa: F401 — 重新导出
    CAT_FRAME_PITY_THRESHOLD,
    DAILY_ACTION_LIMIT,
    DAILY_GIFT_LIMIT,
    DAILY_NEST_LIMIT,
    DAILY_SELL_LIMIT,
    DISPLAY_SLOT_COSTS,
    INDEX_RARITY,
    MAX_FRAME_BUFF_LAYERS,
    MAX_NEST_LAYERS,
    MAX_STATUS_PER_DAY,
    RARITY_COLORS,
    RARITY_DISTRIBUTION,
    RARITY_INDEX,
    RARITY_MAP,
    RARITY_MIN_LEVEL,
    RARITY_MULTIPLIER,
    RARITY_NAMES,
    RARITY_ORDER,
    UPGRADE_DISPLAY_COSTS,
    STARRY_FRAMES_MAX,
    STARRY_FRAME_UPGRADE_COSTS,
    WEATHER_EFFECT_DESC,
    WEATHER_EMOJI,
    WEATHER_NAME,
    apply_meteor_effect,
    calculate_fish_price,
    generate_fish_numeric_id,
    normalize_fish_numeric_id,
    get_display_probabilities,
    get_meteor_adjusted_probabilities,
    get_rarity_probabilities,
    get_rarity_probabilities_full,
)

# ── 配置文件路径 ──────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config"


# ── Pydantic 数据模型 ─────────────────────────────────────────────────────────


class LocationData(BaseModel):
    id: str
    name: str
    difficulty: int
    description: str
    fish_pool: list[str]
    max_rarity: str = "SSR"


class FishData(BaseModel):
    id: str
    base_price: int


class BaitData(BaseModel):
    id: int
    name: str
    speed_bonus: int
    price: int
    description: str


class PotionData(BaseModel):
    id: int
    name: str
    effect: str
    duration: int
    price: int
    description: str


class InitialGiftData(BaseModel):
    rod_level: int
    hook_level: int
    bait: int
    bait_count: int
    display_slots: int


class ShopData(BaseModel):
    rod_upgrade_prices: dict[str, int]
    rod_names: dict[str, str]
    hook_upgrade_prices: dict[str, int]
    hook_speed_bonus_per_level: int = 10
    baits: list[BaitData]
    potions: list[PotionData]
    display_slot_frame_costs: dict[str, int]
    nest_price: int = 500000
    nest_duration_hours: int = 8
    initial_gift: InitialGiftData
    exchange_rate: int = 1
    base_fishing_interval: int = 60


# ── ConfigManager ─────────────────────────────────────────────────────────────


class ConfigManager:
    """钓鱼配置管理器：惰性加载 JSON 配置文件并缓存。"""

    _locations: list[LocationData] | None = None
    _fish: list[FishData] | None = None
    _shop: ShopData | None = None
    _fish_order: dict[str, int] | None = None

    # ── JSON 加载 ─────────────────────────────────────────────────────────

    @classmethod
    def _load_json(cls, filename: str) -> dict[str, Any]:
        file_path = CONFIG_PATH / filename
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    # ── 钓场 ──────────────────────────────────────────────────────────────

    @classmethod
    def get_locations(cls) -> list[LocationData]:
        if cls._locations is None:
            data = cls._load_json("locations.json")
            cls._locations = [LocationData(**loc) for loc in data["locations"]]
        return cls._locations

    @classmethod
    def get_location(cls, location_id: str) -> LocationData | None:
        locations = cls.get_locations()
        try:
            idx = int(location_id)
            if 1 <= idx <= len(locations):
                loc = locations[idx - 1]
                if loc.id == location_id:
                    return loc
        except ValueError:
            pass
        for loc in locations:
            if loc.id == location_id:
                return loc
        return None

    # ── 鱼种 ──────────────────────────────────────────────────────────────

    @classmethod
    def get_fish_list(cls) -> list[FishData]:
        if cls._fish is None:
            data = cls._load_json("fish.json")
            cls._fish = [FishData(**f) for f in data["fish"]]
        return cls._fish

    @classmethod
    def get_fish_order(cls, fish_id: str) -> int:
        if cls._fish_order is None:
            cls._fish_order = {}
            for i, fish in enumerate(cls.get_fish_list()):
                cls._fish_order[fish.id] = i
        return cls._fish_order.get(fish_id, 9999)

    @classmethod
    def get_fish(cls, fish_id: str) -> FishData | None:
        for fish in cls.get_fish_list():
            if fish.id == fish_id:
                return fish
        return None

    get_fish_by_name = get_fish

    # ── 商店 ──────────────────────────────────────────────────────────────

    @classmethod
    def get_shop(cls) -> ShopData:
        if cls._shop is None:
            data = cls._load_json("shop.json")
            cls._shop = ShopData(**data)
        return cls._shop

    # ── 钓竿 / 鱼钩 ───────────────────────────────────────────────────────

    @classmethod
    def get_rod_name(cls, level: int) -> str:
        shop = cls.get_shop()
        return shop.rod_names.get(str(level), f"{level}级钓竿")

    @classmethod
    def get_rod_upgrade_price(cls, current_level: int) -> int:
        if current_level >= 20:
            return 0
        shop = cls.get_shop()
        return shop.rod_upgrade_prices.get(str(current_level + 1), 0)

    @classmethod
    def get_hook_upgrade_price(cls, current_level: int) -> int:
        if current_level >= 10:
            return 0
        shop = cls.get_shop()
        return shop.hook_upgrade_prices.get(str(current_level + 1), 0)

    # ── 物品查询 ──────────────────────────────────────────────────────────

    @classmethod
    def get_bait(cls, bait_id: int | str) -> BaitData | None:
        shop = cls.get_shop()
        if isinstance(bait_id, str):
            if bait_id.isdigit():
                bait_id = int(bait_id)
            else:
                for bait in shop.baits:
                    if bait.name == bait_id:
                        return bait
                return None
        for bait in shop.baits:
            if bait.id == bait_id:
                return bait
        return None

    @classmethod
    def get_potion(cls, potion_id: int | str) -> PotionData | None:
        shop = cls.get_shop()
        if isinstance(potion_id, str):
            if potion_id.isdigit():
                potion_id = int(potion_id)
            else:
                for potion in shop.potions:
                    if potion.name == potion_id:
                        return potion
                return None
        for potion in shop.potions:
            if potion.id == potion_id:
                return potion
        return None

    @classmethod
    def get_item_by_name_or_id(
        cls, name_or_id: str
    ) -> tuple[BaitData | PotionData | None, str | None]:
        bait = cls.get_bait(name_or_id)
        if bait:
            return bait, "bait"
        potion = cls.get_potion(name_or_id)
        if potion:
            return potion, "potion"
        return None, None

    # ── 展示栏 / 打窝 / 兑换 ──────────────────────────────────────────────

    @classmethod
    def get_display_slot_frame_cost(cls, slot_number: int) -> int:
        shop = cls.get_shop()
        return shop.display_slot_frame_costs.get(str(slot_number), slot_number - 3)

    @classmethod
    def get_nest_price(cls) -> int:
        return cls.get_shop().nest_price

    @classmethod
    def get_nest_duration_hours(cls) -> int:
        return cls.get_shop().nest_duration_hours

    @classmethod
    def get_initial_gift(cls) -> InitialGiftData:
        return cls.get_shop().initial_gift

    @classmethod
    def get_exchange_rate(cls) -> int:
        return cls.get_shop().exchange_rate

    @classmethod
    def get_base_fishing_interval(cls) -> int:
        return cls.get_shop().base_fishing_interval

    # ── 钓鱼间隔计算 ──────────────────────────────────────────────────────

    @classmethod
    def calculate_fishing_interval(
        cls, hook_level: int, bait_speed_bonus: int, has_speed_buff: bool = False
    ) -> float:
        base_interval = cls.get_base_fishing_interval()
        hook_multiplier = (
            1 + hook_level * cls.get_shop().hook_speed_bonus_per_level / 100
        )
        bait_multiplier = 1 + bait_speed_bonus / 100
        speed_multiplier = hook_multiplier * bait_multiplier
        if has_speed_buff:
            speed_multiplier *= 1.5
        actual_interval = base_interval / speed_multiplier
        return max(1, actual_interval)
