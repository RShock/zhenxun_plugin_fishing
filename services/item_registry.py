"""
统一道具注册表 — 将散落在不同字段的道具统一抽象管理。

当前道具存储分为两类：
1. JSON 存储：potion（药水）、bait（鱼饵）存于 FishingUser.items JSONField
2. 标量存储：corn（玉米）、display_frames（木框）、cat_frames（猫框）、star_frames（星空框）
   存于 FishingUser 的独立 IntField

本模块提供统一的 add/remove/get 接口，自动路由到正确的存储后端。
同时支持两种模式：
- 即时模式：修改后立即 save（适用于非事务路径）
- 脏模式：仅修改内存，返回 dirty 集合由调用方统一 save（适用于事务内批量操作）

例外：展示栏（displays）和星空鱼展馆（starry_exhibition）不做统一管理，保持独立存储。
"""

from __future__ import annotations

from typing import Any

from ..models import FishingUser
from ..models import user_mutations as mut


# ═══════════════════════════════════════════════════════════════════════════════
# 道具类型常量
# ═══════════════════════════════════════════════════════════════════════════════

class ItemType:
    POTION = "potion"
    BAIT = "bait"
    CORN = "corn"
    DISPLAY_FRAME = "display_frame"
    CAT_FRAME = "cat_frame"
    STAR_FRAME = "star_frame"


# ═══════════════════════════════════════════════════════════════════════════════
# 存储后端映射
# ═══════════════════════════════════════════════════════════════════════════════

# 每种道具类型对应的存储方式和字段名
# ("json", None) → 存于 items JSONField，使用 (item_id, item_type) 作 key
# ("scalar", field_name) → 存于独立 IntField，item_id 被忽略
_STORAGE_MAP: dict[str, tuple[str, str | None]] = {
    ItemType.POTION: ("json", None),
    ItemType.BAIT: ("json", None),
    ItemType.CORN: ("scalar", "corn"),
    ItemType.DISPLAY_FRAME: ("scalar", "display_frames"),
    ItemType.CAT_FRAME: ("scalar", "cat_frames"),
    ItemType.STAR_FRAME: ("scalar", "star_frames"),
}

# 标量道具类型的 display name（用于账本记录）
_SCALAR_DISPLAY_NAMES: dict[str, str] = {
    ItemType.CORN: "香甜玉米",
    ItemType.DISPLAY_FRAME: "木框",
    ItemType.CAT_FRAME: "猫框",
    ItemType.STAR_FRAME: "星空框",
}


def _get_storage(item_type: str) -> tuple[str, str | None]:
    """获取道具的存储后端信息。未知类型默认走 JSON 存储。"""
    return _STORAGE_MAP.get(item_type, ("json", None))


def is_scalar_item(item_type: str) -> bool:
    """判断是否为标量存储的道具类型。"""
    storage, _ = _get_storage(item_type)
    return storage == "scalar"


def get_display_name(item_id: str, item_type: str) -> str:
    """获取道具的显示名称，用于账本记录。"""
    if is_scalar_item(item_type):
        return _SCALAR_DISPLAY_NAMES.get(item_type, item_type)
    # JSON 道具：从 ConfigManager 获取名称
    try:
        from ..config import ConfigManager

        if item_type == ItemType.BAIT:
            bait = ConfigManager.get_bait(item_id)
            return bait.name if bait else f"鱼饵#{item_id}"
        if item_type == ItemType.POTION:
            return item_id  # 药水名称即 item_id
    except Exception:
        pass
    return f"{item_type}#{item_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# 脏模式操作（内存修改，不 save）
# ═══════════════════════════════════════════════════════════════════════════════


def apply_add_item(
    user: FishingUser,
    item_id: str,
    item_type: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> None:
    """统一添加道具（内存修改，不 save）。

    标量道具：直接修改对应 IntField
    JSON 道具：写入 items JSONField 的 {item_id|item_type: {item_type, count}}
    """
    if count <= 0:
        return
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        current = int(getattr(user, field_name, 0) or 0)
        setattr(user, field_name, current + count)
        mut.mark_dirty(dirty, field_name)
    else:
        mut.apply_add_item(user, item_id, item_type, count, dirty)


def apply_remove_item(
    user: FishingUser,
    item_id: str,
    item_type: str,
    count: int = 1,
    dirty: set[str] | None = None,
) -> bool:
    """统一消耗道具（内存修改，不 save）。返回是否成功。"""
    if count <= 0:
        return True
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        current = int(getattr(user, field_name, 0) or 0)
        if current < count:
            return False
        setattr(user, field_name, current - count)
        mut.mark_dirty(dirty, field_name)
        return True
    else:
        return mut.apply_remove_item(user, item_id, item_type, count, dirty)


def get_item_on_user(
    user: FishingUser, item_id: str, item_type: str
) -> dict | None:
    """从内存中的 user 实例查询道具数量。"""
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        count = int(getattr(user, field_name, 0) or 0)
        if count <= 0:
            return None
        return {"item_id": item_type, "item_type": item_type, "count": count}
    else:
        return mut.get_item_on_user(user, item_id, item_type)


def get_all_items_on_user(user: FishingUser) -> list[dict]:
    """获取用户所有道具列表（统一格式）。"""
    result: list[dict] = []
    # 标量道具
    for item_type, (_, field_name) in _STORAGE_MAP.items():
        if not field_name:
            continue
        count = int(getattr(user, field_name, 0) or 0)
        if count > 0:
            result.append({
                "item_id": item_type,
                "item_type": item_type,
                "count": count,
            })
    # JSON 道具
    result.extend(mut.get_user_items_on_user(user))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 即时模式操作（修改后立即 save）
# ═══════════════════════════════════════════════════════════════════════════════


async def add_item(
    user_id: str, item_id: str, item_type: str, count: int = 1
) -> None:
    """统一添加道具并立即保存。"""
    if count <= 0:
        return
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        user = await FishingUser.get_user(user_id)
        dirty: set[str] = set()
        apply_add_item(user, item_id, item_type, count, dirty)
        await mut.save_dirty(user, dirty)
    else:
        await FishingUser.add_item(user_id, item_id, item_type, count)


async def remove_item(
    user_id: str, item_id: str, item_type: str, count: int = 1
) -> bool:
    """统一消耗道具并立即保存。返回是否成功。"""
    if count <= 0:
        return True
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        user = await FishingUser.get_user(user_id)
        dirty: set[str] = set()
        ok = apply_remove_item(user, item_id, item_type, count, dirty)
        if ok:
            await mut.save_dirty(user, dirty)
        return ok
    else:
        return await FishingUser.remove_item(user_id, item_id, item_type, count)


async def get_item(
    user_id: str, item_id: str, item_type: str
) -> dict | None:
    """查询用户某道具。"""
    storage, field_name = _get_storage(item_type)
    if storage == "scalar" and field_name:
        user = await FishingUser.get_user(user_id)
        return get_item_on_user(user, item_id, item_type)
    else:
        return await FishingUser.get_item(user_id, item_id, item_type)


async def get_all_items(user_id: str) -> list[dict]:
    """获取用户所有道具列表（标量 + JSON 统一）。"""
    user = await FishingUser.get_user(user_id)
    return get_all_items_on_user(user)
