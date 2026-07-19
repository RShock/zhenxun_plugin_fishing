"""
背包主模块（向后兼容门面）。

所有核心逻辑已迁移到 backpack/ 子包，本模块仅做重新导出以保持现有导入路径有效。
新增代码应直接从 backpack/ 导入。
"""

from .backpack import (
    FishSelection,
    get_backpack_image,
    get_collection_image,
    gift_fish,
    lock_fish,
    parse_fish_selection,
    sell_fish,
    unlock_fish,
)

__all__ = [
    "get_backpack_image",
    "get_collection_image",
    "sell_fish",
    "gift_fish",
    "lock_fish",
    "unlock_fish",
    "FishSelection",
    "parse_fish_selection",
]