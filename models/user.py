"""
用户数据模型 — FishingUser。

所有玩家数据存储在 JSON 字段中（backpack/collection/items/displays 等），
避免多表 JOIN 查询。字段缺失时通过 _repair_user_fields 自动修复。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from tortoise import fields

from zhenxun.services.db_context import Model

from ..config import (
    DAILY_ACTION_LIMIT,
    DAILY_GIFT_LIMIT,
    DAILY_NEST_LIMIT,
    DAILY_SELL_LIMIT,
    MAX_STATUS_PER_DAY,
    normalize_fish_numeric_id,
)
from ..scene_instance import get_scene_instance_id
from . import user_mutations as mut


def _make_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


_EMPTY_DAILY = {
    "stop": {"count": 0, "date": None},
    "sell": {"count": 0, "date": None},
    "nest": {"count": 0, "date": None},
    "gift": {"count": 0, "date": None},
    "status": {"count": 0, "date": None},
    "black_market": {"count": 0, "date": None},
}

_EMPTY_BACKPACK = {}
_EMPTY_COLLECTION = {}
_EMPTY_ACHIEVEMENTS = []
_EMPTY_ITEMS = {}
_EMPTY_DISPLAYS = {}
_EMPTY_STARRY_FISH = []


def _ensure_dict(data: Any) -> dict:
    if not data or not isinstance(data, dict):
        return {}
    return data


def _normalize_backpack_numeric_ids(backpack: dict) -> tuple[dict, bool]:
    normalized: dict = {}
    changed = False
    for numeric_id, entry in backpack.items():
        new_id = normalize_fish_numeric_id(numeric_id)
        changed = changed or new_id != numeric_id
        if new_id in normalized:
            existing = normalized[new_id]
            existing["count"] = existing.get("count", 0) + entry.get("count", 0)
            existing["locked"] = existing.get("locked", False) or entry.get(
                "locked", False
            )
        else:
            normalized[new_id] = dict(entry)
    return normalized, changed


def _normalize_collection(collection: dict) -> tuple[dict, bool]:
    normalized: dict = {}
    changed = False
    for key, value in collection.items():
        if isinstance(value, dict):
            fish_name = key
            normalized.setdefault(fish_name, {})
            for rarity, count in value.items():
                normalized[fish_name][rarity] = normalized[fish_name].get(
                    rarity, 0
                ) + int(count or 0)
            continue
        parts = str(key).split("|", 1)
        if len(parts) != 2:
            normalized[key] = value
            continue
        fish_name, rarity = parts
        normalized.setdefault(fish_name, {})
        normalized[fish_name][rarity] = normalized[fish_name].get(rarity, 0) + int(
            value or 0
        )
        changed = True
    return normalized, changed


def _ensure_list(data: Any) -> list:
    if not data or not isinstance(data, list):
        return []
    return data


_FIELD_DEFAULTS = [
    ("owned_skins", list, ["1"]),
    ("skin_id", str, "1"),
    ("daily_counters", dict, lambda: dict(_EMPTY_DAILY)),
    ("backpack", dict, lambda: dict(_EMPTY_BACKPACK)),
    ("collection", dict, lambda: dict(_EMPTY_COLLECTION)),
    ("achievements", list, lambda: list(_EMPTY_ACHIEVEMENTS)),
    ("items", dict, lambda: dict(_EMPTY_ITEMS)),
    ("displays", dict, lambda: dict(_EMPTY_DISPLAYS)),
    ("starry_fish", list, lambda: list(_EMPTY_STARRY_FISH)),
    ("starry_exhibition", list, list),
]


def _repair_user_fields(user: "FishingUser") -> list[str]:
    need_save = False
    update_fields: list[str] = []

    for field_name, expected_type, default_factory in _FIELD_DEFAULTS:
        value = getattr(user, field_name, None)
        # 注意：空 list/dict 是合法默认值，不能用 `not value` 误判为缺失，
        # 否则会在 get_or_create 时把刚写入的 starry_fish=[] 反复覆盖。
        if expected_type in (list, dict):
            is_invalid = not isinstance(value, expected_type)
        else:
            is_invalid = value in (None, "") or not isinstance(value, expected_type)

        if field_name == "backpack" and isinstance(value, dict):
            normalized, normalized_changed = _normalize_backpack_numeric_ids(value)
            if normalized_changed:
                setattr(user, field_name, normalized)
                value = normalized
                need_save = True

        if field_name == "collection" and isinstance(value, dict):
            normalized, normalized_changed = _normalize_collection(value)
            if normalized_changed:
                setattr(user, field_name, normalized)
                value = normalized
                need_save = True

        if field_name == "owned_skins" and isinstance(value, list):
            if "1" not in value:
                value.append("1")
                need_save = True
            is_invalid = False

        if field_name == "skin_id" and not value:
            is_invalid = True

        if is_invalid:
            default = (
                default_factory() if callable(default_factory) else default_factory
            )
            setattr(user, field_name, default)
            need_save = True

        if need_save and field_name not in update_fields:
            update_fields.append(field_name)

    # 迁移：检测已领取猫猫乐园3级雕像奖励但 bonus_rod_level 未同步的玩家
    if user.bonus_rod_level == 0 and isinstance(user.items, dict):
        cp_entry = user.items.get("cat_park_state|event_state", {})
        raw = cp_entry.get("data") if isinstance(cp_entry, dict) else None
        if raw:
            try:
                cp_state = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(cp_state, dict) and cp_state.get("rod_reward_claimed"):
                    user.bonus_rod_level = 1
                    need_save = True
                    if "bonus_rod_level" not in update_fields:
                        update_fields.append("bonus_rod_level")
            except (json.JSONDecodeError, TypeError):
                pass

    return update_fields if need_save else []


class FishingUser(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    user_id = fields.CharField(255, unique=True, description="用户ID")
    rod_level = fields.IntField(default=0, description="钓竿等级(含额外加成)")
    bonus_rod_level = fields.IntField(
        default=0, description="额外鱼竿等级(猫猫乐园3级雕像)"
    )
    hook_level = fields.IntField(default=0, description="鱼钩等级")
    bait_id = fields.CharField(50, default="0", description="当前鱼饵ID(0=不使用)")
    preferred_bait_id = fields.CharField(
        50, default="0", description="优先鱼饵ID(0=自动选择)"
    )
    skin_id = fields.CharField(50, default="1", description="当前皮肤ID")
    owned_skins = fields.JSONField(default=["1"], description="拥有的皮肤列表")
    nickname = fields.CharField(255, default="", description="角色昵称")
    display_slots = fields.IntField(default=3, description="展示框数")
    gold = fields.IntField(default=0, description="钓鱼币")
    corn = fields.IntField(default=0, description="香甜玉米(打窝材料)")
    last_sign_date = fields.DateField(null=True, description="上次签到日期")
    display_frames = fields.IntField(default=0, description="木框数量")
    cat_frames = fields.IntField(default=0, description="猫框数量")
    upgraded_display_count = fields.IntField(
        default=0, description="猫猫展示框数量"
    )
    frame_pity_counter = fields.IntField(default=0, description="木框保底计数器")
    cat_frame_pity_counter = fields.IntField(default=0, description="猫框保底计数器")
    utr_pity_counter = fields.IntField(default=0, description="迷途风UTR保底计数器")
    black_market_pity_counter = fields.IntField(
        default=0, description="黑商秘密保底计数器(连续失败次数)"
    )
    smart_black_market_available_date = fields.DateField(
        null=True, description="智能黑商下次可用日期"
    )

    # ── 流星鱼 / 星空祈愿系统 ──
    starry_score_accumulated = fields.FloatField(
        default=0.0, description="流星鱼累计分数(星空祈愿努力值)"
    )
    star_frames = fields.IntField(default=0, description="星空框数量(奇迹奖励)")
    starry_frames = fields.IntField(default=0, description="星空展示框数量(星空框升级)")
    s2_ticket_claimed = fields.BooleanField(
        default=False, description="是否已领取S2入场券"
    )
    starry_fish = fields.JSONField(
        default=list, description="流星鱼背包[{id, score, display_score, ...}]"
    )
    starry_exhibition = fields.JSONField(
        default=list,
        description="流星鱼展馆[{fish_name, rarity, numeric_id, score, ...}]",
    )
    auto_sell = fields.BooleanField(default=False, description="自动卖鱼开关")
    auto_sell_rarity = fields.CharField(
        10, default="UTR", description="自动卖鱼稀有度阈值"
    )
    auto_lock = fields.BooleanField(default=False, description="自动锁鱼开关")
    auto_lock_pattern = fields.CharField(
        100, default="", description="自动锁鱼通配符表达式"
    )

    daily_counters = fields.JSONField(
        default=dict, description="每日计数器{type: {count, date}}"
    )
    backpack = fields.JSONField(
        default=dict, description="背包{numeric_id: {fish_name, rarity, count, locked}}"
    )
    collection = fields.JSONField(
        default=dict, description="图鉴{(fish_name,rarity): count}"
    )
    achievements = fields.JSONField(default=list, description="已完成成就列表[key]")
    items = fields.JSONField(
        default=dict, description="物品{item_id: {item_type, count}}"
    )
    displays = fields.JSONField(
        default=dict, description="展示栏{slot: {fish_name, rarity, numeric_id}}"
    )
    fishing_status = fields.JSONField(
        default=None, null=True, description="钓鱼状态{location_id, start_time}"
    )
    # ── 防闲置：记录上次钓鱼的地图与活跃时间，闲置超阈值时自动回溯钓鱼 ──
    last_location_id = fields.CharField(
        50, default="", description="上次钓鱼地图ID（防闲置用）"
    )
    last_active_time = fields.DatetimeField(
        null=True, description="上次钓鱼活跃时间（防闲置用）"
    )

    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "fishing_user"
        table_description = "钓鱼用户数据表"

    @property
    def base_rod_level(self) -> int:
        """商店定价用基础鱼竿等级（排除猫猫乐园雕像额外加成）。"""
        return max(0, self.rod_level - self.bonus_rod_level)

    @classmethod
    def _run_script(cls):
        return [
            "ALTER TABLE fishing_user ADD COLUMN cat_frames INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN upgraded_display_count INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN cat_frame_pity_counter INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN utr_pity_counter INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN black_market_pity_counter INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN smart_black_market_available_date DATE;",
            "ALTER TABLE fishing_user ADD COLUMN preferred_bait_id VARCHAR(50) NOT NULL DEFAULT '0';",
            "ALTER TABLE fishing_user ADD COLUMN bonus_rod_level INTEGER NOT NULL DEFAULT 0;",
            # ── 流星鱼 / 星空祈愿系统 ──
            "ALTER TABLE fishing_user ADD COLUMN starry_score_accumulated REAL NOT NULL DEFAULT 0.0;",
            "ALTER TABLE fishing_user ADD COLUMN star_frames INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN starry_frames INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN s2_ticket_claimed INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_user ADD COLUMN starry_fish TEXT;",
            "ALTER TABLE fishing_user ADD COLUMN starry_exhibition TEXT;",
            # ── 防闲置 ──
            "ALTER TABLE fishing_user ADD COLUMN last_location_id VARCHAR(50) NOT NULL DEFAULT '';",
            "ALTER TABLE fishing_user ADD COLUMN last_active_time TIMESTAMP;",
        ]

    @classmethod
    async def get_or_create_user(
        cls, user_id: str, nickname: str = ""
    ) -> tuple["FishingUser", bool]:
        defaults = {
            "owned_skins": ["1"],
            "daily_counters": dict(_EMPTY_DAILY),
            "backpack": dict(_EMPTY_BACKPACK),
            "collection": dict(_EMPTY_COLLECTION),
            "achievements": list(_EMPTY_ACHIEVEMENTS),
            "items": dict(_EMPTY_ITEMS),
            "displays": dict(_EMPTY_DISPLAYS),
            "starry_fish": list(_EMPTY_STARRY_FISH),
            "starry_exhibition": [],
        }
        if nickname:
            defaults["nickname"] = nickname
        user, created = await cls.get_or_create(user_id=user_id, defaults=defaults)
        if not created and nickname and not user.nickname:
            user.nickname = nickname
            await user.save(update_fields=["nickname"])
        if not created:
            update_fields = _repair_user_fields(user)
            if update_fields:
                await user.save(update_fields=update_fields)
        return user, created

    @classmethod
    async def get_user(cls, user_id: str) -> "FishingUser":
        user, _ = await cls.get_or_create_user(user_id)
        return user

    @classmethod
    async def rename_user(cls, user_id: str, new_name: str) -> bool:
        user = await cls.get_user(user_id)
        user.nickname = new_name
        await user.save(update_fields=["nickname"])
        return True

    @classmethod
    async def change_skin(cls, user_id: str, skin_id: str) -> tuple[bool, str]:
        user = await cls.get_user(user_id)
        if not user.owned_skins or skin_id not in user.owned_skins:
            return False, f"你没有皮肤 {skin_id}"
        user.skin_id = skin_id
        await user.save(update_fields=["skin_id"])
        return True, f"已更换为皮肤 {skin_id}"

    @classmethod
    async def add_skin(cls, user_id: str, skin_id: str) -> None:
        user = await cls.get_user(user_id)
        if not user.owned_skins:
            user.owned_skins = ["1"]
        if skin_id not in user.owned_skins:
            user.owned_skins.append(skin_id)
            await user.save(update_fields=["owned_skins"])

    @classmethod
    async def get_owned_skins(cls, user_id: str) -> list[str]:
        user = await cls.get_user(user_id)
        if not user.owned_skins or not isinstance(user.owned_skins, list):
            return ["1"]
        if "1" not in user.owned_skins:
            user.owned_skins.append("1")
            await user.save(update_fields=["owned_skins"])
        return user.owned_skins

    @classmethod
    async def update_gold(cls, user_id: str, amount: int) -> None:
        user = await cls.get_user(user_id)
        user.gold += amount
        await user.save(update_fields=["gold"])

    @classmethod
    async def add_gold(cls, user_id: str, amount: int) -> None:
        await cls.update_gold(user_id, amount)

    @classmethod
    async def reduce_gold(cls, user_id: str, amount: int) -> bool:
        user = await cls.get_user(user_id)
        if user.gold < amount:
            return False
        user.gold -= amount
        await user.save(update_fields=["gold"])
        return True

    @classmethod
    async def update_corn(cls, user_id: str, amount: int) -> None:
        user = await cls.get_user(user_id)
        user.corn += amount
        await user.save(update_fields=["corn"])

    @classmethod
    async def add_corn(cls, user_id: str, amount: int = 1) -> None:
        await cls.update_corn(user_id, amount)

    @classmethod
    async def reduce_corn(cls, user_id: str, amount: int = 1) -> bool:
        user = await cls.get_user(user_id)
        if user.corn < amount:
            return False
        user.corn -= amount
        await user.save(update_fields=["corn"])
        return True

    @classmethod
    async def get_auto_sell(cls, user_id: str) -> bool:
        user = await cls.get_user(user_id)
        return bool(user.auto_sell)

    @classmethod
    async def get_auto_sell_rarity(cls, user_id: str) -> str:
        user = await cls.get_user(user_id)
        return user.auto_sell_rarity or "UTR"

    @classmethod
    async def toggle_auto_sell(cls, user_id: str, enabled: bool) -> None:
        user = await cls.get_user(user_id)
        user.auto_sell = enabled
        await user.save(update_fields=["auto_sell"])

    @classmethod
    async def set_auto_sell_rarity(cls, user_id: str, rarity: str) -> None:
        user = await cls.get_user(user_id)
        user.auto_sell_rarity = rarity
        user.auto_sell = True
        await user.save(update_fields=["auto_sell_rarity", "auto_sell"])

    @classmethod
    async def get_auto_lock(cls, user_id: str) -> bool:
        user = await cls.get_user(user_id)
        return bool(user.auto_lock)

    @classmethod
    async def get_auto_lock_pattern(cls, user_id: str) -> str:
        user = await cls.get_user(user_id)
        return user.auto_lock_pattern or ""

    @classmethod
    async def toggle_auto_lock(cls, user_id: str, enabled: bool) -> None:
        user = await cls.get_user(user_id)
        user.auto_lock = enabled
        await user.save(update_fields=["auto_lock"])

    @classmethod
    async def set_auto_lock_pattern(cls, user_id: str, pattern: str) -> None:
        user = await cls.get_user(user_id)
        user.auto_lock_pattern = pattern
        user.auto_lock = True
        await user.save(update_fields=["auto_lock_pattern", "auto_lock"])

    @classmethod
    async def check_and_sign(cls, user_id: str) -> tuple[bool, int, int]:
        """检查并签到，返回 (是否新签到, 当前玉米数, 错过的天数)。

        错过天数 = 距离上次签到间隔的天数 - 1（整日未收杆的天数）。
        当日复签返回 (False, 0, 0)；首次签到返回 (True, corn, 0)。
        """
        user = await cls.get_user(user_id)
        today = date.today()
        if user.last_sign_date == today:
            return False, 0, 0

        days_missed = 0
        if user.last_sign_date is not None:
            delta = (today - user.last_sign_date).days
            days_missed = max(0, delta - 1)

        user.last_sign_date = today
        user.corn += 1
        await user.save(update_fields=["last_sign_date", "corn"])
        return True, user.corn, days_missed

    def _get_daily_counter(self, counter_type: str) -> tuple[int, str | None]:
        counters = _ensure_dict(self.daily_counters)
        info = counters.get(counter_type, {"count": 0, "date": None})
        return info.get("count", 0), info.get("date")

    def _set_daily_counter(
        self, counter_type: str, count: int, date_str: str | None
    ) -> None:
        self.daily_counters = _ensure_dict(self.daily_counters)
        self.daily_counters[counter_type] = {"count": count, "date": date_str}

    @classmethod
    async def _increment_daily_counter(
        cls, user_id: str, counter_type: str, max_count: int
    ) -> tuple[int, bool]:
        user = await cls.get_user(user_id)
        today_str = date.today().isoformat()
        current_count, current_date = user._get_daily_counter(counter_type)
        if current_date != today_str:
            current_count = 0
        new_count = current_count + 1
        user._set_daily_counter(counter_type, new_count, today_str)
        await user.save(update_fields=["daily_counters"])
        return new_count, new_count >= max_count

    @classmethod
    async def _get_daily_count(cls, user_id: str, counter_type: str) -> int:
        user = await cls.get_user(user_id)
        today_str = date.today().isoformat()
        current_count, current_date = user._get_daily_counter(counter_type)
        if current_date != today_str:
            return 0
        return current_count

    @classmethod
    async def increment_stop_count(cls, user_id: str) -> tuple[int, bool]:
        return await cls._increment_daily_counter(user_id, "stop", DAILY_ACTION_LIMIT)

    @classmethod
    async def get_stop_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "stop")

    @classmethod
    async def increment_sell_count(cls, user_id: str) -> tuple[int, bool]:
        return await cls._increment_daily_counter(user_id, "sell", DAILY_SELL_LIMIT)

    @classmethod
    async def get_sell_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "sell")

    @classmethod
    async def add_display_frames(cls, user_id: str, count: int = 1) -> None:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        mut.apply_add_display_frames(user, count, dirty)
        await mut.save_dirty(user, dirty)

    @classmethod
    async def reduce_display_frames(cls, user_id: str, count: int = 1) -> bool:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        ok = mut.apply_reduce_display_frames(user, count, dirty)
        if ok:
            await mut.save_dirty(user, dirty)
        return ok

    @classmethod
    async def add_cat_frames(cls, user_id: str, count: int = 1) -> None:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        mut.apply_add_cat_frames(user, count, dirty)
        await mut.save_dirty(user, dirty)

    @classmethod
    async def reduce_cat_frames(cls, user_id: str, count: int = 1) -> bool:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        ok = mut.apply_reduce_cat_frames(user, count, dirty)
        if ok:
            await mut.save_dirty(user, dirty)
        return ok

    @classmethod
    async def increment_nest_count(cls, user_id: str) -> tuple[int, bool]:
        return await cls._increment_daily_counter(user_id, "nest", DAILY_NEST_LIMIT)

    @classmethod
    async def get_nest_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "nest")

    @classmethod
    async def increment_gift_count(cls, user_id: str) -> int:
        count, _ = await cls._increment_daily_counter(user_id, "gift", DAILY_GIFT_LIMIT)
        return count

    @classmethod
    async def get_gift_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "gift")

    @classmethod
    async def increment_black_market_count(cls, user_id: str) -> int:
        count, _ = await cls._increment_daily_counter(user_id, "black_market", 1)
        return count

    @classmethod
    async def get_black_market_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "black_market")

    @classmethod
    async def decrement_black_market_count(cls, user_id: str) -> int:
        """黑商撤回时回退当日交换计数（不低于 0），返回回退后的值。"""
        user = await cls.get_user(user_id)
        today_str = date.today().isoformat()
        current_count, current_date = user._get_daily_counter("black_market")
        if current_date != today_str:
            current_count = 0
        new_count = max(0, current_count - 1)
        user._set_daily_counter("black_market", new_count, today_str)
        await user.save(update_fields=["daily_counters"])
        return new_count

    @classmethod
    async def increment_status_count(cls, user_id: str) -> tuple[int, bool]:
        return await cls._increment_daily_counter(user_id, "status", MAX_STATUS_PER_DAY)

    @classmethod
    async def get_status_count(cls, user_id: str) -> int:
        return await cls._get_daily_count(user_id, "status")

    @classmethod
    async def add_fish(
        cls, user_id: str, fish_name: str, rarity: str, numeric_id: str, count: int = 1
    ) -> None:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        mut.apply_add_fish(user, fish_name, rarity, numeric_id, count, dirty)
        await mut.save_dirty(user, dirty)

    @classmethod
    async def get_user_fish(cls, user_id: str) -> list[dict]:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        if not backpack:
            return []
        rarity_order = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "UTR": 5}
        fish_list = []
        for numeric_id, entry in backpack.items():
            fish_list.append(
                {
                    "numeric_id": numeric_id,
                    "fish_name": entry.get("fish_name", ""),
                    "rarity": entry.get("rarity", "N"),
                    "count": entry.get("count", 0),
                    "locked": entry.get("locked", False),
                }
            )
        fish_list.sort(
            key=lambda f: (rarity_order.get(f["rarity"], 0), f["count"]), reverse=True
        )
        return fish_list

    @classmethod
    async def get_fish_by_numeric_id(cls, user_id: str, numeric_id: str) -> dict | None:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        normalized_id = normalize_fish_numeric_id(numeric_id)
        entry = backpack.get(normalized_id)
        if not entry:
            return None
        return {
            "numeric_id": normalized_id,
            "fish_name": entry.get("fish_name", ""),
            "rarity": entry.get("rarity", "N"),
            "count": entry.get("count", 0),
            "locked": entry.get("locked", False),
        }

    @classmethod
    async def remove_fish_by_numeric_id(
        cls, user_id: str, numeric_id: str, count: int = 1
    ) -> bool:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        normalized_id = normalize_fish_numeric_id(numeric_id)
        entry = backpack.get(normalized_id)
        if not entry or entry.get("count", 0) < count:
            return False
        entry["count"] -= count
        if entry["count"] <= 0:
            del user.backpack[normalized_id]
        user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
        await user.save(update_fields=["backpack"])
        return True

    @classmethod
    async def toggle_lock_by_numeric_id(
        cls, user_id: str, numeric_id: str, lock: bool | None = None
    ) -> bool:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        normalized_id = normalize_fish_numeric_id(numeric_id)
        entry = backpack.get(normalized_id)
        if not entry:
            return False
        entry["locked"] = lock if lock is not None else not entry.get("locked", False)
        user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
        await user.save(update_fields=["backpack"])
        return True

    @classmethod
    async def lock_by_rarity(cls, user_id: str, rarity: str) -> int:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if entry.get("rarity") == rarity and not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def unlock_by_rarity(cls, user_id: str, rarity: str) -> int:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if entry.get("rarity") == rarity and entry.get("locked", False):
                entry["locked"] = False
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def lock_by_location_prefix(cls, user_id: str, prefix: str) -> int:
        """锁定鱼ID以 prefix 开头的所有鱼（如 s1 匹配猫猫乐园全部鱼）。"""
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if numeric_id.startswith(prefix) and not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def unlock_by_location_prefix(cls, user_id: str, prefix: str) -> int:
        """解锁鱼ID以 prefix 开头的所有鱼。"""
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if numeric_id.startswith(prefix) and entry.get("locked", False):
                entry["locked"] = False
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def lock_all(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def unlock_all(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        count = 0
        for numeric_id, entry in backpack.items():
            if entry.get("locked", False):
                entry["locked"] = False
                count += 1
        if count > 0:
            user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
            await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def get_unlocked_fish(cls, user_id: str) -> list[dict]:
        fish_list = await cls.get_user_fish(user_id)
        return [f for f in fish_list if not f.get("locked", False)]

    @classmethod
    async def clear_user_backpack(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        count = len(user.backpack) if user.backpack else 0
        user.backpack = {}
        await user.save(update_fields=["backpack"])
        return count

    @classmethod
    async def filter_fish(
        cls,
        user_id: str,
        rarity_in: list[str] | None = None,
        locked: bool | None = None,
        numeric_id: str | None = None,
    ) -> list[dict]:
        fish_list = await cls.get_user_fish(user_id)
        normalized_id = normalize_fish_numeric_id(numeric_id) if numeric_id else None
        result = []
        for f in fish_list:
            if rarity_in and f["rarity"] not in rarity_in:
                continue
            if locked is not None and f.get("locked", False) != locked:
                continue
            if normalized_id and f["numeric_id"] != normalized_id:
                continue
            result.append(f)
        return result

    @classmethod
    async def delete_fish_entries(cls, user_id: str, fish_list: list[dict]) -> None:
        user = await cls.get_user(user_id)
        backpack = _ensure_dict(user.backpack)
        for f in fish_list:
            nid = normalize_fish_numeric_id(f.get("numeric_id"))
            if nid and nid in backpack:
                del user.backpack[nid]
        user.backpack = dict(user.backpack)  # 强制 tortoise 检测 JSONField 嵌套变更
        await user.save(update_fields=["backpack"])

    @classmethod
    async def mark_collected(
        cls, user_id: str, fish_name: str, rarity: str, count: int = 1
    ) -> None:
        user = await cls.get_user(user_id)
        collection, _ = _normalize_collection(_ensure_dict(user.collection))
        fish_entry = collection.setdefault(fish_name, {})
        fish_entry[rarity] = fish_entry.get(rarity, 0) + count
        user.collection = collection
        await user.save(update_fields=["collection"])

    @classmethod
    async def get_user_collected(cls, user_id: str) -> set[tuple[str, str]]:
        user = await cls.get_user(user_id)
        collection, changed = _normalize_collection(_ensure_dict(user.collection))
        if changed:
            user.collection = collection
            await user.save(update_fields=["collection"])
        result = set()
        for fish_name, rarities in collection.items():
            if not isinstance(rarities, dict):
                continue
            for rarity, count in rarities.items():
                if count:
                    result.add((fish_name, rarity))
        return result

    @classmethod
    async def get_user_collected_with_count(
        cls, user_id: str
    ) -> dict[tuple[str, str], int]:
        user = await cls.get_user(user_id)
        collection, changed = _normalize_collection(_ensure_dict(user.collection))
        if changed:
            user.collection = collection
            await user.save(update_fields=["collection"])
        result = {}
        for fish_name, rarities in collection.items():
            if not isinstance(rarities, dict):
                continue
            for rarity, count in rarities.items():
                result[(fish_name, rarity)] = count
        return result

    @classmethod
    async def is_collected(cls, user_id: str, fish_name: str, rarity: str) -> bool:
        user = await cls.get_user(user_id)
        collection, changed = _normalize_collection(_ensure_dict(user.collection))
        if changed:
            user.collection = collection
            await user.save(update_fields=["collection"])
        return bool(collection.get(fish_name, {}).get(rarity, 0))

    @classmethod
    async def clear_user_collection(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        count = len(user.collection) if user.collection else 0
        user.collection = {}
        await user.save(update_fields=["collection"])
        return count

    @classmethod
    async def is_achievement_completed(cls, user_id: str, achievement_key: str) -> bool:
        user = await cls.get_user(user_id)
        achievements = _ensure_list(user.achievements)
        result = achievement_key in achievements
        return result

    @classmethod
    async def mark_achievement_completed(
        cls, user_id: str, achievement_key: str
    ) -> None:
        user = await cls.get_user(user_id)
        user.achievements = _ensure_list(user.achievements)
        if achievement_key not in user.achievements:
            user.achievements.append(achievement_key)
            await user.save(update_fields=["achievements"])

    @classmethod
    async def get_user_achievements(cls, user_id: str) -> set[str]:
        user = await cls.get_user(user_id)
        achievements = _ensure_list(user.achievements)
        return set(achievements)

    @classmethod
    async def has_unlocked_lost_wind(cls, user_id: str, location_id: str) -> bool:
        achievement_key = f"collect_scene_{location_id}"
        result = await cls.is_achievement_completed(user_id, achievement_key)
        return result

    @classmethod
    async def add_item(
        cls, user_id: str, item_id: str, item_type: str, count: int = 1
    ) -> None:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        mut.apply_add_item(user, item_id, item_type, count, dirty)
        await mut.save_dirty(user, dirty)

    @classmethod
    async def add_starry_fish(
        cls, user_id: str, fish_id: int | str, location_id: str = ""
    ) -> dict:
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        record = mut.apply_add_starry_fish(user, fish_id, location_id, dirty)
        await mut.save_dirty(user, dirty)
        return record

    @classmethod
    async def get_user_starry_fish(cls, user_id: str) -> list[dict]:
        user = await cls.get_user(user_id)
        return list(_ensure_list(user.starry_fish))

    @classmethod
    async def get_user_starry_exhibition(cls, user_id: str) -> list[dict]:
        user = await cls.get_user(user_id)
        return list(_ensure_list(user.starry_exhibition))

    @classmethod
    async def get_all_starry_exhibition_entries(cls) -> list[tuple[str, str, list[dict]]]:
        """返回所有拥有展馆藏品的 (user_id, nickname, exhibition_records) 列表。

        仅供星空排行使用：遍历全表，在 Python 层过滤空展馆，
        避免依赖 JSONField 的 DB 端过滤差异（SQLite/PostgreSQL 行为不同）。
        """
        users = await cls.all().only("user_id", "nickname", "starry_exhibition")
        result: list[tuple[str, str, list[dict]]] = []
        for user in users:
            exhibition = _ensure_list(user.starry_exhibition)
            if exhibition:
                name = user.nickname or user.user_id
                result.append((user.user_id, name, exhibition))
        return result

    @classmethod
    async def get_exhibition_fisher_ids_in_group(cls, group_id: str) -> set[str]:
        """返回最近一次钓鱼来源群为指定群的玩家 ID 集合。

        仅作为星空排行按群过滤的备用手段：当 get_group_member_list
        不可用（如 QQ 官方群无成员接口）时，按开始钓鱼时记录的来源群判定归属。
        """
        group_id = str(group_id)
        result: set[str] = set()
        users = await cls.all().only("user_id", "fishing_status")
        for user in users:
            status = user.fishing_status
            if isinstance(status, dict) and str(status.get("group_id", "")) == group_id:
                result.add(user.user_id)
        return result

    @classmethod
    async def try_claim_miracle(cls, user_id: str) -> dict | None:
        """尝试用持有的流星鱼凑一次奇迹，成功则消耗子集并 +1 星空框。

        规则：
        - `starry_fish`、`starry_exhibition` 与旧 `items.meteor_fish` 均参与并消耗
        - 搜索全部持有记录，优先使用 MITM 精确子集和
        - 星空框库存不设持有上限
        """
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        info = mut.apply_try_claim_miracle(user, dirty)
        await mut.save_dirty(user, dirty)
        return info

    @classmethod
    async def try_claim_miracles(
        cls, user_id: str, *, max_claims: int | None = None
    ) -> list[dict]:
        """连续尝试奇迹结算，直到无法再凑出符合条件的子集。

        每次成功消耗一组持有的流星鱼并 +1 星空框。
        """
        user = await cls.get_user(user_id)
        dirty: set[str] = set()
        claims = mut.apply_try_claim_miracles(user, max_claims=max_claims, dirty=dirty)
        await mut.save_dirty(user, dirty)
        return claims

    @classmethod
    async def get_user_items(cls, user_id: str) -> list[dict]:
        user = await cls.get_user(user_id)
        items = _ensure_dict(user.items)
        result = []
        for key, entry in items.items():
            parts = key.split("|", 1)
            if len(parts) == 2:
                result.append(
                    {
                        "item_id": parts[0],
                        "item_type": entry.get("item_type", parts[1]),
                        "count": entry.get("count", 0),
                    }
                )
        return result

    @classmethod
    async def get_item(cls, user_id: str, item_id: str, item_type: str) -> dict | None:
        user = await cls.get_user(user_id)
        items = _ensure_dict(user.items)
        key = f"{item_id}|{item_type}"
        entry = items.get(key)
        if not entry:
            return None
        return {
            "item_id": item_id,
            "item_type": entry.get("item_type", item_type),
            "count": entry.get("count", 0),
        }

    @classmethod
    async def remove_item(
        cls, user_id: str, item_id: str, item_type: str, count: int = 1
    ) -> bool:
        user = await cls.get_user(user_id)
        items = _ensure_dict(user.items)
        key = f"{item_id}|{item_type}"
        entry = items.get(key)
        if not entry or entry.get("count", 0) < count:
            return False
        entry["count"] -= count
        if entry["count"] <= 0:
            del user.items[key]
        await user.save(update_fields=["items"])
        return True

    @classmethod
    async def has_item(cls, user_id: str, item_id: str, item_type: str) -> bool:
        user = await cls.get_user(user_id)
        items = _ensure_dict(user.items)
        key = f"{item_id}|{item_type}"
        return key in items

    @classmethod
    async def clear_user_items(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        count = len(user.items) if user.items else 0
        user.items = {}
        await user.save(update_fields=["items"])
        return count

    @classmethod
    async def get_user_displays(cls, user_id: str) -> list[dict]:
        user = await cls.get_user(user_id)
        displays = _ensure_dict(user.displays)
        if not displays:
            return []
        result = []
        for slot_str, entry in displays.items():
            result.append(
                {
                    "slot": int(slot_str),
                    "fish_name": entry.get("fish_name", ""),
                    "rarity": entry.get("rarity", "N"),
                    "numeric_id": normalize_fish_numeric_id(
                        entry.get("numeric_id", "")
                    ),
                }
            )
        result.sort(key=lambda d: d["slot"])
        return result

    @classmethod
    async def set_display(
        cls, user_id: str, slot: int, fish_name: str, rarity: str, numeric_id: str
    ) -> dict:
        user = await cls.get_user(user_id)
        user.displays = _ensure_dict(user.displays)
        numeric_id = normalize_fish_numeric_id(numeric_id)
        slot_str = str(slot)
        existing = user.displays.get(slot_str)
        if existing:
            await cls.add_fish(
                user_id,
                existing.get("fish_name", ""),
                existing.get("rarity", "N"),
                existing.get("numeric_id", ""),
                1,
            )
        user.displays[slot_str] = {
            "fish_name": fish_name,
            "rarity": rarity,
            "numeric_id": numeric_id,
        }
        await user.save(update_fields=["displays"])
        return user.displays[slot_str]

    @classmethod
    async def remove_display(cls, user_id: str, slot: int) -> bool:
        user = await cls.get_user(user_id)
        user.displays = _ensure_dict(user.displays)
        slot_str = str(slot)
        if slot_str not in user.displays:
            return False
        del user.displays[slot_str]
        await user.save(update_fields=["displays"])
        return True

    @classmethod
    async def get_all_displays(cls) -> list[dict]:
        users = await cls.all()
        result = []
        for user in users:
            if not user.displays or not isinstance(user.displays, dict):
                continue
            for slot_str, entry in user.displays.items():
                result.append(
                    {
                        "user_id": user.user_id,
                        "slot": int(slot_str),
                        "fish_name": entry.get("fish_name", ""),
                        "rarity": entry.get("rarity", "N"),
                        "numeric_id": normalize_fish_numeric_id(
                            entry.get("numeric_id", "")
                        ),
                    }
                )
        return result

    @classmethod
    async def clear_user_displays(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        count = len(user.displays) if user.displays else 0
        user.displays = {}
        await user.save(update_fields=["displays"])
        return count

    @classmethod
    async def start_fishing(
        cls,
        user_id: str,
        location_id: str,
        start_time: datetime | None = None,
        group_id: str | None = None,
    ) -> dict:
        user = await cls.get_user(user_id)
        # start_time 用于防闲置回溯：会话起始设为过去时刻，懒计算在收杆时补算鱼获
        session_start = start_time or datetime.now()
        now_iso = session_start.isoformat()
        user.fishing_status = {
            "location_id": location_id,
            "start_time": now_iso,
            "last_settle_time": now_iso,
            "fish_caught": [],
            "bait_consumed": 0,
            "frame_pity": user.frame_pity_counter,
            "utr_pity": user.utr_pity_counter,
            "cat_frame_pity": user.cat_frame_pity_counter,
            "time_potions_used": [],
        }
        if group_id:
            user.fishing_status["group_id"] = str(group_id)
        # 防闲置记录：last_active_time 始终为真实操作时间（now），而非回溯的 start_time
        user.last_location_id = location_id
        user.last_active_time = datetime.now()
        await user.save(
            update_fields=["fishing_status", "last_location_id", "last_active_time"]
        )
        return user.fishing_status

    @classmethod
    async def get_status(cls, user_id: str) -> dict | None:
        user = await cls.get_user(user_id)
        return user.fishing_status

    @classmethod
    async def update_fishing_status(cls, user_id: str, status: dict) -> None:
        user = await cls.get_user(user_id)
        user.fishing_status = status
        await user.save(update_fields=["fishing_status"])

    @classmethod
    async def stop_fishing(cls, user_id: str) -> dict | None:
        user = await cls.get_user(user_id)
        status = user.fishing_status
        if status:
            # 防闲置：收杆时记录上次钓鱼位置和活跃时间
            if isinstance(status, dict) and status.get("location_id"):
                user.last_location_id = status["location_id"]
            user.last_active_time = datetime.now()
            user.fishing_status = None
            await user.save(
                update_fields=[
                    "fishing_status", "last_location_id", "last_active_time"
                ]
            )
        return status

    @classmethod
    async def is_fishing(cls, user_id: str) -> bool:
        user = await cls.get_user(user_id)
        return user.fishing_status is not None

    @classmethod
    async def get_location_fishers(cls, location_id: str) -> list[str]:
        users = await cls.all()
        result = []
        for user in users:
            if user.fishing_status and isinstance(user.fishing_status, dict):
                scene_id = get_scene_instance_id(user.fishing_status)
                if scene_id == location_id:
                    result.append(user.user_id)
        return result

    @classmethod
    async def get_location_fisher_counts(cls) -> dict[str, int]:
        users = await cls.all()
        counts: dict[str, int] = {}
        for user in users:
            if user.fishing_status and isinstance(user.fishing_status, dict):
                lid = get_scene_instance_id(user.fishing_status)
                if lid:
                    counts[lid] = counts.get(lid, 0) + 1
        return counts

    @classmethod
    async def clear_user_status(cls, user_id: str) -> int:
        user = await cls.get_user(user_id)
        if user.fishing_status:
            user.fishing_status = None
            await user.save(update_fields=["fishing_status"])
            return 1
        return 0

    @classmethod
    async def reset_user(cls, user_id: str) -> bool:
        user = await cls.filter(user_id=user_id).first()
        if user:
            await user.delete()
            return True
        return False

    @classmethod
    async def clear_all_user_data(cls, user_id: str) -> None:
        user = await cls.get_user(user_id)
        user.backpack = {}
        user.collection = {}
        user.achievements = []
        user.items = {}
        user.displays = {}
        user.fishing_status = None
        user.daily_counters = dict(_EMPTY_DAILY)
        await user.save(
            update_fields=[
                "backpack",
                "collection",
                "achievements",
                "items",
                "displays",
                "fishing_status",
                "daily_counters",
            ]
        )
