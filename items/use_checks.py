"""Shared preflight checks for every public fishing item-use entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from ..config import ConfigManager
from ..constants import DAILY_NEST_LIMIT, MAX_FRAME_BUFF_LAYERS, MAX_NEST_LAYERS
from ..core.context import normalize_time_potions
from ..models import BuffEffect, FishingBuff
from ..models import user_mutations as mut
from ..models.user import _normalize_collection
from ..scene_instance import get_scene_instance_id
from ..services import get_or_create_user
from ..services.achievement_service import BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE
from ..starry import STARRY_BONUS_VALUE, STARRY_MAX_LAYERS, is_starry_location


@dataclass(frozen=True)
class ItemUseCheck:
    canonical_name: str
    count: int
    usable: bool
    reason: str = ""


@dataclass(frozen=True)
class UtrUseOption:
    location_id: str
    fish_name: str

    @property
    def label(self) -> str:
        return f"{self.location_id}图 {self.fish_name}"

    @property
    def command(self) -> str:
        return f"钓鱼使用 UTR自选券 {self.fish_name}"


_ITEM_ORDER = (
    "时光药水",
    "回档药水",
    "幸运药水",
    "真多多药水",
    "闪光药水",
    "UTR自选券",
    "香甜玉米",
    "展示木框",
    "猫猫框",
    "大肥鱼",
    "许愿药水",
    "星空框",
)

_ALIASES = {
    "时间药水": "时光药水",
    "回溯药水": "回档药水",
    "多多药水": "真多多药水",
    "utr自选券": "UTR自选券",
    "UTR券": "UTR自选券",
    "utr券": "UTR自选券",
    "玉米": "香甜玉米",
    "木框": "展示木框",
    "猫框": "猫猫框",
}

_JSON_ITEMS = {
    "时光药水": ("time_potion", "potion"),
    "回档药水": ("回档药水", "potion"),
    "幸运药水": ("幸运药水", "potion"),
    "真多多药水": ("真多多药水", "potion"),
    "闪光药水": ("闪光药水", "potion"),
    "UTR自选券": ("utr_select_ticket", "ticket"),
    "大肥鱼": (BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE),
    "许愿药水": ("许愿药水", "potion"),
}

_SCALAR_FIELDS = {
    "香甜玉米": "corn",
    "展示木框": "display_frames",
    "猫猫框": "cat_frames",
    "星空框": "star_frames",
}

_UNITS = {
    "时光药水": "瓶",
    "回档药水": "瓶",
    "幸运药水": "瓶",
    "真多多药水": "瓶",
    "闪光药水": "瓶",
    "UTR自选券": "张",
}

_RELEVANT_BUFF_TYPES = (
    BuffEffect.BUFF_TYPE_NEST,
    BuffEffect.BUFF_TYPE_FRAME,
    BuffEffect.BUFF_TYPE_CAT_NEST,
    BuffEffect.BUFF_TYPE_STARRY_BONUS,
)


def normalize_use_item_name(item_name: str) -> str:
    compact = (item_name or "").replace(" ", "").replace("　", "")
    return _ALIASES.get(compact, compact)


def _json_item_count(user, item_id: str, item_type: str) -> int:
    items = user.items if isinstance(getattr(user, "items", None), dict) else {}
    entry = items.get(f"{item_id}|{item_type}")
    if not isinstance(entry, dict):
        return 0
    return max(0, int(entry.get("count", 0) or 0))


def _normalize_utr_fish_name(raw: str) -> str:
    name = (raw or "").strip()
    upper = name.upper()
    if upper.endswith(" UTR"):
        return name[:-4].strip()
    if upper.endswith("UTR") and len(name) > 3:
        return name[:-3].strip()
    return name


@dataclass
class UseCheckContext:
    user_id: str
    user: object
    is_private: bool = False
    _active_buffs_cache: list | None = field(default=None, init=False, repr=False)
    _collected_cache: set[tuple[str, str]] | None = field(
        default=None, init=False, repr=False
    )

    @classmethod
    async def create(
        cls,
        user_id: str,
        *,
        is_private: bool = False,
        user=None,
        nickname: str = "",
    ) -> "UseCheckContext":
        if user is None:
            user = await get_or_create_user(user_id, nickname)
        return cls(user_id=str(user_id), user=user, is_private=is_private)

    @property
    def status(self) -> dict:
        status = getattr(self.user, "fishing_status", None)
        return status if isinstance(status, dict) else {}

    def item_count(self, canonical_name: str) -> int:
        if canonical_name in _JSON_ITEMS:
            item_id, item_type = _JSON_ITEMS[canonical_name]
            return _json_item_count(self.user, item_id, item_type)
        field_name = _SCALAR_FIELDS.get(canonical_name)
        if field_name:
            return max(0, int(getattr(self.user, field_name, 0) or 0))
        return 0

    def nest_count(self) -> int:
        counters = getattr(self.user, "daily_counters", None)
        if not isinstance(counters, dict):
            return 0
        info = counters.get("nest")
        if not isinstance(info, dict) or info.get("date") != date.today().isoformat():
            return 0
        return max(0, int(info.get("count", 0) or 0))

    def collected(self) -> set[tuple[str, str]]:
        if self._collected_cache is None:
            raw = getattr(self.user, "collection", None)
            collection, _ = _normalize_collection(raw if isinstance(raw, dict) else {})
            self._collected_cache = {
                (fish_name, rarity)
                for fish_name, rarities in collection.items()
                if isinstance(rarities, dict)
                for rarity, count in rarities.items()
                if count
            }
        return self._collected_cache

    async def active_buffs(self) -> list:
        if self._active_buffs_cache is None:
            now = datetime.now()
            self._active_buffs_cache = await FishingBuff.filter(
                buff_type__in=_RELEVANT_BUFF_TYPES,
                start_time__lte=now,
                end_time__gt=now,
            ).all()
        return self._active_buffs_cache

    async def global_buff_count(self, buff_type: str) -> int:
        return sum(
            1
            for buff in await self.active_buffs()
            if buff.buff_type == buff_type
            and buff.target_type == BuffEffect.TARGET_TYPE_GLOBAL
        )

    async def location_nest_count(self, scene_instance_id: str) -> int:
        return sum(
            1
            for buff in await self.active_buffs()
            if buff.buff_type == BuffEffect.BUFF_TYPE_NEST
            and buff.target_type == BuffEffect.TARGET_TYPE_LOCATION
            and str(buff.target_id) == str(scene_instance_id)
        )

    async def starry_bonus_count(self) -> int:
        values = [
            int(buff.value or 0)
            for buff in await self.active_buffs()
            if buff.buff_type == BuffEffect.BUFF_TYPE_STARRY_BONUS
            and buff.target_type == BuffEffect.TARGET_TYPE_GLOBAL
        ]
        if not values:
            return 0
        return min(max(values) // STARRY_BONUS_VALUE, STARRY_MAX_LAYERS)

    async def utr_options(self, *, limit: int = 10) -> list[UtrUseOption]:
        collected = self.collected()
        options: list[UtrUseOption] = []
        for location in ConfigManager.get_locations():
            fish_names = list(location.fish_pool)
            if not fish_names:
                continue
            if not any((fish_name, "UTR") in collected for fish_name in fish_names):
                continue
            if any((fish_name, "UR") not in collected for fish_name in fish_names):
                continue
            for fish_name in fish_names:
                options.append(UtrUseOption(str(location.id), fish_name))
                if len(options) >= limit:
                    return options
        return options


def _insufficient_reason(canonical_name: str) -> str:
    unit = _UNITS.get(canonical_name, "个")
    return f"{canonical_name}不足（当前0{unit}）"


async def _check_time_potion(context: UseCheckContext) -> str:
    if not context.status:
        return "你还没有在钓鱼，无法使用时光药水！请先【钓鱼 地点编号】开始钓鱼"
    bait = ConfigManager.get_bait(str(getattr(context.user, "bait_id", "0") or "0"))
    if not bait or str(getattr(context.user, "bait_id", "0")) == "0":
        return "当前没有使用鱼饵，无法使用时光药水"
    bait_count = _json_item_count(context.user, str(bait.id), "bait")
    if bait_count < 30:
        return f"当前鱼饵{bait.name}不足30个（当前{bait_count}个），无法使用时光药水"
    return ""


def _check_rollback_potion(context: UseCheckContext) -> str:
    if not context.status:
        return "你还没有在钓鱼，无法使用回档药水！请先【钓鱼 地点编号】开始钓鱼"
    if not is_starry_location(str(context.status.get("location_id", ""))):
        return "回档药水仅可在星空地图（11-20）使用，普通地图和猫猫乐园无法使用"
    if normalize_time_potions(context.status.get("time_potions_used", [])):
        return "本次钓鱼期间使用过时光药水，无法使用回档药水"
    return ""


async def _check_corn(context: UseCheckContext) -> str:
    status = context.status
    if not status:
        return "你还没有在钓鱼，无法打窝！请先【钓鱼 地点编号】开始钓鱼"
    location_id = str(status.get("location_id", ""))
    location = ConfigManager.get_location(location_id)
    if not location:
        return "当前钓鱼地点无效"
    if not context.is_private and context.nest_count() >= DAILY_NEST_LIMIT:
        return "今天已经不能再打窝了"
    available_layers = MAX_NEST_LAYERS
    if not is_starry_location(location_id):
        available_layers = max(
            0, MAX_NEST_LAYERS - await context.starry_bonus_count()
        )
    if available_layers <= 0:
        return "当前地点打窝效果已满，无法继续打窝"
    scene_id = get_scene_instance_id(status, location_id)
    if await context.location_nest_count(scene_id) >= available_layers:
        return "当前地点打窝效果已满，无法继续打窝"
    return ""


async def _check_display_frame(context: UseCheckContext) -> str:
    if (
        await context.global_buff_count(BuffEffect.BUFF_TYPE_FRAME)
        >= MAX_FRAME_BUFF_LAYERS
    ):
        return f"全图展示木框效果已满{MAX_FRAME_BUFF_LAYERS * 5}%，无法继续使用"
    return ""


async def _check_cat_frame(context: UseCheckContext) -> str:
    if not context.status:
        return "你还没有在钓鱼，无法使用猫框打窝！请先【钓鱼 地点编号】开始钓鱼"
    if not is_starry_location(str(context.status.get("location_id", ""))):
        return "猫框打窝只能在 11-20 星空图使用"
    if not context.is_private and context.nest_count() >= DAILY_NEST_LIMIT:
        return "今天已经不能再打窝了"
    if (
        await context.global_buff_count(BuffEffect.BUFF_TYPE_CAT_NEST)
        >= MAX_NEST_LAYERS
    ):
        return f"猫框打窝效果已满{MAX_NEST_LAYERS * 5}%，无法继续打窝"
    return ""


def _find_utr_target(raw_name: str):
    from ..backpack.black_market import find_fish_target

    fish_name = _normalize_utr_fish_name(raw_name)
    target = find_fish_target(fish_name, "UTR")
    if target:
        return fish_name, target
    alt = fish_name[:-1] if fish_name.endswith("鱼") else f"{fish_name}鱼"
    return alt, find_fish_target(alt, "UTR")


async def _check_utr_ticket(context: UseCheckContext, arg: str) -> str:
    if not arg:
        if await context.utr_options():
            return ""
        return (
            "当前没有可用 UTR自选券兑换的鱼："
            "需先在对应地图解锁至少1条UTR，且收集齐该图全部UR。"
        )
    fish_name, target = _find_utr_target(arg)
    if not target:
        return (
            f"未找到鱼种「{fish_name}」，请输入正确的鱼名"
            "（如地图中的 UTR 鱼）"
        )
    location = ConfigManager.get_location(target.location_id)
    fish_names = list(location.fish_pool) if location else []
    collected = context.collected()
    if not any((name, "UTR") in collected for name in fish_names):
        return (
            f"无法兑换：需要先在【{target.location_name}】解锁至少 1 条 "
            f"UTR 鱼后，才能用自选券兑换该图的 UTR（目标：{target.name}）"
        )
    missing = [name for name in fish_names if (name, "UR") not in collected]
    if missing:
        missing_names = "、".join(missing)
        return (
            f"无法兑换：需先收集齐【{target.location_name}】的全部 UR 鱼"
            f"（还差 {len(missing)} 条：{missing_names}），"
            "才能用自选券兑换该图的 UTR"
        )
    return ""


def _check_big_fish(context: UseCheckContext, arg: str) -> str:
    position = (arg or "").strip()
    if position and position not in {"1", "2", "3"}:
        return "角色位置只能是1、2或3！"
    if not position and None not in mut.get_character_slots_on_user(context.user):
        return "队伍已满，需要输入“钓鱼使用 大肥鱼 1/2/3”来指定他的位置！"
    return ""


async def check_item_use(
    context: UseCheckContext,
    item_name: str,
    *,
    count: int = 1,
    arg: str = "",
) -> ItemUseCheck:
    canonical = normalize_use_item_name(item_name)
    held_count = context.item_count(canonical)
    if canonical not in _ITEM_ORDER:
        return ItemUseCheck(canonical, held_count, False, f"未知的物品：{item_name}")
    if count < 1:
        return ItemUseCheck(canonical, held_count, False, "数量必须大于0")
    if held_count <= 0:
        return ItemUseCheck(
            canonical, held_count, False, _insufficient_reason(canonical)
        )

    reason = ""
    if canonical == "时光药水":
        reason = await _check_time_potion(context)
    elif canonical == "回档药水":
        reason = _check_rollback_potion(context)
    elif canonical == "UTR自选券":
        reason = await _check_utr_ticket(context, arg)
    elif canonical == "香甜玉米":
        reason = await _check_corn(context)
    elif canonical == "展示木框":
        reason = await _check_display_frame(context)
    elif canonical == "猫猫框":
        reason = await _check_cat_frame(context)
    elif canonical == "大肥鱼":
        reason = _check_big_fish(context, arg)
    elif canonical in {"许愿药水", "星空框"}:
        reason = "当前版本暂未开放使用方式"
    return ItemUseCheck(canonical, held_count, not reason, reason)


async def get_held_item_use_checks(
    context: UseCheckContext,
) -> list[ItemUseCheck]:
    checks: list[ItemUseCheck] = []
    for item_name in _ITEM_ORDER:
        if context.item_count(item_name) <= 0:
            continue
        checks.append(await check_item_use(context, item_name))
    return checks


__all__ = [
    "ItemUseCheck",
    "UseCheckContext",
    "UtrUseOption",
    "check_item_use",
    "get_held_item_use_checks",
    "normalize_use_item_name",
]
