"""
数据模型包。

拆分为多个子模块：
- user.py: FishingUser, _make_naive
- buff.py: BuffEffect, FishingBuff, FishingBuffCalculator
- weather.py: FishingWeather
- exchange.py: FishingExchangeRecord
- ledger.py: FishingLedger (账本)
- web_key.py: FishingWebKey
- announcement.py: FishingActiveGroup
"""

from .announcement import FishingActiveGroup
from .buff import BuffEffect, BuffMeta, FishingBuff, FishingBuffCalculator
from .exchange import FishingExchangeRecord
from .ledger import FishingLedger
from .user import FishingUser, _make_naive
from .weather import FishingWeather
from .web_key import FishingWebKey

__all__ = [
    "BuffEffect",
    "BuffMeta",
    "FishingActiveGroup",
    "FishingBuff",
    "FishingBuffCalculator",
    "FishingExchangeRecord",
    "FishingLedger",
    "FishingUser",
    "FishingWeather",
    "FishingWebKey",
    "_make_naive",
]
