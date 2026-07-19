"""
shop/ — 商店、药水、打窝、皮肤子包。

避免在此处实现业务逻辑；各模块只负责单一关注点：
  view       — 渲染（商店、状态、地点列表、皮肤列表）
  purchase   — 购买、装备升级、展示栏升级
  nest       — 打窝
  potion_use — 药水使用（时光、回档、幸运、闪光、展示木框加速、UTR自选券）
  misc       — 兑换、签到、改名、皮肤切换
"""

from .misc import change_skin, check_sign, exchange_to_gold, rename_fishing_user
from .nest import do_cat_frame_nest, do_nest
from .potion_use import (
    use_display_frame_buff,
    use_flash_potion,
    use_lucky_potion,
    use_rollback_potion,
    use_time_potion,
    use_utr_select_ticket,
)
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
    # potion
    "use_time_potion",
    "use_rollback_potion",
    "use_lucky_potion",
    "use_flash_potion",
    "use_utr_select_ticket",
    "use_display_frame_buff",
    # misc
    "exchange_to_gold",
    "check_sign",
    "rename_fishing_user",
    "change_skin",
]