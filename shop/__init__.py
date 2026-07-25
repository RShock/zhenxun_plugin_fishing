"""
shop/ — 商店、打窝、皮肤子包。

避免在此处实现业务逻辑；各模块只负责单一关注点：
  view       — 渲染（商店、状态、地点列表、皮肤列表）
  purchase   — 购买、装备升级、展示栏升级
  nest       — 打窝
  account    — 兑换、签到、改名、皮肤切换
  item_dispatch — 「钓鱼使用」道具分发表（指向 items/potion_use 和 nest）

药水使用逻辑已拆出至 items/potion_use.py，药水配置见 config/items.json。
"""

from .account import change_skin, check_sign, exchange_to_gold, rename_fishing_user
from .nest import do_cat_frame_nest, do_nest
from .purchase import (
    buy_item,
    upgrade_display_slots,
    upgrade_hook,
    upgrade_rod,
)
from .view import (
    get_location_list_image,
    get_shop_image,
    get_skin_list_image,
    get_status_image,
)

__all__ = [
    # view
    "get_shop_image",
    "get_status_image",
    "get_location_list_image",
    "get_skin_list_image",
    # purchase
    "buy_item",
    "upgrade_rod",
    "upgrade_hook",
    "upgrade_display_slots",
    # nest
    "do_nest",
    "do_cat_frame_nest",
    # account
    "exchange_to_gold",
    "check_sign",
    "rename_fishing_user",
    "change_skin",
]
