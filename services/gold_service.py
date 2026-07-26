"""
统一金币服务 — 所有金币变动的入口，内置账本记录。

提供即时模式（非事务路径）和事务辅助模式：
- spend_gold / earn_gold: 修改金币 + 保存 + 记录账本（即时模式）
- GoldDelta: 事务内跟踪金币变动，事务后统一记录（事务模式）

替换原有散落在各处的 user.gold -= / FishingUser.add_gold / FishingUser.reduce_gold。
事务内（stop_mutations）的 apply_add_gold/apply_reduce_gold 保持不变，
由调用方在事务后用 GoldDelta 记录净变动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zhenxun.services.log import logger

from ..models import FishingUser
from . import ledger_service


# ═══════════════════════════════════════════════════════════════════════════════
# 即时模式：非事务路径使用
# ═══════════════════════════════════════════════════════════════════════════════


async def spend_gold(
    user_id: str,
    amount: int,
    operation: str,
    reason: str = "",
    details: dict | None = None,
) -> bool:
    """扣除金币并记录账本。余额不足返回 False。

    operation 示例: "buy_bait", "upgrade_rod", "upgrade_hook",
                   "buy_starry_ship", "exchange_gold"
    """
    if amount <= 0:
        return True
    user = await FishingUser.get_user(user_id)
    gold_before = int(user.gold or 0)
    if gold_before < amount:
        return False
    user.gold = gold_before - amount
    gold_after = user.gold
    await user.save(update_fields=["gold"])
    await ledger_service.log_gold_change(
        user_id,
        operation=operation,
        amount=-amount,
        gold_before=gold_before,
        gold_after=gold_after,
        reason=reason,
        details=details,
    )
    return True


async def earn_gold(
    user_id: str,
    amount: int,
    operation: str,
    reason: str = "",
    details: dict | None = None,
) -> None:
    """获得金币并记录账本。

    operation 示例: "sell_fish", "sell_bait", "fishing_income",
                   "display_income", "cat_gift", "achievement",
                   "gm_add", "gift_reward", "cat_park_material"
    """
    if amount <= 0:
        return
    user = await FishingUser.get_user(user_id)
    gold_before = int(user.gold or 0)
    user.gold = gold_before + amount
    gold_after = user.gold
    await user.save(update_fields=["gold"])
    await ledger_service.log_gold_change(
        user_id,
        operation=operation,
        amount=amount,
        gold_before=gold_before,
        gold_after=gold_after,
        reason=reason,
        details=details,
    )


async def set_gold(
    user_id: str,
    amount: int,
    operation: str,
    reason: str = "",
    details: dict | None = None,
) -> None:
    """GM 直接设置金币（不检查余额）。记录账本。"""
    user = await FishingUser.get_user(user_id)
    gold_before = int(user.gold or 0)
    user.gold = amount
    gold_after = amount
    await user.save(update_fields=["gold"])
    await ledger_service.log_gold_change(
        user_id,
        operation=operation,
        amount=gold_after - gold_before,
        gold_before=gold_before,
        gold_after=gold_after,
        reason=reason,
        details=details,
    )


async def adjust_gold(
    user_id: str,
    amount: int,
    operation: str,
    reason: str = "",
    details: dict | None = None,
) -> None:
    """GM 调整金币（可正可负，不检查余额）。记录账本。"""
    if amount == 0:
        return
    user = await FishingUser.get_user(user_id)
    gold_before = int(user.gold or 0)
    user.gold = gold_before + amount
    gold_after = user.gold
    await user.save(update_fields=["gold"])
    await ledger_service.log_gold_change(
        user_id,
        operation=operation,
        amount=amount,
        gold_before=gold_before,
        gold_after=gold_after,
        reason=reason,
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 事务辅助模式：事务内跟踪金币变动，事务后统一记录
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class GoldDelta:
    """事务内金币变动跟踪器。

    使用方式：
        delta = GoldDelta(user_id, gold_before)
        # 事务内 apply_add_gold(user, amount, dirty) 照常使用
        # 事务后:
        delta.set_after(user.gold)
        await delta.commit("fishing_income", "收杆结算")
    """

    user_id: str
    gold_before: int
    gold_after: int | None = None
    # 记录子项明细（如签到收益、展示收益、猫礼物、卖鱼等）
    items: list[dict] = field(default_factory=list)

    def add_item(self, operation: str, amount: int, reason: str = "") -> None:
        """记录一笔子项变动（仅用于 details 明细）。"""
        self.items.append({
            "operation": operation,
            "amount": amount,
            "reason": reason,
        })

    def set_after(self, gold_after: int) -> None:
        """事务完成后设置最终金币。"""
        self.gold_after = gold_after

    @property
    def total_delta(self) -> int:
        """金币净变动。"""
        if self.gold_after is None:
            return 0
        return self.gold_after - self.gold_before

    async def commit(
        self, operation: str, reason: str = ""
    ) -> bool:
        """将金币净变动写入账本。

        事务提交后调用。如果净变动为 0 则不记录。
        返回是否检测到异常。
        """
        if self.gold_after is None:
            return False
        delta = self.total_delta
        if delta == 0:
            return False
        details = {
            "items": self.items,
            "gold_before": self.gold_before,
            "gold_after": self.gold_after,
        }
        return await ledger_service.log_gold_change(
            self.user_id,
            operation=operation,
            amount=delta,
            gold_before=self.gold_before,
            gold_after=self.gold_after,
            reason=reason or f"净变动{delta:+d}",
            details=details,
        )
