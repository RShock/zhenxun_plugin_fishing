"""
backpack/ — 背包、卖鱼、卖鱼饵、赠送、锁定、图鉴子包。

各模块只负责单一关注点：
  selection — 鱼获选择解析（FishSelection, parse_fish_selection）
  view      — 渲染（背包、图鉴）
  sell      — 卖鱼、卖鱼饵
  gift      — 赠送
  lock      — 锁定/解锁
"""

from .black_market import (
    black_market_exchange,
    extract_market_exchange_input,
    render_white_market_records,
    white_market_exchange,
)
from .gift import gift_fish
from .lock import auto_lock_fish, lock_fish, unlock_fish
from .selection import FishSelection, is_likely_misfire, parse_fish_selection
from .sell import sell_bait, sell_fish
from .view import get_backpack_image, get_collection_image, get_starry_exhibition_image

__all__ = [
    "get_backpack_image",
    "get_collection_image",
    "get_starry_exhibition_image",
    "sell_bait",
    "sell_fish",
    "gift_fish",
    "black_market_exchange",
    "extract_market_exchange_input",
    "render_white_market_records",
    "white_market_exchange",
    "lock_fish",
    "unlock_fish",
    "auto_lock_fish",
    "FishSelection",
    "is_likely_misfire",
    "parse_fish_selection",
]
